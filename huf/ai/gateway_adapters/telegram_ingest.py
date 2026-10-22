# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram inbound handling beyond plain messages (WhatsApp-parity ingest, hook-driven).

``handle_update`` runs from ``handle_gateway_webhook`` BEFORE ``normalize_inbound``: it parses the
verified update, classifies it, and either handles it (ack 200, never retried) or ingests it as a
Gateway Event through the normal ``ingest_gateway_event`` path. Returns ``None`` to fall through to the
generic path (unparseable body).

Bot blocked/unblocked reuses the existing "Opted out" access-entry state (the same state outbound
``is_opted_out`` checks), so a blocked user is unsendable and is restored when they unblock.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import frappe

from huf.ai.gateway_adapters.telegram_inbound import TelegramUpdate, media_refs, to_event

# Bot API getFile hard limit.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024

_MEMBERSHIP = {"my_chat_member", "chat_member", "chat_join_request"}
_BUSINESS = {"business_message", "edited_business_message", "deleted_business_messages", "business_connection"}
_MEDIA_TYPE = {
	"photo": "image",
	"document": "document",
	"voice": "audio",
	"audio": "audio",
	"video": "video",
	"video_note": "video",
	"animation": "video",
	"sticker": "sticker",
}


def classify(parsed: TelegramUpdate) -> str:
	"""message / callback / reaction / membership / business / other."""
	kind = parsed.kind
	if kind in ("message", "edited_message", "channel_post", "edited_channel_post"):
		return "message"
	if kind == "callback_query":
		return "callback"
	if kind in ("message_reaction", "message_reaction_count"):
		return "reaction"
	if kind in _MEMBERSHIP:
		return "membership"
	if kind in _BUSINESS:
		return "business"
	return "other"


def _ack(kind: str, note: str = "") -> dict:
	return {"success": True, "ignored": kind, "note": note}


def _meta(parsed: TelegramUpdate) -> dict[str, Any]:
	meta = {
		"update_kind": parsed.kind,
		"chat_type": parsed.chat_type,
		"is_bot": parsed.is_bot,
		"message_thread_id": parsed.message_thread_id,
		"business_connection_id": parsed.business_connection_id,
		"sender_business_bot": parsed.sender_business_bot,
		"start_payload": parsed.start_payload,
		"callback_query_id": parsed.callback_query_id,
	}
	return {k: v for k, v in meta.items() if v not in ("", False, None)}


def _handle_block_change(gateway, parsed: TelegramUpdate) -> dict:
	from huf.ai import gateway_service as svc

	if parsed.chat_type != "private" or not parsed.sender_id:
		return _ack(parsed.kind, "non-private membership change recorded only")
	if parsed.bot_blocked:
		if svc._sender_is_known(gateway, parsed.sender_id):
			svc._record_opt_out(gateway, parsed.sender_id, parsed.display_name)
			return _ack("bot_blocked", "sender marked unsendable")
		return _ack("bot_blocked", "unknown sender; nothing stored")
	svc._record_opt_in(gateway, parsed.sender_id)
	return _ack("bot_unblocked", "sender restored")


def handle_update(gateway, adapter, request) -> dict | None:
	from huf.ai.gateway_service import ingest_gateway_event
	from huf.ai.gateway_webhook import _event_context, touch_last_event

	try:
		parsed = adapter.parse_update(request)
	except ValueError:
		return None
	category = classify(parsed)
	if parsed.bot_blocked or parsed.bot_unblocked:
		return _handle_block_change(gateway, parsed)
	if category in ("membership", "business", "other"):
		# Handled by later work packages (join/guard, business, inline); acked so Telegram never retries.
		return _ack(parsed.kind)
	if parsed.kind == "message_reaction_count":
		return _ack(parsed.kind)
	if parsed.kind == "callback_query":
		payload = adapter.verify_callback_data(parsed.callback_data, parsed.chat_id)
		if payload is None:
			frappe.logger("huf").warning(
				f"Telegram gateway {gateway.name}: dropped callback_query with invalid signature "
				f"(update {parsed.update_id})"
			)
			return _ack("callback_query", "invalid signature; dropped")
		parsed = replace(parsed, text=payload)
	try:
		event = to_event(parsed, ())
	except ValueError:
		return _ack(parsed.kind, "missing identifiers; dropped")
	if event is None:
		return _ack(parsed.kind)
	raw = dict(event.raw_payload)
	raw["telegram_meta"] = {**_meta(parsed), "callback_data": parsed.text if parsed.kind == "callback_query" else ""}
	result = ingest_gateway_event(
		gateway.name,
		event.provider_event_id,
		_event_context(event),
		verified_sender=True,
		raw_payload=raw,
	)
	if not result.get("duplicate"):
		touch_last_event(gateway)
	return {"success": True, **result}


