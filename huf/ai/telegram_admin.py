# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram admin cockpit: an owner/admin personal assistant for Frappe/ERPNext inside the same bot.

Design: ``docs/gateways/telegram-admin-cockpit.md``. Summary of the security contract:

- Identity: a ``Telegram Admin Binding`` links a Telegram user id to a Frappe user. It is created only from a
  one-time code minted by the signed-in Frappe user (``create_binding_code``) and redeemed in a private chat
  with ``/start BIND-<code>``. Telegram-side self assertion never creates a binding.
- Every read/write runs AS the bound Frappe user (``run_as``) under normal Frappe permission checks:
  never Administrator/Guest, never ``ignore_permissions``. ``role_scope`` only narrows what the cockpit
  offers; it never grants a Frappe permission.
- State changes are two-step: the first message shows what will happen with signed Confirm/Cancel buttons
  carrying a single-use nonce (5 min TTL, bound to telegram user + chat + action hash); the confirm press
  executes and writes an append-only ``Telegram Admin Audit`` row.
- Only private chats, only slash commands and ``adm:`` callbacks are intercepted (update-handler registry);
  everything else (free text) falls through to the normal gateway agent routing.

Pure helpers take injectable ``cache`` / ``now``; Frappe is touched only through small helpers so unit tests
can run without a site.
"""

from __future__ import annotations

import hashlib
import json
import re
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable

PREFIX = "adm:"
NONCE_TTL = 300
BIND_CODE_TTL = 600
BIND_CODE_PREFIX = "BIND-"
SESSION_TTL = 900
MINIAPP_MAX_AGE = 600
RATE_LIMIT = 30  # commands + presses per user per window
RATE_WINDOW = 60
BIND_ATTEMPT_LIMIT = 5  # /start BIND- attempts per telegram user per window
BIND_ATTEMPT_WINDOW = 600
MINT_LIMIT = 5  # codes per Frappe user per window
MINT_WINDOW = 600
MINIAPP_AUTH_LIMIT = 20  # per IP per window
LIST_LIMIT = 10
ROLE_RANK = {"Viewer": 1, "Operator": 2, "Admin": 3}
FORBIDDEN_USERS = ("Administrator", "Guest")
# Secret-bearing / cockpit-internal doctypes are never browsable from chat even when permitted.
DENY_DOCTYPES = frozenset(
	{
		"Telegram Admin Binding",
		"Telegram Admin Audit",
		"Gateway",
		"Gateway Access Entry",
		"Gateway Event",
		"Email Account",
		"Huf API Key",
		"AI Provider",
		"User",
		"OAuth Bearer Token",
		"OAuth Client",
		"Access Log",
		"Session Default Settings",
		"System Settings",
	}
)
_SECRET_KEY_RE = re.compile(r"pass|token|secret|key|otp|pin|auth|cookie", re.IGNORECASE)
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
MSG_DENIED = "Not authorised."
MSG_EXPIRED = "This confirmation has expired or was already used."


class AdminError(Exception):
	"""A cockpit request was refused (message is safe to show the user)."""


# -- cache -------------------------------------------------------------------------------------


class MemCache:
	"""Process-local TTL cache with the subset of ``frappe.cache()`` used here (tests / no site)."""

	def __init__(self, clock: Callable[[], float] = time.time) -> None:
		self.d: dict[str, tuple[Any, float | None]] = {}
		self.clock = clock

	def get_value(self, key):
		item = self.d.get(key)
		if item is None:
			return None
		value, exp = item
		if exp is not None and self.clock() >= exp:
			self.d.pop(key, None)
			return None
		return value

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = (value, self.clock() + expires_in_sec if expires_in_sec else None)

	def delete_value(self, key):
		self.d.pop(key, None)


_LOCAL = MemCache()


def _cache(cache: Any = None) -> Any:
	if cache is not None:
		return cache
	try:
		import frappe

		if getattr(frappe.local, "site", None):
			return frappe.cache()
	except Exception:
		pass
	return _LOCAL


_CLAIM_LOCK = threading.Lock()


def _claim(c: Any, key: str, ttl: int) -> bool:
	"""Atomically mark ``key`` as used; True only for the first caller (Redis SET NX when available)."""
	try:
		make_key = getattr(c, "make_key", None)
		if make_key is not None and hasattr(c, "set"):
			return bool(c.set(make_key(key), 1, nx=True, ex=ttl))
	except Exception:
		pass
	with _CLAIM_LOCK:
		if c.get_value(key):
			return False
		c.set_value(key, 1, expires_in_sec=ttl)
		return True


def _sha(text: str) -> str:
	return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def action_hash(action: dict) -> str:
	return _sha(json.dumps(action, sort_keys=True, separators=(",", ":"), default=str))


# -- rate limits -------------------------------------------------------------------------------


_RL_LOCK = threading.Lock()


def check_rate(key: str, limit: int, window: int, *, cache: Any = None, now: float | None = None) -> bool:
	"""Fixed-window counter. True while under ``limit`` (the call is counted).

	Atomic via Redis INCRBY + EXPIRE when the cache exposes them; otherwise (or if Redis errors) a
	lock-guarded read-modify-write on the cache's ``get_value`` / ``set_value`` (process-local safe).
	"""
	c = _cache(cache)
	current = time.time() if now is None else now
	bucket = f"huf_tg_adm_rl:{key}:{int(current // window)}"
	try:
		make_key = getattr(c, "make_key", None)
		if make_key is not None and hasattr(c, "incrby") and hasattr(c, "expire"):
			rkey = make_key(bucket)
			count = int(c.incrby(rkey, 1))
			if count == 1:
				c.expire(rkey, window)
			return count <= limit
	except Exception:
		pass
	if not hasattr(c, "get_value"):
		c = _LOCAL
	with _RL_LOCK:
		count = int(c.get_value(bucket) or 0)
		if count >= limit:
			return False
		c.set_value(bucket, count + 1, expires_in_sec=window)
		return True


# -- nonces (two-step confirm) -----------------------------------------------------------------


def issue_nonce(
	tg_user: Any, chat_id: Any, action: dict, *, cache: Any = None, now: float | None = None, ttl: int | None = None
) -> str:
	"""Single-use nonce for ``action`` bound to telegram user + chat + action hash (``NONCE_TTL``)."""
	nonce = secrets.token_urlsafe(12)
	current = time.time() if now is None else now
	life = int(ttl or NONCE_TTL)
	_cache(cache).set_value(
		f"huf_tg_adm_n:{nonce}",
		{
			"u": str(tg_user),
			"c": str(chat_id),
			"h": action_hash(action),
			"a": action,
			"exp": current + life,
		},
		expires_in_sec=life,
	)
	return nonce


def consume_nonce(
	nonce: str, tg_user: Any, chat_id: Any, *, cache: Any = None, now: float | None = None
) -> dict:
	"""Return the bound action and burn the nonce; raise ``AdminError`` when expired/used/foreign."""
	c = _cache(cache)
	key = f"huf_tg_adm_n:{nonce}"
	record = c.get_value(key)
	current = time.time() if now is None else now
	if not isinstance(record, dict) or current >= float(record.get("exp") or 0):
		raise AdminError(MSG_EXPIRED)
	if record.get("u") != str(tg_user) or record.get("c") != str(chat_id):
		# Not burned: a foreign presser must not be able to cancel the owner's pending confirmation.
		raise AdminError(MSG_DENIED)
	action = record.get("a")
	if not isinstance(action, dict) or action_hash(action) != record.get("h"):
		raise AdminError(MSG_EXPIRED)
	if not _claim(c, f"huf_tg_adm_nu:{nonce}", NONCE_TTL):
		raise AdminError(MSG_EXPIRED)
	try:
		c.delete_value(key)
	except Exception:
		pass
	return action


# -- agent actions awaiting a human admin (op "agent_action") -----------------------------------


def agent_action_mark_pending(fp: str, *, cache: Any = None, ttl: int = 600) -> None:
	_cache(cache).set_value(f"huf_tg_adm_pend:{fp}", 1, expires_in_sec=ttl)


def agent_action_begin(fp: str, *, cache: Any = None, ttl: int = 600) -> bool:
	"""Atomically claim the right to request approval for ``fp`` and mark it pending BEFORE any button is sent.

	True only for the first concurrent caller; a loser must not send a second approval.
	"""
	c = _cache(cache)
	key = f"huf_tg_adm_pend:{fp}"
	if not _claim(c, key + ":s", ttl):
		return False
	c.set_value(key, 1, expires_in_sec=ttl)
	return True


def agent_action_clear(fp: str, *, cache: Any = None) -> None:
	"""Undo ``agent_action_begin`` (nothing was delivered)."""
	c = _cache(cache)
	key = f"huf_tg_adm_pend:{fp}"
	c.delete_value(key)
	c.delete_value(key + ":s")


def agent_action_pending(fp: str, *, cache: Any = None) -> bool:
	return bool(_cache(cache).get_value(f"huf_tg_adm_pend:{fp}"))


def agent_action_take(fp: str, *, cache: Any = None) -> bool:
	"""Resolve a pending agent action exactly once (first approve/reject press wins)."""
	c = _cache(cache)
	key = f"huf_tg_adm_pend:{fp}"
	if not _claim(c, key + ":u", 600):
		return False
	had = bool(c.get_value(key))
	c.delete_value(key)
	c.delete_value(key + ":s")
	c.delete_value(key + ":u")
	return had


def callback_payload(verb: str, nonce: str) -> str:
	"""``adm:<verb>:<nonce>``; verbs: ``p`` propose (opens a confirm), ``c`` confirm, ``x`` cancel."""
	return f"{PREFIX}{verb}:{nonce}"


def parse_callback_payload(payload: str) -> tuple[str, str] | None:
	if not isinstance(payload, str) or not payload.startswith(PREFIX):
		return None
	verb, _, nonce = payload[len(PREFIX) :].partition(":")
	if verb not in ("p", "c", "x") or not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", nonce or ""):
		return None
	return verb, nonce


# -- bind codes --------------------------------------------------------------------------------


def mint_bind_code(user: str, gateway: str, role_scope: str, *, cache: Any = None) -> str:
	"""Short-lived one-time code (10 chars, ~50 bits). Only its hash is stored."""
	if user in FORBIDDEN_USERS or not user:
		raise AdminError("Sign in as a named user to bind Telegram.")
	if role_scope not in ROLE_RANK:
		raise AdminError("Unknown role scope.")
	code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(10))
	_cache(cache).set_value(
		f"huf_tg_adm_bc:{_sha(code)}",
		{"user": user, "gateway": gateway, "role_scope": role_scope},
		expires_in_sec=BIND_CODE_TTL,
	)
	return code


def consume_bind_code(code: str, gateway: str, *, cache: Any = None) -> dict | None:
	"""Redeem a code once for ``gateway``; None when unknown/expired/used/other gateway."""
	code = str(code or "").strip().upper()
	if code.startswith(BIND_CODE_PREFIX):
		code = code[len(BIND_CODE_PREFIX) :]
	if not re.fullmatch(r"[A-Z0-9]{6,16}", code):
		return None
	c = _cache(cache)
	key = f"huf_tg_adm_bc:{_sha(code)}"
	record = c.get_value(key)
	if not isinstance(record, dict) or record.get("gateway") != gateway:
		return None
	if not _claim(c, f"huf_tg_adm_bcu:{_sha(code)}", BIND_CODE_TTL):
		return None
	try:
		c.delete_value(key)
	except Exception:
		pass
	return record


# -- Mini App session tokens -------------------------------------------------------------------


def mint_session_token(binding: dict, *, cache: Any = None, now: float | None = None) -> str:
	token = secrets.token_urlsafe(32)
	current = time.time() if now is None else now
	_cache(cache).set_value(
		f"huf_tg_adm_s:{_sha(token)}",
		{
			"binding": binding["name"],
			"frappe_user": binding["frappe_user"],
			"telegram_user_id": str(binding["telegram_user_id"]),
			"gateway": binding["gateway"],
			"role_scope": binding["role_scope"],
			"exp": current + SESSION_TTL,
		},
		expires_in_sec=SESSION_TTL,
	)
	return token


def resolve_session_token(
	token: str, *, cache: Any = None, now: float | None = None, binding_lookup=None
) -> dict | None:
	"""Session dict for a Mini App bearer token, or None (expired / binding revoked since)."""
	if not isinstance(token, str) or len(token) < 20:
		return None
	record = _cache(cache).get_value(f"huf_tg_adm_s:{_sha(token)}")
	current = time.time() if now is None else now
	if not isinstance(record, dict) or current >= float(record.get("exp") or 0):
		return None
	lookup = binding_lookup or get_binding
	binding = lookup(record["telegram_user_id"], record["gateway"])
	if not binding or binding["name"] != record["binding"] or binding["frappe_user"] != record["frappe_user"]:
		return None
	return record


# -- redaction ---------------------------------------------------------------------------------


def redact(args: Any, depth: int = 0) -> Any:
	if depth > 4:
		return "..."
	if isinstance(args, dict):
		return {
			k: ("***" if _SECRET_KEY_RE.search(str(k)) else redact(v, depth + 1))
			for k, v in list(args.items())[:30]
		}
	if isinstance(args, (list, tuple)):
		return [redact(v, depth + 1) for v in list(args)[:30]]
	if isinstance(args, str):
		return args[:200]
	return args


# -- Frappe touch points (patched in unit tests) -----------------------------------------------


def _current_user() -> str:
	import frappe

	return frappe.session.user


def _set_user(user: str) -> None:
	import frappe

	frappe.set_user(user)


def _user_enabled(user: str) -> bool:
	import frappe

	return bool(frappe.db.get_value("User", user, "enabled"))


def _log_restore_failure(user: str, previous: str) -> None:
	try:
		import frappe

		frappe.log_error(
			title="Telegram admin: failed to restore user",
			message=f"run_as({user!r}) could not restore {previous!r}",
		)
	except Exception:
		logging.getLogger(__name__).exception("telegram admin: failed to restore user %s", previous)


@contextmanager
def run_as(user: str):
	"""Execute the body as ``user`` under normal permission checks; always restores the previous user.

	If restoring fails it is logged and re-raised as AdminError (never silently leaving the bound user
	active); a last-resort drop to Guest is attempted first.
	"""
	if not user or user in FORBIDDEN_USERS:
		raise AdminError(MSG_DENIED)
	if not _user_enabled(user):
		raise AdminError("The bound Frappe user is disabled.")
	previous = _current_user() or "Guest"
	_set_user(user)
	body_exc: BaseException | None = None
	try:
		yield user
	except BaseException as exc:
		body_exc = exc
		raise
	finally:
		try:
			_set_user(previous)
		except Exception as exc:
			_log_restore_failure(user, previous)
			if body_exc is not None:
				logging.getLogger(__name__).error("telegram admin: body failed before restore failure: %r", body_exc)
			try:
				_set_user("Guest")
			except Exception:
				pass
			raise AdminError("Could not restore the previous session user; request aborted.") from (
				body_exc or exc
			)


_ADMIN_RECHECK_TTL = 60
_AUDIT_ONCE_TTL = 3600


def _live_scope(row: dict, cache: Any = None) -> str:
	"""Re-validate a bound Admin: 'Admin' | 'Operator' (no longer gateway admin) | '' (user disabled)."""
	c = _cache(cache)
	user = row["frappe_user"]
	ckey = f"huf_tg_adm_live:{row['name']}:{user}"
	hit = c.get_value(ckey)
	if hit is not None:
		return hit if hit != "-" else ""
	verdict = "Admin"
	if not _user_enabled(user):
		verdict = ""
	else:
		try:
			from huf.permissions import is_gateway_admin

			if not is_gateway_admin(user):
				verdict = "Operator"
		except Exception:
			verdict = "Operator"  # fail closed
	c.set_value(ckey, verdict or "-", expires_in_sec=_ADMIN_RECHECK_TTL)
	if verdict != "Admin" and _claim(c, f"huf_tg_adm_dem:{row['name']}:{verdict or 'off'}", _AUDIT_ONCE_TTL):
		try:
			write_audit(
				row,
				{"op": "scope_recheck", "was": "Admin", "now": verdict or "inactive"},
				"scope_downgraded" if verdict else "user_disabled",
			)
			_commit()
		except Exception:
			pass
	return verdict


def get_binding(tg_user: Any, gateway: str, *, cache: Any = None) -> dict | None:
	"""Active binding row for this Telegram user on this gateway (system lookup).

	Admin scope is re-validated against the live Frappe user (cached <= 60s).
	"""
	import frappe

	row = frappe.db.get_value(
		"Telegram Admin Binding",
		{"telegram_user_id": str(tg_user), "gateway": gateway, "is_active": 1},
		["name", "telegram_user_id", "frappe_user", "gateway", "role_scope", "chat_id"],
		as_dict=True,
	)
	if not row or row.frappe_user in FORBIDDEN_USERS:
		return None
	row = dict(row)
	if row.get("role_scope") == "Admin":
		live = _live_scope(row, cache)
		if not live:
			return None
		row["role_scope"] = live
	return row


def _touch_binding(name: str) -> None:
	try:
		import frappe

		frappe.db.set_value(
			"Telegram Admin Binding", name, "last_seen_at", frappe.utils.now_datetime(), update_modified=False
		)
	except Exception:
		pass


def write_audit(
	binding: dict, action: dict, result: str, *, detail: str = "", nonce: str = "", ip: str = ""
) -> None:
	"""Insert one append-only audit row (system bookkeeping, not a user-scoped business write)."""
	import frappe

	frappe.get_doc(
		{
			"doctype": "Telegram Admin Audit",
			"telegram_user_id": str(binding.get("telegram_user_id") or ""),
			"frappe_user": binding.get("frappe_user"),
			"gateway": binding.get("gateway"),
			"action": str(action.get("op") or "")[:140],
			"reference_doctype": action.get("dt") or None,
			"reference_name": action.get("dn") or None,
			"arguments_json": json.dumps(redact(action), default=str)[:2000],
			"result": result[:140],
			"detail": detail[:1000],
			"confirmed_by_nonce": _sha(nonce)[:32] if nonce else "",
			"ip_address": ip,
			"ts": frappe.utils.now_datetime(),
		}
	).insert(ignore_permissions=True)


def _safe_error(exc: BaseException) -> str:
	text = str(exc) or exc.__class__.__name__
	try:
		from huf.ai.gateway_service import _redact_error_text

		text = _redact_error_text(text)
	except Exception:
		pass
	return re.sub(r"<[^>]+>", "", text)[:300]


# -- replies -----------------------------------------------------------------------------------


@dataclass
class Reply:
	text: str
	# rows of (label, verb, action); signed into callback_data when sent
	buttons: list[list[tuple[str, str, dict]]] = field(default_factory=list)
	links: list[tuple[str, str]] = field(default_factory=list)  # (label, url) or ("web_app:"+label, url)


@dataclass
class Ctx:
	binding: dict
	tg_user: str
	chat_id: str
	gateway: str
	cache: Any = None
	now: float | None = None


def _rank(binding: dict) -> int:
	return ROLE_RANK.get(binding.get("role_scope") or "", 0)


def _check_doctype(dt: str) -> str:
	import frappe

	dt = (dt or "").strip()
	if not dt or dt in DENY_DOCTYPES:
		raise AdminError("That DocType is not available here.")
	meta = frappe.get_meta(dt)  # raises DoesNotExistError
	if meta.istable or meta.issingle:
		raise AdminError("That DocType is not available here.")
	return dt


def _resolve_doctype(text: str) -> tuple[str, str]:
	"""Split ``<doctype> <rest>`` where the doctype may contain spaces (longest existing prefix wins)."""
	import frappe

	words = (text or "").split()
	for n in range(min(len(words), 5), 0, -1):
		candidate = " ".join(words[:n])
		if frappe.db.exists("DocType", candidate):
			return candidate, " ".join(words[n:])
		titled = candidate.title()
		if titled != candidate and frappe.db.exists("DocType", titled):
			return titled, " ".join(words[n:])
	raise AdminError("Unknown DocType. Usage: /find <doctype> <text>")


def _desk_url(dt: str, dn: str) -> str:
	import frappe
	from frappe.utils import get_url

	return get_url(f"/app/{frappe.scrub(dt).replace('_', '-')}/{dn}")


# -- commands ----------------------------------------------------------------------------------

HELP = (
	"Admin cockpit\n"
	"/me - who you are bound as\n"
	"/find <doctype> <text> - search records you can read\n"
	"/open <doctype> <name> - summary of one record\n"
	"/approvals - workflow items waiting for you\n"
	"/digest - today's summary\n"
	"/audit - recent cockpit actions (Admin scope)\n"
	"/unbind - unlink this Telegram account\n"
	"Anything else you type goes to your assistant agent."
)


def cmd_help(ctx: Ctx, args: str) -> Reply:
	return Reply(HELP)


def cmd_me(ctx: Ctx, args: str) -> Reply:
	import frappe

	full_name = frappe.utils.get_fullname(ctx.binding["frappe_user"])
	reply = Reply(
		f"Bound as {full_name} ({ctx.binding['frappe_user']})\nScope: {ctx.binding['role_scope']}\n"
		f"Gateway: {ctx.gateway}"
	)
	url = miniapp_launch_url(ctx.binding)
	if url:
		reply.links.append(("web_app:Open console", url))
	return reply


def cmd_find(ctx: Ctx, args: str) -> Reply:
	import frappe

	dt, text = _resolve_doctype(args)
	dt = _check_doctype(dt)
	meta = frappe.get_meta(dt)
	title_field = meta.title_field if meta.title_field and meta.has_field(meta.title_field) else None
	fields = ["name"] + ([title_field] if title_field else [])
	or_filters = None
	if text:
		like = f"%{text}%"
		or_filters = [[dt, "name", "like", like]] + ([[dt, title_field, "like", like]] if title_field else [])
	rows = frappe.get_list(
		dt, fields=fields, or_filters=or_filters, limit_page_length=LIST_LIMIT, order_by="modified desc"
	)
	if not rows:
		return Reply(f"No {dt} found.")
	lines = [f"{dt} ({len(rows)})"]
	for r in rows:
		title = r.get(title_field) if title_field else ""
		lines.append(f"- {r['name']}" + (f"  {title}" if title and title != r["name"] else ""))
	lines.append("Use /open " + dt + " <name>")
	return Reply("\n".join(lines))


def _transitions(doc) -> list[str]:
	try:
		from frappe.model.workflow import get_transitions

		return [t.get("action") for t in get_transitions(doc) if t.get("action")]
	except Exception:
		return []


def _transition_buttons(ctx: Ctx, dt: str, dn: str, actions: list[str]) -> list[list[tuple[str, str, dict]]]:
	if _rank(ctx.binding) < ROLE_RANK["Operator"] or not actions:
		return []
	return [[(a[:30], "p", {"op": "workflow", "dt": dt, "dn": dn, "transition": a}) for a in actions[:4]]]


def cmd_open(ctx: Ctx, args: str) -> Reply:
	import frappe

	dt, dn = _resolve_doctype(args)
	dt = _check_doctype(dt)
	dn = dn.strip()
	if not dn:
		raise AdminError("Usage: /open <doctype> <name>")
	doc = frappe.get_doc(dt, dn)
	doc.check_permission("read")
	meta = frappe.get_meta(dt)
	lines = [f"{dt} {doc.name}"]
	title = doc.get(meta.title_field) if meta.title_field else None
	if title and title != doc.name:
		lines.append(str(title))
	workflow = meta.get_workflow()
	state_field = frappe.get_cached_value("Workflow", workflow, "workflow_state_field") if workflow else None
	docstatus = (
		{0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(doc.docstatus) if meta.is_submittable else None
	)
	for label, value in (
		("Workflow state", doc.get(state_field) if state_field else None),
		("Status", doc.get("status")),
		("Docstatus", docstatus),
	):
		if value:
			lines.append(f"{label}: {value}")
	shown = 0
	for df in meta.fields:
		if shown >= 8:
			break
		if not df.in_list_view or df.fieldtype in (
			"Password",
			"Attach",
			"Attach Image",
			"Table",
			"Table MultiSelect",
		):
			continue
		if df.permlevel:  # higher permlevels are never echoed to chat
			continue
		value = doc.get(df.fieldname)
		if value not in (None, ""):
			lines.append(f"{df.label or df.fieldname}: {str(value)[:80]}")
			shown += 1
	lines.append(f"Modified: {doc.modified}")
	reply = Reply("\n".join(lines), links=[("Open in Desk", _desk_url(dt, doc.name))])
	reply.buttons = _transition_buttons(ctx, dt, doc.name, _transitions(doc))
	return reply


def pending_approvals(limit: int = LIST_LIMIT) -> list[dict]:
	"""Open Workflow Actions visible to the current (bound) user under Frappe permissions."""
	import frappe

	return frappe.get_list(
		"Workflow Action",
		filters={"status": "Open"},
		fields=["name", "reference_doctype", "reference_name", "workflow_state"],
		limit_page_length=limit,
		order_by="creation desc",
	)


def cmd_approvals(ctx: Ctx, args: str) -> Reply:
	import frappe

	rows = pending_approvals()
	if not rows:
		return Reply("Nothing is waiting for your approval.")
	lines = [f"Waiting for you ({len(rows)})"]
	buttons: list[list[tuple[str, str, dict]]] = []
	for r in rows:
		dt, dn = r["reference_doctype"], r["reference_name"]
		lines.append(f"- {dt} {dn} [{r.get('workflow_state') or ''}]")
		if len(buttons) < 5 and _rank(ctx.binding) >= ROLE_RANK["Operator"] and dt not in DENY_DOCTYPES:
			try:
				doc = frappe.get_doc(dt, dn)
				doc.check_permission("read")
				row = _transition_buttons(ctx, dt, dn, _transitions(doc))
				if row:
					buttons.append([(f"{label} {dn}"[:40], verb, act) for label, verb, act in row[0][:2]])
			except Exception:
				continue
	return Reply("\n".join(lines), buttons=buttons)


def collect_digest(binding: dict, *, now_dt: Any = None) -> dict:
	"""Digest data for the CURRENT (bound) user: pending approvals and today's cockpit actions."""
	import frappe

	since = frappe.utils.add_days(now_dt or frappe.utils.now_datetime(), -1)
	approvals = pending_approvals(limit=50)
	actions = frappe.db.count(
		"Telegram Admin Audit", {"frappe_user": binding["frappe_user"], "creation": (">=", since)}
	)
	return {"user": binding["frappe_user"], "approvals": approvals, "actions_24h": actions}


