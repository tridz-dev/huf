# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Backend API for the Huf Telegram Mini App (the admin cockpit's rich UI).

Contract: ``docs/gateways/telegram-miniapp-api.md``. Security summary:

- Endpoints are ``allow_guest`` only because the caller has no Frappe session; authentication is the opaque
  bearer token minted by ``telegram_admin.telegram_miniapp_auth`` (header ``X-Huf-Tg-Token`` only; a
  ``token`` query/body param is refused so the secret never lands in access logs). Each call resolves the token, re-reads the LIVE binding (including the Admin re-check, so a
  downgrade or revocation applies immediately) and runs every data access inside
  ``telegram_admin.run_as(bound user)`` under normal Frappe permission checks. Never Administrator/Guest,
  never ``ignore_permissions`` for business data.
- State changes are two-step (``act_prepare`` -> ``act_confirm``) using the cockpit nonce machinery and the
  cockpit ``execute`` path, so they are single-use, bound to the Telegram user, and audited.
- Every response is ``{"ok": true, "data": ...}`` or ``{"ok": false, "error": {"code", "message"}}`` with a
  matching HTTP status; internals are never leaked.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from huf.ai import telegram_admin as ta

TOKEN_HEADER = "X-Huf-Tg-Token"
API_RATE_LIMIT = 60  # calls per Telegram user per window
API_RATE_WINDOW = 60
IP_RATE_LIMIT = 120  # calls per IP per window (stops token guessing)
SEARCH_DEFAULT = 10
SEARCH_MAX = 25
AUDIT_DEFAULT = 20
AUDIT_MAX = 50
SUMMARY_MAX_FIELDS = 12
MINIAPP_CHAT = "miniapp"  # nonce "chat" binding prefix for Mini App originated confirmations


def nonce_chat(binding: dict) -> str:
	"""Nonce binding scope: (gateway, telegram user) via the user arg, so ``miniapp:<gateway>``."""
	return f"{MINIAPP_CHAT}:{binding['gateway']}"

_SECRET_FIELD_RE = re.compile(
	r"password|passwd|secret|token|key|otp|pairing_?code|hash|credential|signature|webhook", re.IGNORECASE
)
_HIDDEN_FIELDTYPES = ("Password", "Attach", "Attach Image", "Table", "Table MultiSelect", "Code", "JSON")


class ApiError(Exception):
	"""A refusal with a safe message and an HTTP status."""

	def __init__(self, code: str, message: str, status: int = 400) -> None:
		super().__init__(message)
		self.code, self.message, self.status = code, message, status


# -- envelope ----------------------------------------------------------------------------------


def _fail(code: str, message: str, status: int) -> dict:
	_set_status(status)
	return {"ok": False, "error": {"code": code, "message": message}}


def _set_status(status: int) -> None:
	try:
		import frappe

		frappe.local.response["http_status_code"] = status
	except Exception:
		pass


def _classify(exc: BaseException) -> tuple[str, str, int]:
	if isinstance(exc, ApiError):
		return exc.code, exc.message, exc.status
	if isinstance(exc, ta.AdminError):
		msg = str(exc)
		code = "permission_denied" if msg == ta.MSG_DENIED else "refused"
		return code, msg, 403 if code == "permission_denied" else 400
	try:
		import frappe

		if isinstance(exc, frappe.PermissionError):
			return "permission_denied", "You do not have permission for that.", 403
		if isinstance(exc, frappe.DoesNotExistError):
			return "not_found", "Not found.", 404
		if isinstance(exc, frappe.ValidationError):
			return "invalid", ta._safe_error(exc) or "Invalid request.", 400
	except Exception:
		pass
	return "internal", "Something went wrong.", 500


def _envelope(fn: Callable[[], Any]) -> dict:
	try:
		return {"ok": True, "data": fn()}
	except Exception as exc:
		code, message, status = _classify(exc)
		if code == "internal":
			_log_internal(exc)
			_rollback()
		return _fail(code, message, status)


def _log_internal(exc: BaseException) -> None:
	try:
		import frappe

		frappe.logger("huf").warning(f"Telegram Mini App API error: {ta._safe_error(exc)}")
	except Exception:
		pass


def _rollback() -> None:
	ta._rollback()


# -- auth --------------------------------------------------------------------------------------


def _request_token(token: str = "") -> str:
	"""Return the bearer token from the ``X-Huf-Tg-Token`` header only.

	The ``token`` argument exists only because Frappe binds the URL query string to the whitelisted function
	signature; a non-empty value is refused (empty string) so tokens never travel in URLs or access logs.
	"""
	if (token or "").strip():
		return ""
	value = ""
	try:
		import frappe

		value = frappe.get_request_header(TOKEN_HEADER) or ""
	except Exception:
		pass
	value = value.strip()
	if value.lower().startswith("bearer "):
		value = value[7:].strip()
	return value


