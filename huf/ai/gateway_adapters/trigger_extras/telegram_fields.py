"""Telegram fields a flow trigger sees under ``input.*`` (names equal the registry ``payload_fields``).

``callback_data`` is what the button was built with, not the label swapped into the message text; the text routing for
agents is unchanged. Pure functions over the stored event payload.
"""

from __future__ import annotations

import json
import re
from typing import Any

_MESSAGE_KEYS = ("message", "edited_message", "channel_post", "edited_channel_post")
_EDITED = ("edited_message", "edited_channel_post")
_CHANNEL = ("channel_post", "edited_channel_post")
_COMMAND = re.compile(r"^/([A-Za-z0-9_]{1,32})(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$", re.S)


def meta_of(parsed) -> dict[str, Any]:
	"""``telegram_meta`` stored beside the raw update: what the parser learned that the raw update does not say."""
	meta = {
		"update_kind": parsed.kind,
		"chat_type": parsed.chat_type,
		"is_bot": parsed.is_bot,
		"message_thread_id": parsed.message_thread_id,
		"business_connection_id": parsed.business_connection_id,
		"sender_business_bot": parsed.sender_business_bot,
		"start_payload": parsed.start_payload,
		"callback_query_id": parsed.callback_query_id,
		"is_room": parsed.is_room,
		"mentioned": parsed.mentioned,
	}
	return {k: v for k, v in meta.items() if v not in ("", False, None)}


def _raw(event) -> dict:
	raw = event.get("raw_payload") if hasattr(event, "get") else getattr(event, "raw_payload", None)
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	return raw if isinstance(raw, dict) else {}


def _message(raw: dict) -> dict:
	for key in _MESSAGE_KEYS:
		if isinstance(raw.get(key), dict):
			return raw[key]
	return {}


def split_command(text: str) -> tuple[str, str]:
	"""``("start", "ref42")`` for ``/start@MyBot ref42``; ``("", "")`` when the text is not a command."""
	match = _COMMAND.match((text or "").strip())
	if not match:
		return "", ""
	return match.group(1).lower(), (match.group(2) or "").strip()


def _name(user: dict) -> str:
	return " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p).strip()


def extra_fields(event, gateway, sender) -> dict:
	"""Provider extras merged into a flow's trigger payload for a Telegram event."""
	raw = _raw(event)
	meta = raw.get("telegram_meta") or {}
	callback = raw.get("callback_query") if isinstance(raw.get("callback_query"), dict) else {}
	update_kind = next((k for k in _MESSAGE_KEYS if isinstance(raw.get(k), dict)), "callback_query" if callback else "")
	msg = _message(raw) or callback.get("message") or {}
	chat = msg.get("chat") or {}
	user = (callback.get("from") if callback else msg.get("from")) or {}
	text = str(msg.get("text") or msg.get("caption") or "") if not callback else ""
	command, args = split_command(text)
	command = command or str(meta.get("command") or "")
	web_app = msg.get("web_app_data") if isinstance(msg.get("web_app_data"), dict) else None
	chat_type = meta.get("chat_type") or chat.get("type") or ""
	values = {
		"telegram_user_id": sender,
		"telegram_chat_id": str(chat.get("id") or event.conversation_id or ""),
		"telegram_chat_type": chat_type,
		"message_thread_id": meta.get("message_thread_id") or "",
		"topic_id": meta.get("message_thread_id") or "",
		"command": command,
		"command_args": args,
		"callback_data": meta.get("callback_data") or "",
		"callback_query_id": meta.get("callback_query_id") or "",
		"username": user.get("username") or "",
		"edited": update_kind in _EDITED,
		"is_channel_post": update_kind in _CHANNEL,
		"web_app_data": {"data": web_app.get("data") or "", "button_text": web_app.get("button_text") or ""} if web_app else None,
		"sender_is_bot": bool(meta.get("is_bot") or user.get("is_bot")),
		"business_connection_id": meta.get("business_connection_id") or "",
		"kind": "callback" if callback else "message",
		"display_name": _name(user),
		"language": user.get("language_code") or "",
		"is_room": bool(meta.get("is_room")) or chat_type in ("group", "supergroup", "channel"),
		"mentioned": bool(meta.get("mentioned")),
	}
	return {k: v for k, v in values.items() if v not in ("", None)}