def compose_digest(data: dict) -> str:
	"""Pure: digest text from ``collect_digest`` data."""
	approvals = list(data.get("approvals") or [])
	lines = ["Daily digest", f"Pending approvals: {len(approvals)}"]
	for r in approvals[:5]:
		lines.append(
			f"- {r.get('reference_doctype')} {r.get('reference_name')} [{r.get('workflow_state') or ''}]"
		)
	if len(approvals) > 5:
		lines.append(f"... and {len(approvals) - 5} more (/approvals)")
	lines.append(f"Cockpit actions in the last 24h: {int(data.get('actions_24h') or 0)}")
	return "\n".join(lines)


def cmd_digest(ctx: Ctx, args: str) -> Reply:
	return Reply(compose_digest(collect_digest(ctx.binding)))


def cmd_audit(ctx: Ctx, args: str) -> Reply:
	import frappe

	if _rank(ctx.binding) < ROLE_RANK["Admin"]:
		raise AdminError("Admin scope required.")
	rows = frappe.get_list(  # Audit read is permission-checked (System Manager / Huf Manager only).
		"Telegram Admin Audit",
		fields=["action", "frappe_user", "reference_doctype", "reference_name", "result", "creation"],
		limit_page_length=LIST_LIMIT,
		order_by="creation desc",
	)
	if not rows:
		return Reply("No cockpit actions recorded.")
	return Reply(
		"\n".join(
			["Recent cockpit actions"]
			+ [
				f"- {r['creation']:%m-%d %H:%M} {r['frappe_user']} {r['action']} "
				f"{r.get('reference_doctype') or ''} {r.get('reference_name') or ''} -> {r['result']}"
				for r in rows
			]
		)
	)