def _auth(token: str = "", *, cache: Any = None, now: float | None = None) -> tuple[dict, dict, str]:
	"""Return ``(session, live_binding, token)`` or raise ``ApiError`` (one generic 401)."""
	unauth = ApiError("unauthorized", "Session expired. Reopen the app from Telegram.", 401)
	raw = _request_token(token)
	if not raw:
		raise unauth
	ip = ta._client_ip()
	if ip and not ta.check_rate(f"mapi_ip:{ip}", IP_RATE_LIMIT, API_RATE_WINDOW, cache=cache, now=now):
		raise ApiError("rate_limited", "Too many requests.", 429)
	session = ta.resolve_session_token(raw, cache=cache, now=now)
	if not session:
		raise unauth
	if not ip:  # unknown client IP: a per-user bucket, never one shared empty-IP bucket
		user_key = f"mapi_nouip:{session.get('gateway')}:{session.get('telegram_user_id')}"
		if not ta.check_rate(user_key, IP_RATE_LIMIT, API_RATE_WINDOW, cache=cache, now=now):
			raise ApiError("rate_limited", "Too many requests.", 429)
	# resolve_session_token already confirmed an active binding; re-read it so the CURRENT role scope
	# (e.g. Admin demoted to Operator) applies, not the scope frozen into the token at mint time.
	binding = ta.get_binding(session["telegram_user_id"], session["gateway"], cache=cache)
	if (
		not binding
		or binding.get("name") != session.get("binding")
		or binding.get("frappe_user") != session.get("frappe_user")
	):
		raise unauth
	if not ta.check_rate(
		f"mapi:{session['telegram_user_id']}", API_RATE_LIMIT, API_RATE_WINDOW, cache=cache, now=now
	):
		raise ApiError("rate_limited", "Too many requests.", 429)
	return session, binding, raw


def _serve(
	token: str, fn: Callable[[dict, dict], Any], *, as_user: bool = True, cache: Any = None, now=None
) -> dict:
	"""Authenticate, then run ``fn(binding, session)`` (inside ``run_as`` unless ``as_user`` is False)."""

	def run():
		session, binding, _raw = _auth(token, cache=cache, now=now)
		if not as_user:
			return fn(binding, session)
		with ta.run_as(binding["frappe_user"]):
			return fn(binding, session)

	return _envelope(run)


def _rank(binding: dict) -> int:
	return ta._rank(binding)


def _clamp(value: Any, default: int, maximum: int) -> int:
	try:
		n = int(value)
	except (TypeError, ValueError):
		return default
	return max(1, min(n, maximum))


# -- handlers (run inside run_as unless noted) -------------------------------------------------


def _h_me(binding: dict, session: dict, now: float | None = None) -> dict:
	import frappe

	return {
		"frappe_user": binding["frappe_user"],
		"full_name": frappe.utils.get_fullname(binding["frappe_user"]),
		"role_scope": binding["role_scope"],
		"gateway": binding["gateway"],
		"telegram_user_id": str(binding["telegram_user_id"]),
	}


def _h_config(binding: dict, session: dict) -> dict:
	scope = binding["role_scope"]
	return {
		"gateway": binding["gateway"],
		"bot_name": _bot_name(binding["gateway"]),
		"role_scope": scope,
		"session_ttl": ta.SESSION_TTL,
		"confirm_ttl": ta.NONCE_TTL,
		"limits": {"search_max": SEARCH_MAX, "audit_max": AUDIT_MAX},
		"features": {
			"search": True,
			"approvals": True,
			"digest": True,
			"act": _rank(binding) >= ta.ROLE_RANK["Operator"],
			"audit": True,
			"audit_all": _rank(binding) >= ta.ROLE_RANK["Admin"],
		},
	}


def _bot_name(gateway: str) -> str:
	try:
		import frappe

		return str(frappe.db.get_value("Gateway", gateway, "gateway_name") or gateway)
	except Exception:
		return gateway


def _h_search(binding: dict, session: dict, doctype: str, text: str, limit: Any) -> dict:
	import frappe

	dt = ta._check_doctype(doctype)
	n = _clamp(limit, SEARCH_DEFAULT, SEARCH_MAX)
	meta = frappe.get_meta(dt)
	title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else None
	fields = ["name"] + ([title_field] if title_field else [])
	or_filters = None
	text = (text or "").strip()[:100]
	if text:
		like = f"%{text}%"
		or_filters = [[dt, "name", "like", like]] + ([[dt, title_field, "like", like]] if title_field else [])
	rows = frappe.get_list(
		dt, fields=fields, or_filters=or_filters, limit_page_length=n, order_by="modified desc"
	)
	return {
		"doctype": dt,
		"items": [
			{"name": r["name"], "title": (r.get(title_field) if title_field else "") or r["name"]}
			for r in rows
		],
	}


