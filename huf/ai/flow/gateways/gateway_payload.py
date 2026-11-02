"""The flat ``input.*`` payload a Flow gets for a gateway message (moved out of ``gateway_service``).

Generic keys are the registry's generic ``payload_fields``; provider extras stay behind
``provider_hooks.extra_event_fields``. Pure parsing helpers have no frappe dependency.
"""

from __future__ import annotations

import json

#: Normalized ``message_type`` values (registry ``MESSAGE_KINDS``).
MESSAGE_TYPES = (
	"text", "image", "audio", "voice", "video", "document", "sticker", "location", "contact",
	"button_reply", "list_reply", "order", "other",
)

_WA_TYPES = {
	"text": "text", "image": "image", "audio": "audio", "video": "video", "document": "document",
	"sticker": "sticker", "location": "location", "contacts": "contact", "contact": "contact",
	"order": "order", "button": "button_reply",
}
_TG_KEYS = (
	("voice", "voice"), ("audio", "audio"), ("photo", "image"), ("video", "video"), ("video_note", "video"),
	("document", "document"), ("sticker", "sticker"), ("location", "location"), ("contact", "contact"),
)
_TG_ROOM_TYPES = ("group", "supergroup", "channel")


def _dict(value) -> dict:
	return value if isinstance(value, dict) else {}


def parse_raw(event) -> dict:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	return _dict(raw)


def _telegram_message(raw: dict) -> dict:
	for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
		if isinstance(raw.get(key), dict):
			return raw[key]
	return _dict(_dict(raw.get("callback_query")).get("message"))


def normalize_message_type(raw: dict) -> str:
	"""One of ``MESSAGE_TYPES`` from a WhatsApp-shaped or Telegram-shaped raw payload."""
	if isinstance(raw.get("callback_query"), dict):
		return "button_reply"
	message = _dict(raw.get("message"))
	wa_type = str(message.get("type") or "")
	if wa_type == "interactive":
		interactive = _dict(message.get("interactive"))
		return "list_reply" if interactive.get("list_reply") else "button_reply"
	if wa_type == "audio" and _dict(message.get("audio")).get("voice"):
		return "voice"
	if wa_type in _WA_TYPES:
		return _WA_TYPES[wa_type]
	tg = _telegram_message(raw)
	for key, kind in _TG_KEYS:
		if tg.get(key):
			return kind
	if wa_type or tg.get("text") is not None:
		return "text" if (not wa_type or wa_type == "text") else "other"
	return "text"


def event_kind(raw: dict) -> str:
	if raw.get("kind"):
		return str(raw["kind"])
	return "callback" if isinstance(raw.get("callback_query"), dict) else "message"


def _sender_dict(raw: dict) -> dict:
	return _dict(_telegram_message(raw).get("from")) or _dict(_dict(raw.get("callback_query")).get("from"))


def display_name(raw: dict) -> str:
	name = str(raw.get("contact_name") or "").strip()
	if name:
		return name
	sender = _sender_dict(raw)
	full = " ".join(str(sender.get(k) or "").strip() for k in ("first_name", "last_name")).strip()
	return full or str(sender.get("username") or "")


def is_room(raw: dict) -> bool:
	if "is_room" in raw:
		return bool(raw["is_room"])
	meta = _dict(raw.get("telegram_meta"))
	chat_type = meta.get("chat_type") or _dict(_telegram_message(raw).get("chat")).get("type")
	return str(chat_type or "") in _TG_ROOM_TYPES


def is_mentioned(raw: dict) -> bool:
	meta = _dict(raw.get("telegram_meta"))
	return bool(raw.get("mentioned") or meta.get("mentioned") or meta.get("addressed"))


def language(raw: dict) -> str:
	return str(_sender_dict(raw).get("language_code") or "")


def build_payload(event, gateway, attachments: list[str], extra_fields=None) -> dict:
	"""What a Flow gets for a gateway message: who, where, what, media and reply context."""
	raw = parse_raw(event)
	message = _dict(raw.get("message"))
	context = _dict(message.get("context"))
	interactive = _dict(message.get("interactive"))
	reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
	sender = str(event.sender_id or "")
	received = getattr(event, "received_at", None)
	payload = {
		"gateway_event": event.name,
		"gateway": gateway.name,
		"provider": gateway.provider,
		"sender_id": sender,
		"wa_id": "",
		"display_name": display_name(raw),
		"conversation_id": event.conversation_id,
		"thread_id": event.thread_id,
		"message_id": event.provider_event_id,
		"message": event.message_text,
		"text": event.message_text,
		"message_type": normalize_message_type(raw),
		"kind": event_kind(raw),
		"attachments": list(attachments),
		"received_at": str(received) if received else "",
		"is_room": is_room(raw),
		"mentioned": is_mentioned(raw),
		"language": language(raw),
		"reply_to_message_id": str(context.get("id") or "") or None,
		"interactive_reply": {"id": reply.get("id"), "title": reply.get("title")} if reply else None,
	}
	if extra_fields is not None:
		merge_extras(payload, extra_fields(event, gateway, sender) or {})
	return payload


def _is_empty(value) -> bool:
	return value is None or value == "" or value == [] or value == {}


def merge_extras(payload: dict, extras: dict) -> None:
	"""Provider extras refine the generic keys: a provider value wins only when it is non-empty.

	An empty provider value (None, "", [], {}) never blanks a generic value that was already derived
	(``display_name``, ``language``, ``is_room``, ``mentioned``, ``kind``...). ``False`` and ``0`` are real values."""
	for key, value in extras.items():
		if key in payload and not _is_empty(payload[key]) and _is_empty(value):
			continue
		payload[key] = value