def cmd_unbind(ctx: Ctx, args: str) -> Reply:
	return propose(ctx, {"op": "unbind", "binding": ctx.binding["name"]})


COMMANDS: dict[str, tuple[str, Callable[[Ctx, str], Reply]]] = {
	"help": ("Viewer", cmd_help),
	"me": ("Viewer", cmd_me),
	"find": ("Viewer", cmd_find),
	"open": ("Viewer", cmd_open),
	"approvals": ("Viewer", cmd_approvals),
	"digest": ("Viewer", cmd_digest),
	"audit": ("Admin", cmd_audit),
	"unbind": ("Viewer", cmd_unbind),
}


# -- two-step state changes --------------------------------------------------------------------


def describe(action: dict) -> str:
	op = action.get("op")
	if op == "workflow":
		return f"Apply '{action['transition']}' to {action['dt']} {action['dn']}"
	if op == "unbind":
		return "Unlink this Telegram account from your Frappe user"
	if op == "agent_action":
		bits = json.dumps(redact(action.get("args") or {}), default=str)[:300]
		return f"Agent action '{action.get('action')}' in chat {action.get('chat') or '(bot-wide)'} with {bits}"
	raise AdminError("Unknown action.")


def propose(ctx: Ctx, action: dict) -> Reply:
	"""Step 1: show what will happen + Confirm/Cancel bound to a fresh single-use nonce."""
	if action.get("op") == "workflow" and _rank(ctx.binding) < ROLE_RANK["Operator"]:
		raise AdminError("Operator scope required.")
	text = describe(action) + "?\nConfirm within 5 minutes."
	return Reply(text, buttons=[[("Confirm", "c", action), ("Cancel", "x", action)]])


