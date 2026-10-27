"""Slack interactivity endpoint (buttons, later modals/shortcuts) + opaque action sessions.

Slack POSTs ``application/x-www-form-urlencoded`` with a ``payload`` JSON field. The raw
body is signature-verified (same logic, replay window and status codes as ``slack_events``)
BEFORE anything is parsed. Buttons carry only a Gateway Action Session name; business data
stays server-side. The first valid click consumes the session with ONE conditional UPDATE.
Identity comes only from the signed payload's user/team mapped via the A1 identity link;
``response_url`` and every other client-supplied field are never trusted.
"""

from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import parse_qs

import frappe
from frappe.rate_limiter import rate_limit

from huf.ai.gateways import blocks as bk

DOCTYPE = "Gateway Action Session"
DEFAULT_TTL_SECONDS = 3600
_DEDUPE_PREFIX = "huf_slack_interaction:"
_DEDUPE_TTL = 600

_REASON_STATUS = {
	"unknown_gateway": 404,
	"gateway_disabled": 403,
	"wrong_provider": 403,
	"missing_headers": 401,
	"invalid_timestamp": 401,
	"stale_timestamp": 401,
	"missing_secret": 401,
	"bad_signature": 401,
}

MSG_LINK_FIRST = "Please link your Huf account first, then try again."
MSG_NOT_FOR_YOU = "This action was not meant for you."
MSG_USED = "This action was already handled."
MSG_EXPIRED = "This action has expired."
MSG_CANCELLED = "This action was cancelled."
MSG_UNKNOWN = "This action is no longer available."
MSG_UNSUPPORTED = "Sorry, that action is not supported yet."
MSG_FAILED = "Sorry, something went wrong handling that action."

_HANDLERS: dict[str, object] = {}
# Prefixes whose handler runs for a clicker who has NO linked Huf user (e.g. the identity-link
# confirmation itself). Their handlers get ``actor_user=None`` and must verify the Slack user.
_ACTOR_OPTIONAL: set[str] = set()


# --------------------------------------------------------------------------- registry
def register_action_handler(kind_prefix: str, fn, *, requires_actor: bool = True) -> None:
	"""Register ``fn(gateway, session, actor_user, payload) -> dict`` for session kinds
	starting with ``kind_prefix``. Result keys: ``text`` (status text), ``blocks`` (optional
	replacement blocks). The longest matching prefix wins; re-registering replaces.
	``requires_actor=False`` lets clickers without a linked Huf user through (handler gets
	``actor_user=None``)."""
	if not kind_prefix or not callable(fn):
		raise ValueError("kind_prefix and a callable handler are required")
	_HANDLERS[kind_prefix] = fn
	(_ACTOR_OPTIONAL.discard if requires_actor else _ACTOR_OPTIONAL.add)(kind_prefix)


def _actor_optional(kind: str) -> bool:
	matches = [p for p in _HANDLERS if str(kind or "").startswith(p)]
	return bool(matches) and max(matches, key=len) in _ACTOR_OPTIONAL


def get_action_handler(kind: str):
	# Handler modules register at import time; make sure the module list is loaded in this process.
	from huf.ai.gateways import hooks as gw_hooks

	gw_hooks.register_all()
	matches = [p for p in _HANDLERS if str(kind or "").startswith(p)]
	return _HANDLERS[max(matches, key=len)] if matches else None


# --------------------------------------------------------------------------- sessions
def _now():
	return frappe.utils.now_datetime()


def create_action_session(gateway, kind, payload=None, intended_user=None, intended_slack_user=None,
	ttl_seconds=DEFAULT_TTL_SECONDS, channel=None, message_ts=None) -> str:
	"""Create a Pending session and return its name (the only thing put in a button)."""
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"gateway": getattr(gateway, "name", gateway),
			"kind": kind,
			"state": "Pending",
			"payload": json.dumps(payload or {}),
			"intended_user": intended_user,
			"intended_slack_user": intended_slack_user,
			"expires_at": _now() + timedelta(seconds=int(ttl_seconds)),
			"channel": channel,
			"message_ts": message_ts,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _rowcount() -> int:
	cursor = getattr(frappe.db, "_cursor", None)
	return int(getattr(cursor, "rowcount", 0) or 0)


