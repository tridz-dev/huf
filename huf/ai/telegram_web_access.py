# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram web access: exchange signed Mini App initData for a real Frappe session (one tap).

Telegram (HMAC-signed ``initData``) plus an active Telegram Admin Binding is the only trusted
authentication source. Every failure is the same HTTP 403 "Not authorized"; the reason lives only in
the log (reason code + short hash digest, never initData or the sid) and in the audit row.
What the session may then do is enforced elsewhere (``telegram_web_access_enforce``).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.telegram_admin import _claim, _client_ip, check_rate, get_binding, write_audit
from huf.ai.telegram_web_access_paths import (
	MARKER_KEY,
	PRIVILEGED_ROLES,
	normalize_target,
	parse_prefixes,
	target_allowed,
)

MAX_AGE_SECONDS = 120
REPLAY_TTL = MAX_AGE_SECONDS + 60  # max age + future skew
USER_RATE_LIMIT = 10
USER_RATE_WINDOW = 60
IP_RATE_LIMIT = 30
IP_RATE_WINDOW = 60
DEFAULT_SESSION_HOURS = 24
MARKER_VERSION = 1
MAX_SESSION_HOURS = 720
ALWAYS_REFUSED_USERS = ("Administrator", "Guest")


class WebAccessDenied(Exception):
	"""Internal: carries the reason code. Never shown to the caller."""

	def __init__(self, code: str):
		super().__init__(code)
		self.code = code


# -- target validation -------------------------------------------------------------------------


def allowed_prefixes(gateway_doc: Any) -> list[str]:
	"""Normalized, de-duplicated route prefixes from ``telegram_web_allowed_paths`` ("/" is not allowed)."""
	raw = gateway_doc.get("telegram_web_allowed_paths") if gateway_doc is not None else ""
	return parse_prefixes(raw, keep_case=True)


def resolve_target(to: Any, gateway_doc: Any) -> str:
	prefixes = allowed_prefixes(gateway_doc)
	if not prefixes:
		raise WebAccessDenied("no_allowed_paths")
	if to is None or (isinstance(to, str) and not to.strip()):
		return prefixes[0]
	target = normalize_target(to)
	if not target:
		raise WebAccessDenied("bad_target")
	if not target_allowed(target, prefixes):
		raise WebAccessDenied("target_not_allowed")
	return target


# -- session marker ----------------------------------------------------------------------------


def session_marker(session_data: Any) -> dict | None:
	"""The ``tg_origin`` marker of a session, or None. Accepts the inner session dict or the outer one."""
	if not session_data:
		return None
	try:
		inner = session_data.get("data") if "data" in session_data else session_data
		marker = (inner or {}).get(MARKER_KEY)
	except Exception:
		return None
	if isinstance(marker, dict) and marker.get("web_access_version") == MARKER_VERSION:
		return marker
	return None


def is_tg_session() -> bool:
	"""True when the current request is authenticated by a Telegram-origin session."""
	try:
		if frappe.session.user in ("Guest", None):
			return False
		return session_marker(frappe.session.data) is not None
	except Exception:
		return False


# -- helpers -----------------------------------------------------------------------------------


def _digest(init_data: str) -> str:
	h = ""
	try:
		from urllib.parse import parse_qsl

		h = dict(parse_qsl(init_data or "")).get("hash", "")
	except Exception:
		pass
	return hashlib.sha256((h or str(init_data or "")).encode("utf-8")).hexdigest()[:12]


def _log(code: str, digest: str, tg_id: str, binding: str, outcome: str) -> None:
	try:
		frappe.logger("huf").info(
			f"telegram_web_access outcome={outcome} reason={code} h={digest} tg={tg_id or '-'} "
			f"binding={binding or '-'}"
		)
	except Exception:
		pass


def _audit(binding: dict | None, tg_id: str, gateway: str, code: str, outcome: str) -> None:
	"""Best effort; committed immediately so a following throw does not roll it back."""
	try:
		b = dict(binding or {})
		b.setdefault("telegram_user_id", tg_id)
		b.setdefault("gateway", gateway)
		write_audit(
			b, {"op": "web_login"}, outcome if outcome == "ok" else "denied", detail=code, ip=_client_ip()
		)
		frappe.db.commit()
	except Exception:
		pass


