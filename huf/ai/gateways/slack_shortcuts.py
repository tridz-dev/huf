"""Slack message shortcut: "Ask Huf about this" (act on an existing message).

Slack POSTs a signed ``message_action`` payload to the interactivity endpoint; B1 routes it
to the handler registered under ``message_action:huf_ask_message`` as
``fn(gateway, None, actor_user, payload)`` (``actor_user`` is the A1-linked Huf user and B1
has already replied with the link prompt for unlinked clickers). The selected message is
injected into the NORMAL gateway pipeline via ``ingest_gateway_event`` so routing, bindings,
admission, privacy, identity and run-as-user apply exactly as for a typed message. The
message body is third-party content and is wrapped with ``wrap_untrusted``. Message bodies
and tokens are never logged.
"""

from __future__ import annotations

import frappe

from huf.ai.gateways import safety
from huf.ai.gateways import slack_interactivity as _si

CALLBACK_ID = "huf_ask_message"
HANDLER_KEY = f"message_action:{CALLBACK_ID}"
SHORTCUT_NAME = "Ask Huf about this"
SHORTCUT_DESCRIPTION = "Ask Huf to act on this message"

MSG_ON_IT = "On it — I'll reply in the thread."
MSG_LINK = "Please link your Huf account first (send me a direct message to get a link), then try again."
MSG_FAILED = "Sorry, I could not start that. Please try again."


def _s(value) -> str:
	return "" if value is None else str(value)


def is_room_channel(channel: str) -> bool:
	"""Public/private channels and group DMs are rooms; 1:1 DMs ('D...') are not."""
	return _s(channel).startswith(("C", "G"))


def build_event_id(team: str, channel: str, message_ts: str, actor_slack_id: str) -> str:
	return f"shortcut:{team}:{channel}:{message_ts}:{actor_slack_id}"


def _permalink(api, channel: str, ts: str) -> str:
	"""Best effort; failures only drop the link."""
	try:
		return _s(api.permalink(channel, ts))
	except Exception:
		return ""


def _api(gateway):
	from huf.ai.gateways.slack_context import get_slack_api

	return get_slack_api(gateway)


def build_context(payload: dict, permalink: str = "") -> dict:
	user = payload.get("user") or {}
	msg = payload.get("message") or {}
	channel = _s((payload.get("channel") or {}).get("id"))
	ts = _s(msg.get("ts") or payload.get("message_ts"))
	wrapped = safety.wrap_untrusted(
		msg.get("text") or "", "slack_message", author=_s(msg.get("user")) or None, ts=ts or None
	)
	text = (
		"The user asked you to act on this Slack message "
		f"(permalink: {permalink or 'unavailable'}):\n{wrapped}"
	)
	return {
		"sender_id": _s(user.get("id")),
		"conversation_id": channel,
		"thread_id": _s(msg.get("thread_ts") or ts),
		"message_text": text,
		"is_room": is_room_channel(channel),
		"mentioned": True,
		"display_name": _s(user.get("name") or user.get("username")) or None,
	}


def _tell(gateway, channel: str, slack_user: str, text: str) -> None:
	try:
		api = _api(gateway)
		if channel:
			api.post_ephemeral(channel, slack_user, text=text)
		else:
			api.post_message(api.conversations_open([slack_user]), text=text)
	except Exception:
		frappe.log_error(title="Slack shortcut notice failed")


def handle_ask_message(gateway, session, actor_user, payload) -> dict:
	"""Registered handler. ``session`` is always None for shortcuts."""
	user = payload.get("user") or {}
	slack_user = _s(user.get("id"))
	channel = _s((payload.get("channel") or {}).get("id"))
	msg = payload.get("message") or {}
	ts = _s(msg.get("ts") or payload.get("message_ts"))
	team = _s((payload.get("team") or {}).get("id") or user.get("team_id"))

	if not actor_user:
		_tell(gateway, channel, slack_user, MSG_LINK)
		return {}
	if not (slack_user and channel and ts):
		return {}

	link = _permalink(_api(gateway), channel, ts)
	context = build_context(payload, link)
	# Minimal redacted payload: no message body, tokens, trigger_id or response_url.
	raw = {
		"type": "message_action",
		"callback_id": CALLBACK_ID,
		"team": team,
		"team_id": team,
		"channel": channel,
		"message_ts": ts,
		"user": slack_user,
	}
	from huf.ai import gateway_service

	try:
		result = gateway_service.ingest_gateway_event(
			gateway.name,
			build_event_id(team, channel, ts, slack_user),
			context,
			verified_sender=True,
			raw_payload=raw,
		)
	except Exception:
		frappe.log_error(title="Slack shortcut ingest failed")
		_tell(gateway, channel, slack_user, MSG_FAILED)
		return {}
	if isinstance(result, dict) and result.get("duplicate"):
		return {}
	_tell(gateway, channel, slack_user, MSG_ON_IT)
	return {}


_si.register_action_handler(HANDLER_KEY, handle_ask_message)
