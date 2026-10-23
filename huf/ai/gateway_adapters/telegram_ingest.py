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
_BUSINESS = {
	"business_message",
	"edited_business_message",
	"deleted_business_messages",
	"business_connection",
}
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
		try:
			from huf.ai.gateway_adapters import telegram_groups

			telegram_groups.apply_membership_change(gateway, parsed)
		except Exception:
			frappe.logger("huf").warning("Telegram membership change could not be applied", exc_info=True)
		return _ack(parsed.kind, "non-private membership change recorded")
	if parsed.bot_blocked:
		if svc._sender_is_known(gateway, parsed.sender_id):
			svc._record_opt_out(gateway, parsed.sender_id, parsed.display_name)
			return _ack("bot_blocked", "sender marked unsendable")
		return _ack("bot_blocked", "unknown sender; nothing stored")
	svc._record_opt_in(gateway, parsed.sender_id)
	return _ack("bot_unblocked", "sender restored")


_UPDATE_HANDLERS: dict[str, Any] = {}
_ADDRESSING_KINDS = ("message", "edited_message")


def _with_addressing(gateway, adapter, parsed: TelegramUpdate) -> TelegramUpdate:
	"""Group messages: ``mentioned`` means addressed to THIS bot (its @mention, text_mention, /cmd@bot, a reply
	to one of its messages), not just any mention entity. The bot identity is the token's numeric id plus a
	cached getMe username; with no username only id-based signals (reply to the bot, text_mention) count.
	"""
	if parsed.kind not in _ADDRESSING_KINDS or not parsed.is_room or parsed.is_channel:
		return parsed
	msg = (parsed.raw or {}).get(parsed.kind)
	if not isinstance(msg, dict):
		return parsed
	try:
		from huf.ai.gateway_adapters import telegram_modes_hooks as mh
		from huf.ai.gateway_adapters import telegram_threads as th

		addressed = th.is_addressed_to_bot(msg, mh._bot_username(adapter, gateway), mh._own_id(adapter))
	except Exception:
		frappe.logger("huf").warning("Telegram addressing check failed", exc_info=True)
		return replace(
			parsed, mentioned=False
		)  # fail closed: an unverifiable message is not addressed to the bot
	return replace(parsed, mentioned=addressed)


_DEDUP_TTL = 600
_DEDUP_WARNED = False


def _release_delivery(gateway_name: str, update_id: Any) -> None:
	try:
		frappe.cache().delete_value(f"huf_tg_upd:{gateway_name}:{update_id}")
	except Exception:
		pass


def _first_delivery(gateway_name: str, update_id: Any) -> bool:
	"""True the first time this update id is seen for the gateway (Telegram retries are acked, not re-run)."""
	if not update_id:
		return True
	key = f"huf_tg_upd:{gateway_name}:{update_id}"
	try:
		cache = frappe.cache()
		make_key = getattr(cache, "make_key", None)
		if make_key is not None and hasattr(cache, "set"):
			return bool(cache.set(make_key(key), 1, nx=True, ex=_DEDUP_TTL))
		if cache.get_value(key):
			return False
		cache.set_value(key, 1, expires_in_sec=_DEDUP_TTL)
	except Exception:
		global _DEDUP_WARNED
		if not _DEDUP_WARNED:
			_DEDUP_WARNED = True
			frappe.logger("huf").warning(
				"Telegram update de-duplication cache failed; failing open (duplicate updates may be processed)",
				exc_info=True,
			)
	return True


def register_update_handler(key: str, fn) -> None:
	"""Register ``fn(gateway, adapter, parsed, request) -> dict | None`` for an update kind or category.

	``key`` is a Telegram update kind (``inline_query``, ``chat_join_request``, ``business_message`` ...) or a
	``classify()`` category. A non-None return is the webhook response; None falls through to the default ack.
	"""
	_UPDATE_HANDLERS[key] = fn


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
	raw_key = next((k for k in (parsed.raw or {}) if k != "update_id"), "")
	claimed = False
	for key in dict.fromkeys((parsed.kind, raw_key, category)):
		handler = _UPDATE_HANDLERS.get(key)
		if handler is None:
			continue
		# Message ingestion is deduplicated by ingest_gateway_event; this guards handlers that short-circuit.
		# Claim the update ONCE (several keys can match one update), and keep the claim only if a handler answers.
		if not claimed:
			if not _first_delivery(gateway.name, parsed.update_id):
				return _ack(parsed.kind, "duplicate update ignored")
			claimed = True
		try:
			handled = handler(gateway, adapter, parsed, request)
		except Exception:
			_release_delivery(gateway.name, parsed.update_id)  # let Telegram's retry run the handler again
			raise
		if handled is not None:
			return handled
	if claimed:
		# No handler answered: the update continues to normal ingestion, which has its own dedup, and a failed
		# ingest must stay retryable.
		_release_delivery(gateway.name, parsed.update_id)
	if category in ("membership", "business", "other"):
		# Unhandled kinds (join/guard, business, inline); acked so Telegram never retries.
		return _ack(parsed.kind)
	if parsed.kind == "message_reaction_count":
		return _ack(parsed.kind)
	edit_message_id = ""
	if parsed.kind == "callback_query":
		from huf.ai.gateway_adapters import telegram_buttons

		payload = adapter.verify_callback_data(parsed.callback_data, parsed.chat_id)
		from huf.ai.gateway_adapters import telegram_business

		business = telegram_business.handle_draft_callback(adapter, parsed, payload)
		if business is not None:
			return _ack("callback_query", f"business draft {business.get('result', '')}")
		decision = telegram_buttons.handle_callback(parsed, payload, adapter.sender, gateway.name)
		if decision["action"] != "ingest":
			frappe.logger("huf").info(
				f"Telegram gateway {gateway.name}: callback_query {decision['reason']} (update {parsed.update_id})"
			)
			return _ack("callback_query", decision["reason"])
		edit_message_id = decision["edit_message_id"]
		parsed = replace(parsed, text=decision["text"])
	parsed = _with_addressing(gateway, adapter, parsed)
	try:
		event = to_event(parsed, ())
	except ValueError:
		return _ack(parsed.kind, "missing identifiers; dropped")
	if event is None:
		return _ack(parsed.kind)
	raw = dict(event.raw_payload)
	raw["telegram_meta"] = {
		**_meta(parsed),
		"callback_data": parsed.text if parsed.kind == "callback_query" else "",
		**({"edit_message_id": edit_message_id} if edit_message_id else {}),
	}
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