def _field_visible(df: Any) -> bool:
	return (
		not df.permlevel
		and not df.hidden
		and df.fieldtype not in _HIDDEN_FIELDTYPES
		and df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Button")
		and not _SECRET_FIELD_RE.search(str(df.fieldname or ""))
	)


def _masked_fields(doc: Any, meta: Any) -> set:
	"""Fields the session user may not read: permlevel access denied or a Frappe field mask set."""
	masked: set = set()
	for df in meta.fields:
		try:
			denied = bool(getattr(df, "mask", None)) or not doc.has_permlevel_access_to(df.fieldname, df, "read")
		except Exception:
			denied = True  # fail closed
		if denied:
			masked.add(df.fieldname)
	return masked


def _h_get_doc_summary(binding: dict, session: dict, doctype: str, name: str) -> dict:
	import frappe

	dt = ta._check_doctype(doctype)
	name = (name or "").strip()
	if not name:
		raise ApiError("invalid", "Name is required.", 400)
	doc = frappe.get_doc(dt, name)
	doc.check_permission("read")
	meta = frappe.get_meta(dt)
	workflow = meta.get_workflow()
	state_field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field") if workflow else None
	docstatus = (
		{0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(doc.docstatus) if meta.is_submittable else None
	)
	fields, fallback = [], []
	masked = _masked_fields(doc, meta)
	for df in meta.fields:
		if not _field_visible(df):
			continue
		if df.fieldname in masked:
			continue
		value = doc.get(df.fieldname)
		if value in (None, ""):
			continue
		item = {
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"value": str(value)[:200],
		}
		(fields if df.in_list_view else fallback).append(item)
	fields = (fields + fallback)[:SUMMARY_MAX_FIELDS]
	title = doc.get(meta.title_field) if meta.title_field else None
	actions = ta._transitions(doc) if _rank(binding) >= ta.ROLE_RANK["Operator"] else []
	return {
		"doctype": dt,
		"name": doc.name,
		"title": str(title) if title else doc.name,
		"workflow_state": doc.get(state_field) if state_field else None,
		"status": doc.get("status"),
		"docstatus": docstatus,
		"modified": str(doc.modified),
		"fields": fields,
		"actions": actions,
		"desk_url": ta._desk_url(dt, doc.name),
	}


def _h_approvals(binding: dict, session: dict) -> dict:
	import frappe

	items = []
	can_act = _rank(binding) >= ta.ROLE_RANK["Operator"]
	for r in ta.pending_approvals(limit=ta.LIST_LIMIT * 2):
		dt, dn = r["reference_doctype"], r["reference_name"]
		if dt in ta.DENY_DOCTYPES:
			continue
		actions: list[str] = []
		if can_act:
			try:
				doc = frappe.get_doc(dt, dn)
				doc.check_permission("read")
				actions = ta._transitions(doc)
			except Exception:
				continue
		items.append({"doctype": dt, "name": dn, "state": r.get("workflow_state") or "", "actions": actions})
	return {"items": items}


def _h_act_prepare(
	binding: dict, session: dict, doctype: str, name: str, action: str, cache: Any = None, now=None
) -> dict:
	import frappe

	if _rank(binding) < ta.ROLE_RANK["Operator"]:
		raise ApiError("permission_denied", "Operator scope required.", 403)
	dt = ta._check_doctype(doctype)
	name, action = (name or "").strip(), (action or "").strip()
	if not name or not action:
		raise ApiError("invalid", "Name and action are required.", 400)
	doc = frappe.get_doc(dt, name)
	doc.check_permission("read")
	if action not in ta._transitions(doc):
		raise ApiError("invalid", "That action is not available for this record.", 400)
	act = {"op": "workflow", "dt": dt, "dn": doc.name, "transition": action}
	nonce = ta.issue_nonce(binding["telegram_user_id"], nonce_chat(binding), act, cache=cache, now=now)
	return {
		"nonce": nonce,
		"description": ta.describe(act),
		"expires_in": ta.NONCE_TTL,
		"action": {"doctype": dt, "name": doc.name, "action": action},
	}


def _h_act_confirm(binding: dict, session: dict, nonce: str, cache: Any = None, now=None) -> dict:
	"""Not under ``run_as`` here: ``execute`` switches to the bound user itself and audits."""
	if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", nonce or ""):
		raise ApiError("invalid", ta.MSG_EXPIRED, 400)
	act = ta.consume_nonce(nonce, binding["telegram_user_id"], nonce_chat(binding), cache=cache, now=now)
	if act.get("op") != "workflow":
		raise ApiError("invalid", ta.MSG_EXPIRED, 400)
	ctx = ta.Ctx(
		binding=binding,
		tg_user=str(binding["telegram_user_id"]),
		chat_id=MINIAPP_CHAT,
		gateway=binding["gateway"],
		cache=cache,
		now=now,
	)
	text = ta.execute(ctx, act, nonce, ip=ta._client_ip())
	return {"result": text}


def _h_digest(binding: dict, session: dict) -> dict:
	data = ta.collect_digest(binding)
	return {
		"text": ta.compose_digest(data),
		"approvals": [
			{
				"doctype": r.get("reference_doctype"),
				"name": r.get("reference_name"),
				"state": r.get("workflow_state") or "",
			}
			for r in data.get("approvals") or []
			if r.get("reference_doctype") not in ta.DENY_DOCTYPES
		],
		"actions_24h": int(data.get("actions_24h") or 0),
	}


_AUDIT_FIELDS = ["name", "action", "frappe_user", "reference_doctype", "reference_name", "result", "creation"]


def _h_audit(binding: dict, session: dict, limit: Any) -> dict:
	import frappe

	n = _clamp(limit, AUDIT_DEFAULT, AUDIT_MAX)
	if _rank(binding) >= ta.ROLE_RANK["Admin"]:
		rows = frappe.get_list(  # permission-checked (System Manager / Huf Manager)
			"Telegram Admin Audit", fields=_AUDIT_FIELDS, limit_page_length=n, order_by="creation desc"
		)
	else:
		# Own rows only. System read, narrowed to the bound user: the audit DocType is not readable by
		# ordinary users, but everyone may see what was done in their own name.
		rows = frappe.get_all(
			"Telegram Admin Audit",
			filters={"frappe_user": binding["frappe_user"]},
			fields=_AUDIT_FIELDS,
			limit_page_length=n,
			order_by="creation desc",
		)
	items = [
		{**{k: r.get(k) for k in _AUDIT_FIELDS if k != "name"}, "creation": str(r["creation"])} for r in rows
	]
	return {"scope": "all" if _rank(binding) >= ta.ROLE_RANK["Admin"] else "own", "items": items}


def _h_revoke_token(binding: dict, session: dict, raw: str, cache: Any = None) -> dict:
	ta._cache(cache).delete_value(f"huf_tg_adm_s:{ta._sha(raw)}")
	try:
		ta.write_audit(binding, {"op": "miniapp_logout"}, "ok", ip=ta._client_ip())
		ta._commit()
	except Exception:
		pass
	return {"revoked": True}


# -- whitelisted endpoints ---------------------------------------------------------------------


def _whitelist(**kw):
	try:
		import frappe

		return frappe.whitelist(**kw)
	except Exception:  # pragma: no cover
		return lambda fn: fn


@_whitelist(allow_guest=True, methods=["POST"])
def me(token: str = "") -> dict:
	return _serve(token, _h_me)


@_whitelist(allow_guest=True, methods=["POST"])
def config(token: str = "") -> dict:
	return _serve(token, _h_config, as_user=False)


@_whitelist(allow_guest=True, methods=["POST"])
def search(doctype: str, text: str = "", limit: int = SEARCH_DEFAULT, token: str = "") -> dict:
	return _serve(token, lambda b, s: _h_search(b, s, doctype, text, limit))


@_whitelist(allow_guest=True, methods=["POST"])
def get_doc_summary(doctype: str, name: str, token: str = "") -> dict:
	return _serve(token, lambda b, s: _h_get_doc_summary(b, s, doctype, name))


@_whitelist(allow_guest=True, methods=["POST"])
def approvals(token: str = "") -> dict:
	return _serve(token, _h_approvals)


@_whitelist(allow_guest=True, methods=["POST"])
def act_prepare(doctype: str, name: str, action: str, token: str = "") -> dict:
	return _serve(token, lambda b, s: _h_act_prepare(b, s, doctype, name, action))


@_whitelist(allow_guest=True, methods=["POST"])
def act_confirm(nonce: str, token: str = "") -> dict:
	return _serve(token, lambda b, s: _h_act_confirm(b, s, nonce), as_user=False)


@_whitelist(allow_guest=True, methods=["POST"])
def digest(token: str = "") -> dict:
	return _serve(token, _h_digest)


@_whitelist(allow_guest=True, methods=["POST"])
def audit(limit: int = AUDIT_DEFAULT, token: str = "") -> dict:
	return _serve(token, lambda b, s: _h_audit(b, s, limit))


@_whitelist(allow_guest=True, methods=["POST"])
def revoke_token(token: str = "") -> dict:
	raw = _request_token(token)
	return _serve(token, lambda b, s: _h_revoke_token(b, s, raw), as_user=False)
