"""Microsoft Teams chat commands: help, connect, status, disconnect.

A ``pre_ingest_filter`` (provider ``microsoft teams``, priority 40) answers these four words
straight through the Teams outbox, with no LLM and no routing. The reply goes to the
conversation the command came from. Commands only ever act for the activity's real sender;
a target user is never read from text. Anything else passes through untouched.

Privacy: a one-time link is never minted in a channel or group chat, and ``status`` (which
lists the sender's recent runs) is only answered in a personal chat.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe

from huf.ai.gateways import hooks
from huf.ai.gateways import teams_api, teams_identity, teams_outbox, teams_refs
from huf.ai.gateways import teams_contract as tc

HOOK_PROVIDER = tc.PROVIDER_LABEL.lower()
COMMANDS = ("help", "connect", "status", "disconnect")
STATUS_RUN_LIMIT = 5

# --- copy (SPEC section 20) ---------------------------------------------------------------
TEXT_FIRST_CONTACT = (
	"Hi, I'm Huf. Connect your Huf account to ask questions, submit requests and use the tools "
	"your organization has enabled."
)
TEXT_HELP = (
	"You can ask me questions and use your organization's enabled workflows. Choose a tool below, "
	"or describe what you need. I'll ask for missing details and show a review step when an action "
	"needs confirmation.\n\nCommands: help, connect, status, disconnect."
)
TEXT_CONNECT_LINK = (
	"Open this link while logged in to Huf to connect your account. It works once and expires in "
	"10 minutes: {url}"
)
TEXT_CONNECT_PERSONAL = "Open a personal chat with me and send connect."
TEXT_ALREADY_LINKED = (
	"Your Teams account is connected to Huf as {name}. Your access follows your Huf permissions."
)
TEXT_STATUS_HEAD = "Huf account: {name}."
TEXT_STATUS_NONE = "No recent requests."
TEXT_STATUS_PERSONAL = "Open a personal chat with me and send status."
TEXT_GUEST = "Guest and external Microsoft accounts are not supported."
TEXT_DISCONNECTED = (
	"Your Huf account is disconnected from Teams. Personalized requests and notifications are "
	"paused. You can connect again whenever your organization permits."
)
TEXT_NOT_CONNECTED = "Your Huf account is not connected to Teams."


def _s(value: Any) -> str:
	return str(value) if value else ""


def parse_command(text: Any) -> str | None:
	"""``help|connect|status|disconnect`` (trimmed, case-insensitive, optional leading slash) or None."""
	if not isinstance(text, str):
		return None
	word = text.strip()
	if word.startswith("/"):
		word = word[1:]
	word = word.strip().lower()
	return word if word in COMMANDS else None


def _activity(context: Any) -> dict:
	raw = context.get("raw_payload") if isinstance(context, dict) else getattr(context, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = None
	return raw if isinstance(raw, dict) else {}


def _gateway_name(gateway: Any) -> str:
	name = getattr(gateway, "name", None)
	if name is None and isinstance(gateway, dict):
		name = gateway.get("name")
	return _s(name)


def _is_personal(meta) -> bool:
	return meta.conversation_type == "personal"


def _snapshot(gateway_name: str, meta) -> dict:
	"""Reply target built from the activity itself. Raises TeamsApiError on a hostile service URL."""
	service_url = teams_api.validate_service_url(meta.service_url)
	return {
		"conversation_ref": teams_refs.reference_name(
			gateway_name, meta.tenant_id, teams_refs._base_conversation_id(meta.conversation_id)
		),
		"conversation_id": meta.conversation_id,
		"service_url": service_url,
		"tenant_id": meta.tenant_id,
		"gateway": gateway_name,
	}


def idempotency_key(gateway_name: str, activity: dict, command: str) -> str:
	ident = _s(activity.get("id"))
	if not ident:
		ident = hashlib.sha256(json.dumps(activity, sort_keys=True, default=str).encode()).hexdigest()
	raw = "\x1f".join((gateway_name, ident, command))
	return "teams_help:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _display_name(user: str) -> str:
	try:
		return _s(frappe.db.get_value("User", user, "full_name")) or user
	except Exception:
		return user


def _is_guest(activity: dict) -> bool:
	return teams_identity._is_guest(activity)


def _recent_runs(gateway_name: str, user: str) -> list[dict]:
	return frappe.get_all(
		"Agent Run",
		filters={"requester_user": user, "gateway": gateway_name},
		fields=["name", "status", "creation"],
		order_by="creation desc",
		limit=STATUS_RUN_LIMIT,
	)


def _status_text(gateway_name: str, user: str) -> str:
	lines = [TEXT_STATUS_HEAD.format(name=_display_name(user))]
	runs = _recent_runs(gateway_name, user) or []
	if not runs:
		lines.append(TEXT_STATUS_NONE)
	else:
		lines.append("Recent requests:")
		for run in runs:
			status = _s(run.get("status")) or "Unknown"
			lines.append(f"- {_s(run.get('name'))}: {status} ({_s(run.get('creation'))})")
	return "\n".join(lines)


def build_reply(gateway, command: str, activity: dict, meta) -> str:
	"""Reply text for a recognised command. Pure apart from reads and the disconnect revoke."""
	gw = _gateway_name(gateway)
	personal = _is_personal(meta)
	guest = _is_guest(activity) or not (meta.tenant_id and meta.user_aad_id)
	user = None if guest else teams_identity.resolve_user(gw, meta.tenant_id, meta.user_aad_id)

	if command == "disconnect":
		if guest:
			return TEXT_GUEST
		if teams_identity.disconnect_current(gw, meta.tenant_id, meta.user_aad_id):
			return TEXT_DISCONNECTED
		return TEXT_NOT_CONNECTED

	if guest:
		return TEXT_GUEST

	if command == "help":
		if user:
			return TEXT_HELP
		if personal:
			return TEXT_FIRST_CONTACT + "\n\nSend connect to link your account."
		return TEXT_FIRST_CONTACT + "\n\n" + TEXT_CONNECT_PERSONAL

	if command == "connect":
		if user:
			return TEXT_ALREADY_LINKED.format(name=_display_name(user))
		if not personal:
			return TEXT_CONNECT_PERSONAL
		label = _s((activity.get("from") or {}).get("name")) or None
		token = teams_identity._prompt_token(gw, meta.tenant_id, meta.user_aad_id, label)
		return TEXT_CONNECT_LINK.format(url=teams_identity.link_url(token))

	# status
	if not user:
		return TEXT_FIRST_CONTACT + "\n\n" + (
			"Send connect to link your account." if personal else TEXT_CONNECT_PERSONAL
		)
	if not personal:
		return TEXT_STATUS_PERSONAL
	return _status_text(gw, user)


def pre_ingest_commands(gateway, context) -> bool:
	"""True passes the event on; a recognised command is answered here and returns False."""
	command = parse_command(context.get("message_text") if isinstance(context, dict) else None)
	if command is None:
		return True
	try:
		activity = _activity(context)
		meta = teams_refs.parse_meta(activity)
		gw = _gateway_name(gateway)
		snapshot = _snapshot(gw, meta)  # hostile/missing serviceUrl => nothing is sent
		text = build_reply(gateway, command, activity, meta)
		reply = {"type": "message", "text": text, "textFormat": "markdown"}
		if _s(activity.get("id")):
			reply["replyToId"] = _s(activity.get("id"))
		key = idempotency_key(gw, activity, command)
		teams_outbox.enqueue(gw, snapshot, "reply", {"activity": reply}, key)
	except Exception:
		try:
			frappe.log_error(frappe.get_traceback(), "Teams help command failed"[:140])
		except Exception:
			pass
	try:
		frappe.flags.gateway_filter_reason = None  # a command is not a rejection
	except Exception:
		pass
	return False


def register() -> None:
	hooks.register(
		hooks.PRE_INGEST_FILTER,
		pre_ingest_commands,
		provider=HOOK_PROVIDER,
		priority=tc.HOOK_PRIORITY_COMMANDS,
	)


register()