def consume_action_session(name: str, actor_user: str) -> dict:
	"""Atomically consume a Pending, unexpired session. First caller wins.

	Returns ``{"ok": True}`` or ``{"ok": False, "reason": ..., "message": plain text}``.
	"""
	now = frappe.utils.now()
	frappe.db.sql(
		"UPDATE `tabGateway Action Session` SET state=%s, consumed_by=%s, consumed_at=%s "
		"WHERE name=%s AND state='Pending' AND expires_at > %s",
		("Consumed", actor_user, now, name, now),
	)
	if _rowcount() == 1:
		return {"ok": True, "consumed_at": now}
	state = frappe.db.get_value(DOCTYPE, name, "state")
	if state is None:
		return {"ok": False, "reason": "unknown", "message": MSG_UNKNOWN}
	if state == "Consumed":
		return {"ok": False, "reason": "consumed", "message": MSG_USED}
	if state == "Cancelled":
		return {"ok": False, "reason": "cancelled", "message": MSG_CANCELLED}
	if state == "Pending":
		frappe.db.sql(
			"UPDATE `tabGateway Action Session` SET state='Expired' WHERE name=%s AND state='Pending'",
			(name,),
		)
	return {"ok": False, "reason": "expired", "message": MSG_EXPIRED}


def release_action_session(name: str, actor_user: str, consumed_at=None) -> bool:
	"""Re-open a session this request consumed (state back to Pending) so the click is not lost.

	Only touches a row that is still Consumed by ``actor_user`` (and, when given, at exactly
	``consumed_at``, the value returned by :func:`consume_action_session`). Returns True if
	a row was re-opened.
	"""
	sql = ("UPDATE `tabGateway Action Session` SET state='Pending', consumed_by=NULL, consumed_at=NULL "
		"WHERE name=%s AND state='Consumed' AND consumed_by=%s")
	params = [name, actor_user]
	if consumed_at:
		sql += " AND consumed_at=%s"
		params.append(consumed_at)
	frappe.db.sql(sql, tuple(params))
	return _rowcount() == 1


def _load_session(name: str):
	row = frappe.db.get_value(
		DOCTYPE,
		name,
		["name", "gateway", "kind", "state", "intended_user", "intended_slack_user", "payload", "channel",
			"message_ts", "expires_at"],
		as_dict=True,
	)
	if not row:
		return None
	raw = row.get("payload")
	try:
		parsed = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
	except ValueError:
		parsed = {}
	row["payload"] = parsed if isinstance(parsed, dict) else {}
	return row


# --------------------------------------------------------------------------- verification
def verify_request_signature(gateway_name, body, headers):
	"""Thin public wrapper over slack_events' verifier: None if valid, else a reason key."""
	from huf.ai.gateways.slack_events import _verify_slack_signature

	return _verify_slack_signature(gateway_name, body, headers)


def _cache():
	cache = frappe.cache
	return cache() if callable(cache) and not hasattr(cache, "get_value") else cache


def _already_seen(payload: dict) -> bool:
	"""Best-effort dedupe on the Slack action id / trigger id (atomic consume is the real guard)."""
	actions = payload.get("actions") or []
	first = actions[0] if actions and isinstance(actions[0], dict) else {}
	ident = first.get("action_ts") or payload.get("trigger_id") or ""
	if not ident:
		return False
	key = f"{_DEDUPE_PREFIX}{(payload.get('user') or {}).get('id', '')}:{first.get('action_id', '')}:{ident}"
	cache = _cache()
	if cache.get_value(key):
		return True
	cache.set_value(key, 1, expires_in_sec=_DEDUPE_TTL)
	return False


# --------------------------------------------------------------------------- endpoint
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=60)
def handle_slack_interaction():
	gateway_name = frappe.request.args.get("gateway_name") if frappe.request is not None else None
	body = frappe.request.get_data(as_text=False)

	reason = verify_request_signature(gateway_name, body, frappe.request.headers)
	if reason:
		frappe.local.response.http_status_code = _REASON_STATUS.get(reason, 401)
		return {"ok": False, "error": reason}

	payload = _parse_payload(body)
	if payload is None:
		frappe.local.response.http_status_code = 400
		return {"ok": False, "error": "malformed_payload"}

	gateway = frappe.get_doc("Gateway", gateway_name)
	try:
		process_interaction(gateway, payload)
	except Exception:
		frappe.log_error(title="Slack interaction failed")  # never log the payload
	return {}


def _parse_payload(body):
	try:
		text = body.decode("utf-8") if isinstance(body, bytes) else str(body)
		values = parse_qs(text, keep_blank_values=True).get("payload") or []
		if len(values) != 1:
			return None
		payload = json.loads(values[0])
	except (ValueError, UnicodeDecodeError):
		return None
	return payload if isinstance(payload, dict) else None