# -- event-row helpers (hooks) ---------------------------------------------------------------


def _raw(event) -> dict:
	raw = event.get("raw_payload") if hasattr(event, "get") else getattr(event, "raw_payload", None)
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	return raw if isinstance(raw, dict) else {}


def _message(raw: dict) -> dict:
	for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
		if isinstance(raw.get(key), dict):
			return raw[key]
	return {}


def inbound_media_type(event) -> str | None:
	refs = media_refs(_message(_raw(event)))
	return _MEDIA_TYPE.get(refs[0]["kind"]) if refs else None


def extra_fields(event, gateway, sender) -> dict:
	raw = _raw(event)
	meta = raw.get("telegram_meta") or {}
	msg = _message(raw) or (raw.get("callback_query") or {}).get("message") or {}
	chat = msg.get("chat") or {}
	return {
		k: v
		for k, v in {
			"telegram_user_id": sender,
			"telegram_chat_id": str(chat.get("id") or event.conversation_id or ""),
			"telegram_chat_type": meta.get("chat_type") or chat.get("type") or "",
			"message_thread_id": meta.get("message_thread_id") or "",
			"business_connection_id": meta.get("business_connection_id") or "",
			"sender_is_bot": bool(meta.get("is_bot")),
			"callback_query_id": meta.get("callback_query_id") or "",
			"callback_data": meta.get("callback_data") or "",
		}.items()
		if v not in ("", None)
	}


def send_typing_for_event(event, gateway) -> bool:
	"""sendChatAction typing for a private chat or an addressed group message. Best effort."""
	try:
		meta = _raw(event).get("telegram_meta") or {}
		chat_type = meta.get("chat_type") or "private"
		if chat_type in ("channel",):
			return False
		if chat_type != "private" and gateway.get("mention_required"):
			msg = _message(_raw(event))
			ents = list(msg.get("entities") or []) + list(msg.get("caption_entities") or [])
			if not any(e.get("type") in ("mention", "bot_command", "text_mention") for e in ents):
				return False
		from huf.ai.gateway_webhook import get_gateway_adapter

		thread = meta.get("message_thread_id") or None
		return bool(get_gateway_adapter(gateway).send_typing(event.conversation_id, "typing", thread))
	except Exception:
		return False


def save_media(event, gateway) -> list[str]:
	"""Save inbound attachments as private Files on the event. Never raises; oversize is skipped + logged."""
	saved: list[str] = []
	try:
		raw = _raw(event)
		refs = media_refs(_message(raw))
		if not refs:
			return saved
		adapter = None
		for ref in refs:
			size = int(ref.get("file_size") or 0)
			if size > MAX_DOWNLOAD_BYTES:
				frappe.logger("huf").warning(
					f"Telegram media skipped: {ref['kind']} is {size} bytes (Bot API getFile limit 20MB)"
				)
				continue
			doc_name = (ref.get("file_doc") or "").strip()
			if doc_name and frappe.db.exists("File", doc_name):
				saved.append(frappe.db.get_value("File", doc_name, "file_url"))
				continue
			if adapter is None:
				from huf.ai.gateway_webhook import get_gateway_adapter

				adapter = get_gateway_adapter(gateway)
			content, file_path = adapter.client.download_file(ref["file_id"])
			if len(content) > MAX_DOWNLOAD_BYTES:
				continue
			name = ref["filename"] or file_path.rsplit("/", 1)[-1] or f"{ref['kind']}-{ref['file_unique_id']}"
			name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name).lstrip(".")[:100]
			file_doc = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": name or f"{ref['kind']}-{ref['file_unique_id']}",
					"content": content,
					"attached_to_doctype": "Gateway Event",
					"attached_to_name": event.name,
					"is_private": 1,
				}
			).insert(ignore_permissions=True)
			saved.append(file_doc.file_url)
	except Exception as exc:
		from huf.ai.gateway_service import _redact_error_text

		frappe.logger("huf").warning(f"Telegram media download skipped: {_redact_error_text(str(exc))}")
	return saved