def execute(ctx: Ctx, action: dict, nonce: str, *, ip: str = "") -> str:
	"""Step 2: run the confirmed action AS the bound user and audit it. Returns the result text."""
	op = action.get("op")
	if op == "workflow" and _rank(ctx.binding) < ROLE_RANK["Operator"]:
		raise AdminError("Operator scope required.")
	try:
		if op == "workflow":
			import frappe
			from frappe.model.workflow import apply_workflow

			if action.get("dt") in DENY_DOCTYPES:
				raise AdminError("That DocType is not available here.")
			with run_as(ctx.binding["frappe_user"]):
				doc = frappe.get_doc(action["dt"], action["dn"])
				doc.check_permission("read")
				doc = apply_workflow(doc, action["transition"])
				frappe.db.commit()
				state = doc.get("workflow_state") or doc.get("status") or ""
			result_text = f"Done: {action['dt']} {action['dn']} is now {state}".strip()
		elif op == "agent_action":
			if _rank(ctx.binding) < ROLE_RANK["Admin"] or action.get("gateway") != ctx.binding.get("gateway"):
				raise AdminError(MSG_DENIED)
			if not agent_action_take(action.get("fp") or "", cache=ctx.cache):
				raise AdminError(MSG_EXPIRED)
			from huf.ai.tools import telegram_admin_tools

			result_text = telegram_admin_tools.execute_approved(action)
		elif op == "unbind":
			import frappe

			if action.get("binding") != ctx.binding["name"]:
				raise AdminError(MSG_DENIED)
			frappe.db.set_value("Telegram Admin Binding", ctx.binding["name"], "is_active", 0)
			result_text = "Unbound. Bind again from Huf with a new code."
		else:
			raise AdminError("Unknown action.")
	except Exception as exc:
		_rollback()
		write_audit(ctx.binding, action, "error", detail=_safe_error(exc), nonce=nonce, ip=ip)
		_commit()
		if isinstance(exc, AdminError):
			raise
		raise AdminError(f"Failed: {_safe_error(exc)}") from exc
	write_audit(ctx.binding, action, "ok", detail=result_text, nonce=nonce, ip=ip)
	_commit()
	return result_text