def _typing_failure_kind(exc: Exception) -> str:
	if getattr(exc, "blocked_by_user", False):
		return "blocked"
	if getattr(exc, "chat_not_found", False):
		return "chat_not_found"
	if getattr(exc, "flood_control", False):
		return "flood_control"
	code = getattr(exc, "error_code", None)
	return f"api_{code}" if code else type(exc).__name__


def _start_keepalive(gateway, sender, chat_id, thread) -> None:
	"""Keep ``typing`` alive until the reply starts (best effort). Stops once a draft shows real text.

	The empty "Thinking" draft placeholder does not count: it is not a reliable visible indicator."""
	try:
		from huf.ai.gateway_adapters import telegram_stream as ts
		from huf.ai.gateway_adapters import telegram_typing_keepalive as ka
		from huf.ai.gateway_adapters import telegram_typing_metrics as tm

		name = gateway.name
		import frappe

		site = getattr(frappe.local, "site", None)  # captured here: the thread has no site context

		def tick() -> None:
			try:
				sender.send_chat_action(chat_id, "typing", thread_id=thread)
			except Exception as exc:
				tm.record_error(name, _typing_failure_kind(exc))
				raise
			tm.record_keepalive_tick(name)

		ka.start(
			ka.key_for(name, chat_id, thread),
			tick,
			lambda: bool(ts.StreamState(name, chat_id).get().get("draft_text")),
			site=site,
		)
	except Exception:
		pass


def send_typing_for_event(event, gateway) -> bool:
	"""Telegram typing indicator (sendChatAction) for the inbound update. The only typing implementation.

	Gate: ``Gateway.typing_indicator`` (off = no call). Addressed rule: private chats always; groups only when
	the message mentions/commands the bot (or ``mention_required`` is off). Thread: the forum topic or private
	topic id only (``thread_id_for_reply``), never a plain reply-chain id (Telegram rejects it). Best effort:
	never raises, never fails the run. Failures log at WARNING, successes at DEBUG; counters (last sent, 24h
	count, last error type) live in the cache for the Overview (``telegram_typing_metrics``).
	"""
	from huf.ai.gateway_adapters import telegram_typing_metrics as tm
	from huf.ai.gateway_adapters.telegram_threads import thread_id_for_reply

	chat_id = ""
	try:
		enabled = getattr(gateway, "typing_indicator", None)
		if enabled is not None and not int(enabled):
			return False
		raw = _raw(event)
		meta = raw.get("telegram_meta") or {}
		chat_type = meta.get("chat_type") or "private"
		if chat_type == "channel":
			return False
		msg = _message(raw) or (raw.get("callback_query") or {}).get("message") or {}
		if chat_type != "private" and gateway.get("mention_required"):
			ents = list(msg.get("entities") or []) + list(msg.get("caption_entities") or [])
			if not any(e.get("type") in ("mention", "bot_command", "text_mention") for e in ents):
				return False
		chat_id = str(event.conversation_id or "")
		thread = thread_id_for_reply(msg)
	except Exception:
		frappe.logger("huf").warning("Telegram typing skipped: inbound update unreadable", exc_info=True)
		return False
	try:
		from huf.ai.gateway_webhook import get_gateway_adapter

		sender = get_gateway_adapter(gateway).sender
		sender.send_chat_action(chat_id, "typing", thread_id=thread)
	except Exception as exc:
		kind = _typing_failure_kind(exc)
		tm.record_error(gateway.name, kind)
		frappe.logger("huf").warning(f"Telegram typing failed chat={chat_id} action=typing type={kind}")
		return False
	tm.record_sent(gateway.name, chat_id)
	_start_keepalive(gateway, sender, chat_id, thread)
	suffix = f" thread={thread}" if thread else ""
	frappe.logger("huf").debug(f"Telegram typing sent chat={chat_id} action=typing{suffix}")
	return True


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