# --------------------------------------------------------------------------- processing
def _identity(gateway, payload):
	from huf.ai.gateways import identity

	user = payload.get("user") or {}
	team = (payload.get("team") or {}).get("id") or user.get("team_id") or ""
	slack_user = str(user.get("id") or "")
	if not team or not slack_user:
		return slack_user, None
	link = identity._find_link(gateway.name, str(team), slack_user)
	if link and identity._usable(link.user, link.source):
		return slack_user, link.user
	return slack_user, None


def _where(payload):
	container = payload.get("container") or {}
	channel = container.get("channel_id") or (payload.get("channel") or {}).get("id")
	ts = container.get("message_ts") or (payload.get("message") or {}).get("ts")
	return (str(channel) if channel else None), (str(ts) if ts else None)


def _tell(gateway, payload, slack_user, text):
	"""Ephemeral note to the clicker via the bot API (never response_url)."""
	try:
		from huf.ai.gateways.slack_context import get_slack_api

		api = get_slack_api(gateway)
		channel, _ts = _where(payload)
		if not channel:
			channel = api.conversations_open([slack_user])
			api.post_message(channel, text=text)
		else:
			api.post_ephemeral(channel, slack_user, text=text)
	except Exception:
		frappe.log_error(title="Slack interaction notice failed")


def process_interaction(gateway, payload: dict) -> None:
	kind = payload.get("type")
	if kind == "block_actions":
		return _process_block_actions(gateway, payload)
	if kind in ("view_submission", "shortcut", "message_action"):
		slack_user, actor = _identity(gateway, payload)
		key = f"{kind}:{payload.get('callback_id') or (payload.get('view') or {}).get('callback_id') or ''}"
		fn = get_action_handler(key)
		if not fn:
			return _tell(gateway, payload, slack_user, MSG_UNSUPPORTED)
		if not actor:
			return _tell(gateway, payload, slack_user, MSG_LINK_FIRST)
		fn(gateway, None, actor, payload)
	return None


def _process_block_actions(gateway, payload):
	actions = payload.get("actions") or []
	first = actions[0] if actions and isinstance(actions[0], dict) else None
	if not first:
		return
	slack_user, actor = _identity(gateway, payload)
	if _already_seen(payload):
		return
	name = str(first.get("value") or "")
	session_name, choice = bk.parse_action_id(first.get("action_id"))
	if not name or session_name != name:
		return _tell(gateway, payload, slack_user, MSG_UNKNOWN)
	session = _load_session(name)
	if not actor:
		get_action_handler(session.kind if session else "")  # make sure handler modules are loaded
		if not (session and slack_user and _actor_optional(session.kind)):
			return _tell(gateway, payload, slack_user, MSG_LINK_FIRST)
	if not session or session.gateway != gateway.name:
		return _tell(gateway, payload, slack_user, MSG_UNKNOWN)
	channel, ts = _where(payload)
	if session.get("channel") and channel and session["channel"] != channel:
		return _tell(gateway, payload, slack_user, MSG_UNKNOWN)
	if session.intended_user and session.intended_user != actor:
		return _tell(gateway, payload, slack_user, MSG_NOT_FOR_YOU)
	if session.intended_slack_user and session.intended_slack_user != slack_user:
		return _tell(gateway, payload, slack_user, MSG_NOT_FOR_YOU)

	fn = get_action_handler(session.kind)
	if not fn:
		return _tell(gateway, payload, slack_user, MSG_UNSUPPORTED)

	consumer = actor or f"slack:{slack_user}"
	result = consume_action_session(name, consumer)
	if not result["ok"]:
		return _tell(gateway, payload, slack_user, result["message"])

	session["choice"] = choice
	try:
		out = fn(gateway, session, actor, payload) or {}
	except Exception:
		frappe.log_error(title="Slack action handler failed")
		try:
			frappe.db.rollback()
		except Exception:
			pass
		try:
			release_action_session(name, consumer, result.get("consumed_at"))
		except Exception:
			frappe.log_error(title="Slack action session release failed")
		out = {"text": MSG_FAILED}
	_update_message(gateway, channel, ts, out)


def _update_message(gateway, channel, ts, out: dict) -> None:
	if not channel or not ts:
		return
	text = str(out.get("text") or "Done.")
	blocks = out.get("blocks") or bk.status_line(text).blocks
	try:
		from huf.ai.gateways.slack_context import get_slack_api

		get_slack_api(gateway).update_message(channel, ts, text=text, blocks=blocks)
	except Exception:
		frappe.log_error(title="Slack message update failed")