def _commit() -> None:
	try:
		import frappe

		frappe.db.commit()
	except Exception:
		pass


def _rollback() -> None:
	try:
		import frappe

		frappe.db.rollback()
	except Exception:
		pass


# -- rendering / sending -----------------------------------------------------------------------


def render_markup(reply: Reply, ctx: Ctx, sign: Callable[[str], str]) -> dict | None:
	"""Inline keyboard: every action button gets its own single-use nonce, then the payload is signed."""
	from huf.ai.gateway_adapters import telegram_keyboards as kb

	rows = []
	for row in reply.buttons:
		out = []
		for label, verb, action in row:
			nonce = issue_nonce(ctx.tg_user, ctx.chat_id, action, cache=ctx.cache, now=ctx.now)
			out.append(kb.callback_button(label, sign(callback_payload(verb, nonce))))
		rows.append(out)
	for label, url in reply.links:
		if label.startswith("web_app:"):
			rows.append([kb.web_app_button(label[len("web_app:") :], url)])
		elif url.startswith(("https://", "http://")):
			rows.append([kb.url_button(label, url)])
	return kb.inline_keyboard(rows) if rows else None


def _send(adapter: Any, ctx: Ctx, reply: Reply) -> None:
	markup = render_markup(reply, ctx, lambda p: adapter.sign_callback_data(p, ctx.chat_id))
	adapter.sender.send_text(ctx.chat_id, reply.text, markup=markup, link_preview=False)