def _effective_scheme() -> str:
	"""``request.scheme`` is the only per-request signal: Frappe applies X-Forwarded-Proto itself (ProxyFix)
	only when the bench runs with proxy handling, so a client-supplied header is never trusted here. Behind a
	TLS-terminating proxy without that setting, the site's configured public URL (``host_name``) decides."""
	scheme = (getattr(getattr(frappe.local, "request", None), "scheme", "") or "http").lower()
	if scheme == "https":
		return "https"
	try:
		host_name = str(frappe.conf.get("host_name") or "")
	except Exception:
		host_name = ""
	return "https" if host_name.lower().startswith("https://") else "http"


def _check_origin() -> None:
	origin = frappe.get_request_header("Origin")
	if not origin:
		# no Origin: only a browser-asserted same-origin fetch is acceptable
		if (frappe.get_request_header("Sec-Fetch-Site") or "").lower() != "same-origin":
			raise WebAccessDenied("origin_missing")
		return
	parsed = urlparse(origin)
	host = (getattr(getattr(frappe.local, "request", None), "host", "") or "").lower()
	if parsed.netloc.lower() != host or parsed.scheme.lower() != _effective_scheme():
		raise WebAccessDenied("origin_mismatch")


def _bot_token(gateway_doc: Any) -> str:
	from huf.ai.gateway_webhook import _gateway_credentials

	return (_gateway_credentials(gateway_doc).get("token") or "").strip()


def _eligibility(binding: dict, gateway_doc: Any) -> None:
	user = binding.get("frappe_user")
	if not user or user in ALWAYS_REFUSED_USERS:
		raise WebAccessDenied("user_forbidden")
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	if not row or not row.enabled:
		raise WebAccessDenied("user_disabled")
	if row.user_type != "System User":
		raise WebAccessDenied("user_type")
	if PRIVILEGED_ROLES & set(frappe.get_roles(user)) and not int(
		gateway_doc.get("telegram_web_allow_privileged") or 0
	):
		raise WebAccessDenied("privileged_denied")


def _session_hours(gateway_doc: Any) -> int:
	try:
		hours = int(gateway_doc.get("telegram_web_session_hours") or DEFAULT_SESSION_HOURS)
	except (TypeError, ValueError):
		hours = DEFAULT_SESSION_HOURS
	return min(MAX_SESSION_HOURS, max(1, hours))


def _create_session(binding: dict, tg_id: str, gateway_doc: Any, hours: int) -> None:
	from frappe.auth import LoginManager

	marker = {
		"binding": binding["name"],
		"gateway": gateway_doc.name,
		"tg_id": tg_id,
		"allow_writes": int(gateway_doc.get("telegram_web_allow_writes") or 0),
		"web_access_version": MARKER_VERSION,
	}
	end = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
	manager = LoginManager()
	manager.login_as(binding["frappe_user"], session_end=end, audit_user=f"telegram:{tg_id}")
	session_obj = frappe.local.session_obj
	session_obj.data.data[MARKER_KEY] = marker
	session_obj.update(force=True)
	# Re-issue the sid cookie: lifetime = session length, and Secure whenever the connection is https
	# (see ``_effective_scheme``).
	#
	# Known Frappe behaviour, kept on purpose: ``login_as`` -> ``make_session`` -> ``clear_active_sessions``
	# signs the user out of their other sessions when ``deny_multiple_sessions`` is on (site config or System
	# Settings). Skipping that for Telegram would bypass the site's single-session policy, so it is not changed.
	frappe.local.cookie_manager.set_cookie(
		"sid",
		frappe.session.sid,
		max_age=hours * 3600,
		httponly=True,
		secure=_effective_scheme() == "https",
		samesite="Lax",
	)
	for key in ("home_page", "full_name", "message"):
		frappe.local.response.pop(key, None)


