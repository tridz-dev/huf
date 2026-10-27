"""Agent tool for Microsoft Teams: ONE consolidated, gateway-bound tool (``microsoft_teams``).

Follows the WhatsApp/Telegram practice: the gateway is NEVER a model argument. It is derived server
side from the run (Agent Run -> Agent Conversation.channel == ``gateway:<name>``) and must be an enabled
``Microsoft Teams`` Gateway. Bot Framework can only message conversations the bot has already seen, so
recipients are limited to conversations with a stored reference for THIS gateway (default: the
conversation of the current run). Sends are capped per run. Credentials are read server side and never
returned or logged.

Registration: ``hooks.huf_tools`` lists ``huf.ai.teams.tools.TEAMS_TOOLS`` (``_registry.py`` is baselined
and cannot grow). Entries are stamped with the ``microsoft_teams`` Integration Service here, since the
hook path bypasses ``_registry._with_service``.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from huf.ai.gateway_adapters.types import GatewayReply
from huf.ai.teams import client, refs
from huf.ai.tools._registry import _action, _p

SERVICE = "microsoft_teams"
PROVIDER = "Microsoft Teams"
ACTIONS = ("send_message", "list_recent_conversations", "get_account_info")
MAX_SENDS_PER_RUN = 5
MAX_TEXT_CHARS = 8000
LIST_DEFAULT_LIMIT = 10
LIST_MAX_LIMIT = 25
_CAP_TTL = 24 * 3600
_CAP_PREFIX = "huf_teams_tool_sends:"
# Keys the model must never control or supply (tool args are persisted in Agent Tool Call).
_BOUND_KWARGS = (
	"gateway_name", "gateway", "app_id", "app_password", "tenant_id", "tenant", "credentials",
	"service_url", "serviceUrl", "access_token", "token", "channel",
)

# Test seam: a fake transport for the Bot Connector (never set in production).
_transport: Any = None


def _refused(code: str, message: str) -> str:
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


def _ok(data: Any) -> str:
	return json.dumps({"success": True, "data": data}, default=str)


def _run_id() -> str:
	return str(getattr(frappe.flags, "huf_current_agent_run_id", None) or "")


def _run_gateway() -> str:
	"""The enabled Teams Gateway the current run belongs to, or '' (fail closed). Never from tool args."""
	try:
		run_id = _run_id()
		if not run_id:
			return ""
		conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		channel = str(frappe.db.get_value("Agent Conversation", conversation, "channel") or "") if conversation else ""
		if not channel.startswith("gateway:"):
			return ""
		name = channel[len("gateway:"):].strip()
		row = frappe.db.get_value("Gateway", name, ["provider", "is_enabled"], as_dict=True) if name else None
		if not row or row.get("provider") != PROVIDER or not row.get("is_enabled"):
			return ""
		return name
	except Exception:
		return ""


def _credentials(gateway_name: str) -> dict[str, str]:
	try:
		return dict(frappe.get_doc("Gateway", gateway_name)._load_integration_credentials() or {})
	except Exception:
		return {}


def _base(conversation_id: str) -> str:
	return str(conversation_id or "").partition(";messageid=")[0].strip()


def _current_conversation(gateway_name: str) -> str:
	"""Conversation id of the inbound event that started this run (server side)."""
	run_id = _run_id()
	if not run_id:
		return ""
	value = frappe.db.get_value("Gateway Event", {"gateway": gateway_name, "agent_run": run_id}, "conversation_id")
	return str(value or "")


def _escape_like(value: str) -> str:
	return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _has_gateway_reference(gateway_name: str, app_id: str, conversation_id: str) -> bool:
	"""A verified inbound event for THIS gateway exists for the conversation AND a reference is stored."""
	base = _base(conversation_id)
	if not base:
		return False
	seen = frappe.db.exists(
		"Gateway Event",
		{"gateway": gateway_name, "verified_sender": 1, "conversation_id": ["like", f"{_escape_like(base)}%"]},
	)
	if not seen:
		return False
	return bool(refs.get_reference(gateway_name, app_id, base))


def _sent_count(run_id: str) -> int:
	try:
		return int(frappe.cache.get_value(_CAP_PREFIX + run_id) or 0)
	except Exception:
		return 0


def _bump_sent(run_id: str) -> None:
	try:
		frappe.cache.set_value(_CAP_PREFIX + run_id, _sent_count(run_id) + 1, expires_in_sec=_CAP_TTL)
	except Exception:
		pass


def _authorize_read(gateway_name: str) -> str | None:
	"""Read actions need real Gateway read authority (sends are authorised by the run's own gateway)."""
	try:
		allowed = bool(frappe.has_permission("Gateway", "read", doc=gateway_name))
	except Exception:
		allowed = False
	if allowed:
		return None
	return _refused("permission_denied", "Not permitted to use Microsoft Teams through this Gateway")


def _send_message(gateway_name: str, kwargs: dict) -> str:
	# Sending is authorised for the run's own gateway (bound server side), like WhatsApp sends.
	text = kwargs.get("text") if kwargs.get("text") is not None else kwargs.get("message")
	text = str(text or "").strip()
	if not text:
		return _refused("invalid_arguments", "text is required for send_message")
	if len(text) > MAX_TEXT_CHARS:
		return _refused("text_too_long", f"text exceeds {MAX_TEXT_CHARS} characters")
	creds = _credentials(gateway_name)
	if not (creds.get("app_id") and creds.get("app_password") and creds.get("tenant_id")):
		return _refused("not_configured", "This Teams gateway has no complete credentials configured")

	explicit = str(kwargs.get("conversation_id") or "").strip()
	target = explicit or _current_conversation(gateway_name)
	if not target:
		return _refused(
			"no_conversation",
			"No Teams conversation is associated with this run; pass a conversation_id from list_recent_conversations",
		)
	if not _has_gateway_reference(gateway_name, creds["app_id"], target):
		return _refused(
			"no_conversation_reference",
			"No stored Teams conversation reference exists for this gateway and conversation: "
			"the user must message the bot first",
		)
	run_id = _run_id()
	if run_id and _sent_count(run_id) >= MAX_SENDS_PER_RUN:
		return _refused("send_cap_reached", f"This run already sent {MAX_SENDS_PER_RUN} Teams messages (the per-run limit)")
	try:
		delivery = client.send_reply(
			GatewayReply(conversation_id=target, text=text), creds, gateway_name=gateway_name, transport=_transport
		)
	except client.TeamsSendError as exc:
		return _refused("send_failed", client.error_text(exc))
	if run_id:
		_bump_sent(run_id)
	return _ok({"activity_id": delivery.provider_message_id, "conversation_id": target})


def _conversation_type(payload: Any) -> tuple[str, str]:
	if isinstance(payload, str):
		try:
			payload = json.loads(payload)
		except ValueError:
			return "unknown", ""
	conv = payload.get("conversation") if isinstance(payload, dict) else None
	if not isinstance(conv, dict):
		return "unknown", ""
	kind = str(conv.get("conversationType") or ("groupChat" if conv.get("isGroup") else "unknown"))
	return kind, str(conv.get("name") or "")


def _list_recent(gateway_name: str, kwargs: dict) -> str:
	try:
		limit = int(kwargs.get("limit") or LIST_DEFAULT_LIMIT)
	except (TypeError, ValueError):
		return _refused("invalid_arguments", "limit must be an integer")
	limit = max(1, min(limit, LIST_MAX_LIMIT))
	rows = frappe.get_all(
		"Gateway Event",
		filters={"gateway": gateway_name, "verified_sender": 1},
		fields=["conversation_id", "received_at", "raw_payload"],
		order_by="received_at desc, creation desc",
		limit_page_length=limit * 10,
	)
	seen: dict[str, dict] = {}
	for row in rows:
		base = _base(row.get("conversation_id"))
		if not base or base in seen:
			continue
		kind, name = _conversation_type(row.get("raw_payload"))
		seen[base] = {"conversation_id": base, "type": kind, "last_seen": row.get("received_at"), "name": name}
		if len(seen) >= limit:
			break
	return _ok({"conversations": list(seen.values()), "count": len(seen)})


def _account_info(gateway_name: str) -> str:
	creds = _credentials(gateway_name)
	return _ok({
		"bot_name": frappe.db.get_value("Gateway", gateway_name, "gateway_name") or gateway_name,
		"app_id": creds.get("app_id", ""),
		"tenant_id": creds.get("tenant_id", ""),
		"enabled": bool(frappe.db.get_value("Gateway", gateway_name, "is_enabled")),
		"credentials_configured": bool(creds.get("app_id") and creds.get("app_password") and creds.get("tenant_id")),
	})


def handle_action(action: str = "", **kwargs: Any) -> str:
	"""Entry point for the ``microsoft_teams`` tool (bound to the current run's gateway)."""
	action = (action or "").strip().lower()
	for name in _BOUND_KWARGS:
		kwargs.pop(name, None)
	if action not in ACTIONS:
		return _refused("unknown_action", f"action must be one of: {', '.join(ACTIONS)}")
	gateway_name = _run_gateway()
	if not gateway_name:
		return _refused(
			"gateway_context_required",
			"Microsoft Teams can only be used from a run that belongs to an enabled Microsoft Teams gateway.",
		)
	if action == "send_message":
		return _send_message(gateway_name, kwargs)
	refusal = _authorize_read(gateway_name)
	if refusal:
		return refusal
	if action == "list_recent_conversations":
		return _list_recent(gateway_name, kwargs)
	return _account_info(gateway_name)


TEAMS_TOOLS = [
	{
		"tool_name": "microsoft_teams",
		"description": (
			"Send Microsoft Teams messages through the Teams bot gateway this conversation belongs to (it cannot be chosen). "
			"Actions: send_message (text; sends to the Teams conversation you are in by default; optional conversation_id "
			"must be one returned by list_recent_conversations; Teams only allows messages to conversations the bot has "
			f"already seen; max {MAX_TEXT_CHARS} characters and {MAX_SENDS_PER_RUN} messages per run), "
			"list_recent_conversations (limit; conversation ids, type and last seen for this gateway), "
			"get_account_info (bot name, app id, tenant id, enabled state; never secrets)."
		),
		"function_path": "huf.ai.teams.tools.handle_action",
		"category": "Communication Tools",
		"service": SERVICE,
		"parameters": [
			_action("|".join(ACTIONS)),
			_p("text", description="Message text for send_message (Markdown). Alias: message."),
			_p("message", description="Alias for 'text'."),
			_p("conversation_id", description="Optional send_message target; must come from list_recent_conversations. Omit to reply in the current conversation."),
			_p("limit", type="integer", description=f"list_recent_conversations: max rows (default {LIST_DEFAULT_LIMIT}, at most {LIST_MAX_LIMIT})."),
		],
	},
]