def _ack(note: str) -> dict:
	return {"success": True, "ignored": "telegram_admin", "note": note}


# -- update handlers ---------------------------------------------------------------------------


def handle_message(
	gateway, adapter, parsed, request=None, *, cache: Any = None, now: float | None = None
) -> dict | None:
	"""Intercept bind codes and cockpit slash commands in private chats; None = not ours (fall through)."""
	# Private-chat, human, bound-only: refuse everything else before any binding lookup (no existence leak).
	if (
		parsed.kind != "message"
		or parsed.chat_type != "private"
		or parsed.is_bot
		or not parsed.sender_id
		or getattr(parsed, "is_channel", False)
		or getattr(parsed, "business_connection_id", "")
		or getattr(parsed, "sender_business_bot", "")
	):
		return None
	tg_user, chat_id = str(parsed.sender_id), str(parsed.chat_id)
	payload = str(parsed.start_payload or "")
	if parsed.command == "start" and payload.upper().startswith(BIND_CODE_PREFIX):
		return _handle_bind(gateway, adapter, parsed, payload, cache=cache, now=now)
	if parsed.command not in COMMANDS:
		return None
	binding = get_binding(tg_user, gateway.name, cache=cache)
	if not binding:
		return None  # unbound users never see the cockpit; the command goes to normal routing
	ctx = Ctx(binding=binding, tg_user=tg_user, chat_id=chat_id, gateway=gateway.name, cache=cache, now=now)
	if not check_rate(f"u:{tg_user}", RATE_LIMIT, RATE_WINDOW, cache=cache, now=now):
		adapter.sender.send_text(chat_id, "Slow down: too many requests. Try again in a minute.")
		return _ack("rate_limited")
	min_role, fn = COMMANDS[parsed.command]
	args = (parsed.text or "").split(None, 1)[1] if len((parsed.text or "").split(None, 1)) > 1 else ""
	_touch_binding(binding["name"])
	try:
		if _rank(binding) < ROLE_RANK[min_role]:
			raise AdminError(f"{min_role} scope required.")
		if parsed.command in ("unbind",):
			reply = fn(ctx, args)
		else:
			with run_as(binding["frappe_user"]):
				reply = fn(ctx, args)
	except AdminError as exc:
		reply = Reply(str(exc))
	except Exception as exc:
		reply = Reply(_permission_text(exc))
	_send(adapter, ctx, reply)
	return _ack(f"command:{parsed.command}")