def _existing_session_ok(binding: dict, tg_id: str, gateway: str) -> bool:
	if frappe.session.user in ("Guest", None):
		return False
	marker = session_marker(frappe.session.data)
	return bool(
		marker
		and frappe.session.user == binding.get("frappe_user")
		and str(marker.get("tg_id")) == tg_id
		and marker.get("gateway") == gateway
	)


def _fail() -> None:
	frappe.throw(_("Not authorized"), frappe.PermissionError)


# -- endpoint ----------------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=IP_RATE_LIMIT, seconds=IP_RATE_WINDOW)
def exchange(init_data: str = "", gateway: str = "", to: str = "") -> dict:
	"""Sign the Telegram user in as their bound Frappe user and return ``{ok, redirect}``."""
	digest, gw_name, ctx = _digest(init_data), str(gateway or ""), {}
	try:
		return _exchange(init_data, gateway, to, digest, ctx)
	except WebAccessDenied as exc:
		code = exc.code
	except Exception:
		code = "internal_error"
		try:
			frappe.logger("huf").warning(f"telegram_web_access internal error h={digest}")
		except Exception:
			pass
	tg_id = ctx.get("tg_id", "")
	binding = ctx.get("binding")
	_log(code, digest, tg_id, (binding or {}).get("name", ""), "denied")
	if tg_id:
		_audit(binding, tg_id, gw_name, code, "denied")
	_fail()


def _exchange(init_data: Any, gateway: Any, to: Any, digest: str, ctx: dict) -> dict:
	from huf.ai.gateway_adapters.telegram_miniapp import MiniAppAuthError, validate_init_data

	if (
		not isinstance(init_data, str)
		or not init_data
		or not isinstance(gateway, str)
		or len(init_data) > 4096
	):
		raise WebAccessDenied("bad_request")
	_check_origin()
	if not frappe.db.exists("Gateway", {"name": gateway, "provider": "Telegram"}):
		raise WebAccessDenied("gateway_unknown")
	gw = frappe.get_doc("Gateway", gateway)
	if not gw.is_enabled:
		raise WebAccessDenied("gateway_disabled")
	if not int(gw.get("telegram_web_access_enabled") or 0):
		raise WebAccessDenied("web_access_disabled")
	target = resolve_target(to, gw)
	try:
		user = validate_init_data(init_data, _bot_token(gw), max_age_seconds=MAX_AGE_SECONDS)
	except MiniAppAuthError:
		raise WebAccessDenied("init_data_invalid") from None
	except Exception:
		raise WebAccessDenied("token_unavailable") from None
	tg_id = str(user.user_id)
	ctx["tg_id"] = tg_id
	if user.chat_type not in ("", "private", "sender"):
		raise WebAccessDenied("chat_type")
	if not check_rate(f"webx:{tg_id}", USER_RATE_LIMIT, USER_RATE_WINDOW):
		raise WebAccessDenied("rate_limited")
	if not _claim_once(f"huf_tg_web:h:{gateway}:{digest_full(init_data)}"):
		raise WebAccessDenied("replayed")
	if user.query_id and not _claim_once(f"huf_tg_web:q:{gateway}:{_sha(user.query_id)}"):
		raise WebAccessDenied("replayed_query")
	binding = get_binding(tg_id, gateway)
	if not binding:
		raise WebAccessDenied("unbound")
	ctx["binding"] = binding
	_eligibility(binding, gw)
	if _existing_session_ok(binding, tg_id, gateway):
		outcome = "reused"
	else:
		_create_session(binding, tg_id, gw, _session_hours(gw))
		outcome = "ok"
	_audit(binding, tg_id, gateway, outcome, "ok")
	_log(outcome, digest, tg_id, binding.get("name", ""), "ok")
	return {"ok": True, "redirect": target}


def _sha(text: str) -> str:
	return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def digest_full(init_data: str) -> str:
	from urllib.parse import parse_qsl

	h = dict(parse_qsl(init_data or "")).get("hash", "")
	return _sha(h or init_data)


def _claim_once(key: str) -> bool:
	return _claim(frappe.cache(), key, REPLAY_TTL)