def _permission_text(exc: BaseException) -> str:
	try:
		import frappe

		if isinstance(exc, frappe.PermissionError):
			return "You do not have permission for that."
		if isinstance(exc, frappe.DoesNotExistError):
			return "Not found."
	except Exception:
		pass
	return f"Error: {_safe_error(exc)}"


def _handle_bind(
	gateway, adapter, parsed, payload: str, *, cache: Any = None, now: float | None = None
) -> dict:
	tg_user, chat_id = str(parsed.sender_id), str(parsed.chat_id)
	if not check_rate(f"bind:{tg_user}", BIND_ATTEMPT_LIMIT, BIND_ATTEMPT_WINDOW, cache=cache, now=now):
		adapter.sender.send_text(chat_id, "Too many bind attempts. Try again later.")
		return _ack("bind_rate_limited")
	record = consume_bind_code(payload, gateway.name, cache=cache)
	if not record:
		adapter.sender.send_text(chat_id, "That bind code is invalid or expired. Create a new one in Huf.")
		return _ack("bind_invalid")
	try:
		binding = create_binding(record, tg_user, chat_id, parsed.display_name)
	except AdminError as exc:
		adapter.sender.send_text(chat_id, str(exc))
		return _ack("bind_refused")
	write_audit(binding, {"op": "bind", "role_scope": binding["role_scope"]}, "ok")
	_commit()
	adapter.sender.send_text(
		chat_id, f"Bound to {binding['frappe_user']} ({binding['role_scope']}). Send /help to see commands."
	)
	return _ack("bound")


def create_binding(record: dict, tg_user: str, chat_id: str, display_name: str = "") -> dict:
	"""Create (or replace an inactive) binding from a redeemed code record. System write."""
	import frappe

	user = record["user"]
	if user in FORBIDDEN_USERS or not _user_enabled(user):
		raise AdminError("That Frappe user cannot be bound.")
	existing = frappe.db.get_value(
		"Telegram Admin Binding",
		{"telegram_user_id": tg_user},
		["name", "is_active", "frappe_user"],
		as_dict=True,
	)
	if existing:
		if existing.is_active and existing.frappe_user != user:
			raise AdminError("This Telegram account is already bound to another user. /unbind first.")
		frappe.delete_doc("Telegram Admin Binding", existing.name, ignore_permissions=True, force=True)
	doc = frappe.get_doc(
		{
			"doctype": "Telegram Admin Binding",
			"telegram_user_id": tg_user,
			"frappe_user": user,
			"gateway": record["gateway"],
			"role_scope": record["role_scope"],
			"is_active": 1,
			"telegram_username": (display_name or "")[:140],
			"chat_id": chat_id,
			"paired_at": frappe.utils.now_datetime(),
		}
	).insert(ignore_permissions=True)
	return {
		"name": doc.name,
		"telegram_user_id": tg_user,
		"frappe_user": user,
		"gateway": record["gateway"],
		"role_scope": record["role_scope"],
		"chat_id": chat_id,
	}


def handle_callback(
	gateway, adapter, parsed, request=None, *, cache: Any = None, now: float | None = None
) -> dict | None:
	"""Handle signed ``adm:`` button presses; None for foreign (non-admin) callbacks."""
	if parsed.kind != "callback_query":
		return None
	raw_data = str(parsed.callback_data or "")
	if not raw_data.startswith(PREFIX):
		return None
	cqid = parsed.callback_query_id

	def answer(text: str = "") -> None:
		try:
			if cqid:
				adapter.sender.answer_callback_query(cqid, text)
		except Exception:
			pass

	payload = adapter.verify_callback_data(raw_data, parsed.chat_id)
	parsed_payload = parse_callback_payload(payload) if payload else None
	if parsed_payload is None:
		answer(MSG_DENIED)
		return _ack("forged_callback")
	if parsed.chat_type != "private":
		answer(MSG_DENIED)
		return _ack("not_private")
	tg_user, chat_id = str(parsed.sender_id), str(parsed.chat_id)
	binding = get_binding(tg_user, gateway.name, cache=cache)
	if not binding:
		answer(MSG_DENIED)
		return _ack("no_binding")
	if not check_rate(f"u:{tg_user}", RATE_LIMIT, RATE_WINDOW, cache=cache, now=now):
		answer("Slow down.")
		return _ack("rate_limited")
	ctx = Ctx(binding=binding, tg_user=tg_user, chat_id=chat_id, gateway=gateway.name, cache=cache, now=now)
	verb, nonce = parsed_payload
	try:
		action = consume_nonce(nonce, tg_user, chat_id, cache=cache, now=now)
	except AdminError as exc:
		answer(str(exc))
		return _ack("nonce_rejected")
	answer()
	message_id = parsed.message_id
	try:
		if verb == "p":
			_send(adapter, ctx, propose(ctx, action))
			return _ack("proposed")
		if verb == "x":
			text = "Cancelled."
			if action.get("op") == "agent_action" and _rank(binding) >= ROLE_RANK["Admin"]:
				if agent_action_take(action.get("fp") or "", cache=cache):
					write_audit(binding, action, "rejected", nonce=nonce)
					_commit()
		else:
			text = execute(ctx, action, nonce)
	except AdminError as exc:
		text = str(exc)
	try:
		adapter.sender.edit_message_text(chat_id, message_id, text, markup={"inline_keyboard": []})
	except Exception:
		adapter.sender.send_text(chat_id, text)
	return _ack("confirmed" if verb == "c" else "cancelled")


# -- Mini App ----------------------------------------------------------------------------------


def miniapp_launch_url(binding: dict) -> str:
	"""HTTPS launch URL for the admin Mini App (no secrets in the URL; auth is initData only)."""
	try:
		import frappe
		from frappe.utils import get_url

		base = (frappe.conf.get("huf_telegram_admin_miniapp_url") or get_url("/huf/telegram-admin")).strip()
	except Exception:
		return ""
	if not base.startswith("https://"):
		return ""  # Telegram only opens https web apps
	sep = "&" if "?" in base else "?"
	from urllib.parse import quote

	return f"{base}{sep}gw={quote(str(binding.get('gateway') or ''), safe='')}"


def _client_ip() -> str:
	try:
		import frappe

		return str(getattr(frappe.local, "request_ip", "") or "")
	except Exception:
		return ""


def miniapp_auth(
	init_data: str,
	gateway: str,
	*,
	bot_token: str,
	cache: Any = None,
	now: float | None = None,
	binding_lookup=None,
) -> dict:
	"""Pure core of the Mini App auth endpoint. Raises ``AdminError`` with one generic message."""
	from huf.ai.gateway_adapters.telegram_miniapp import MiniAppAuthError, validate_init_data

	try:
		user = validate_init_data(init_data, bot_token, max_age_seconds=MINIAPP_MAX_AGE, now=now)
	except MiniAppAuthError:
		raise AdminError("Mini App authentication failed.") from None
	binding = (binding_lookup or get_binding)(str(user.user_id), gateway)
	if not binding:
		raise AdminError("Mini App authentication failed.")
	token = mint_session_token(binding, cache=cache, now=now)
	return {
		"token": token,
		"expires_in": SESSION_TTL,
		"role_scope": binding["role_scope"],
		"gateway": gateway,
	}


# -- whitelisted endpoints ---------------------------------------------------------------------


def _whitelist(**kw):
	try:
		import frappe

		return frappe.whitelist(**kw)
	except Exception:  # pragma: no cover - frappe always importable on a bench
		return lambda fn: fn


@_whitelist(methods=["POST"])
def create_binding_code(gateway: str, role_scope: str = "Viewer") -> dict:
	"""Mint a one-time bind code for the signed-in user. Admin scope needs gateway-admin rights."""
	import frappe
	from frappe import _

	from huf.permissions import is_gateway_admin

	user = frappe.session.user
	if user in FORBIDDEN_USERS:
		frappe.throw(_("Sign in as a named user to bind Telegram."), frappe.PermissionError)
	if frappe.db.get_value("Gateway", gateway, "provider") != "Telegram":
		frappe.throw(_("Not a Telegram gateway."), frappe.ValidationError)
	if role_scope not in ROLE_RANK:
		frappe.throw(_("Unknown role scope."), frappe.ValidationError)
	if role_scope == "Admin" and not is_gateway_admin(user):
		frappe.throw(_("Admin scope requires gateway admin rights."), frappe.PermissionError)
	if not check_rate(f"mint:{user}", MINT_LIMIT, MINT_WINDOW):
		frappe.throw(_("Too many bind codes requested. Try again later."), frappe.RateLimitExceededError)
	code = mint_bind_code(user, gateway, role_scope)
	return {
		"code": f"{BIND_CODE_PREFIX}{code}",
		"expires_in": BIND_CODE_TTL,
		"instructions": f"Open the bot in a private chat and send: /start {BIND_CODE_PREFIX}{code}",
	}


@_whitelist(methods=["POST"])
def revoke_binding(name: str) -> dict:
	"""Deactivate a binding: its own Frappe user or a gateway admin."""
	import frappe
	from frappe import _

	from huf.permissions import is_gateway_admin

	user = frappe.session.user
	owner = frappe.db.get_value("Telegram Admin Binding", name, "frappe_user")
	if not owner or (owner != user and not is_gateway_admin(user)):
		frappe.throw(_("Not permitted."), frappe.PermissionError)
	frappe.db.set_value("Telegram Admin Binding", name, "is_active", 0)
	binding = {
		"telegram_user_id": frappe.db.get_value("Telegram Admin Binding", name, "telegram_user_id"),
		"frappe_user": owner,
		"gateway": frappe.db.get_value("Telegram Admin Binding", name, "gateway"),
	}
	write_audit(binding, {"op": "revoke", "by": user}, "ok", ip=_client_ip())
	return {"ok": True}


@_whitelist(allow_guest=True, methods=["POST"])
def telegram_miniapp_auth(init_data: str, gateway: str) -> dict:
	"""Exchange Mini App initData for a short-lived cockpit token (only when a binding exists).

	No Frappe session/cookie is issued. Future Mini App endpoints accept the token, call
	``resolve_session_token`` and run ``with run_as(session["frappe_user"])``.
	"""
	import frappe
	from frappe import _

	from huf.ai.gateway_webhook import _gateway_credentials

	if not check_rate(f"ma:{_client_ip()}", MINIAPP_AUTH_LIMIT, RATE_WINDOW):
		frappe.throw(_("Too many requests."), frappe.RateLimitExceededError)
	generic = _("Mini App authentication failed.")
	if not isinstance(gateway, str) or not frappe.db.exists(
		"Gateway", {"name": gateway, "provider": "Telegram"}
	):
		frappe.throw(generic, frappe.AuthenticationError)
	token = (_gateway_credentials(frappe.get_doc("Gateway", gateway)).get("token") or "").strip()
	try:
		return miniapp_auth(init_data, gateway, bot_token=token)
	except AdminError:
		frappe.throw(generic, frappe.AuthenticationError)


# -- scheduler ---------------------------------------------------------------------------------


def send_daily_digests() -> dict:
	"""Daily job (hooks.py ``scheduler_events.daily``): send each active binding its digest as that user."""
	import frappe

	from huf.ai.gateway_webhook import get_gateway_adapter

	sent, failed = 0, 0
	bindings = frappe.get_all(
		"Telegram Admin Binding",
		filters={"is_active": 1},
		fields=["name", "telegram_user_id", "frappe_user", "gateway", "role_scope", "chat_id"],
	)
	adapters: dict[str, Any] = {}
	for b in bindings:
		if not b.chat_id or b.frappe_user in FORBIDDEN_USERS:
			continue
		try:
			with run_as(b.frappe_user):
				text = compose_digest(collect_digest(dict(b)))
			if b.gateway not in adapters:
				adapters[b.gateway] = get_gateway_adapter(frappe.get_doc("Gateway", b.gateway))
			adapters[b.gateway].sender.send_text(b.chat_id, text, link_preview=False)
			sent += 1
		except Exception as exc:
			failed += 1
			frappe.logger("huf").warning(f"Telegram admin digest failed for {b.name}: {_safe_error(exc)}")
	return {"sent": sent, "failed": failed}
