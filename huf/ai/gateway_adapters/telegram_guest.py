# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram guest chat mode (Bot API 10.0, 2026-05-08). WP-8b.

What the Bot API documents (https://core.telegram.org/bots/api, "Guest Mode"):

* Guest mode lets a bot "receive certain messages and issue replies within chats they are not a member of".
* ``User.supports_guest_queries`` (Boolean, only returned by ``getMe``): the bot supports guest queries from
  chats it is not a member of.
* ``Update.guest_message`` (``Message``, optional): "New guest message". The bot uses
  ``Message.guest_query_id`` with ``answerGuestQuery`` to respond.
* ``Message.guest_query_id`` (String, optional): unique id of the guest query; if non-empty the message belongs
  to the chat where the guest bot was summoned, which "may not coincide with other existing bot chats sharing
  the same identifier" (so the chat id must NOT be keyed like a normal DM/room chat).
* ``Message.guest_bot_caller_user`` / ``guest_bot_caller_chat`` appear on a message SENT by a guest bot (the
  user/chat whose message triggered it); not needed for inbound.
* ``answerGuestQuery(guest_query_id: String, result: InlineQueryResult)`` -> ``SentGuestMessage``
  (``inline_message_id``: String). The reply is an inline-query-result object (e.g. ``InlineQueryResultArticle``
  with ``input_message_content``), NOT ``sendMessage`` (the bot is not a chat member).
* There is no ``GuestMessage`` / ``GuestQuery`` type. The docs state NO time window, content-type limit, or
  whether a reply may be delayed/long-running; only that replies need the query id. We therefore answer once,
  as soon as the agent finishes, and treat an API error as final (no retry loop).

``parse_update`` (telegram_inbound, not owned here) maps ``guest_message`` to kind ``"unsupported"``, so this
module registers on ``"unsupported"`` (chained to any prior handler) and on ``"guest_message"`` and reads the
raw update itself. ``ALLOWED_UPDATES`` in telegram_client does not yet list ``guest_message`` (coordinator).

Policy: guests are not paired users. Allowed ONLY when ``gateway.direct_policy == "Open"``; otherwise one short
"ask the owner" answer per guest (no agent run, no data). Rate limits per guest id and per chat. Allowed
messages go through ``ingest_gateway_event`` like a DM with ``telegram_meta.guest = true`` and the
``guest_query_id`` in ``raw_payload``; the pipeline must send replies through ``reply_for_guest`` when
``telegram_meta.guest`` is set.
"""

from __future__ import annotations

from typing import Any, Mapping

import frappe

from huf.ai.gateway_adapters import telegram_ingest as ing

OPEN_POLICY = "Open"
GUEST_CONV_PREFIX = "guest:"
DENIED_TEXT = "Sorry, I can't chat with guests here. Please ask my owner for access."
RATE_TEXT = "You're sending messages too quickly. Please try again in a minute."
PER_GUEST_LIMIT = 5
PER_CHAT_LIMIT = 20
WINDOW_SECONDS = 60
DENY_ONCE_SECONDS = 3600
_MAX_TEXT = 4096


def _map(value: Any) -> Mapping[str, Any]:
	return value if isinstance(value, Mapping) else {}


def parse_guest_update(update: Mapping[str, Any]) -> dict | None:
	"""Validate ``update["guest_message"]``; ``None`` if absent or malformed (missing ids = tampered)."""
	msg = _map(update.get("guest_message"))
	if not msg:
		return None
	query_id = str(msg.get("guest_query_id") or "")
	sender = _map(msg.get("from"))
	chat = _map(msg.get("chat"))
	update_id = str(update.get("update_id") or "")
	if not (query_id and update_id and sender.get("id") is not None and chat.get("id") is not None):
		return None
	if sender.get("is_bot"):
		return None
	return {
		"update_id": update_id,
		"guest_query_id": query_id,
		"guest_id": str(sender["id"]),
		"chat_id": str(chat["id"]),
		"message_id": str(msg.get("message_id") or ""),
		"text": str(msg.get("text") or msg.get("caption") or "")[:_MAX_TEXT],
		"display_name": " ".join(p for p in (sender.get("first_name"), sender.get("last_name")) if p)
		or str(sender.get("username") or ""),
	}


# -- counters (frappe cache; patched in tests) --------------------------------------------------


def _bump(key: str, ttl: int) -> int:
	cache = frappe.cache()
	redis_key = cache.make_key(key)
	count = int(cache.incrby(redis_key, 1))
	cache.expire(redis_key, ttl)
	return count


def _claim_once(key: str, ttl: int) -> bool:
	return bool(frappe.cache().set(key, 1, ex=ttl, nx=True))


def rate_limited(gateway_name: str, guest_id: str, chat_id: str) -> bool:
	guest = _bump(f"huf:tg_guest:{gateway_name}:g:{guest_id}", WINDOW_SECONDS)
	chat = _bump(f"huf:tg_guest:{gateway_name}:c:{chat_id}", WINDOW_SECONDS)
	return guest > PER_GUEST_LIMIT or chat > PER_CHAT_LIMIT


# -- reply ----------------------------------------------------------------------------------------


def answer_payload(guest_query_id: str, text: str, result_id: str = "") -> dict:
	"""``answerGuestQuery`` payload: an InlineQueryResultArticle carrying the text."""
	text = (text or "").strip()[:_MAX_TEXT] or "..."
	return {
		"guest_query_id": guest_query_id,
		"result": {
			"type": "article",
			"id": (result_id or guest_query_id)[:64],
			"title": text[:64],
			"input_message_content": {"message_text": text},
		},
	}


def reply_for_guest(client, guest_query_id: str, text: str, result_id: str = "") -> dict | None:
	"""Send the guest reply via ``answerGuestQuery``. Returns ``SentGuestMessage`` or ``None`` on API error.

	Single attempt: the docs give no retry/expiry semantics. ``client`` is a ``TelegramBotClient``.
	"""
	from huf.ai.gateway_adapters.telegram_client import TelegramApiError

	if not guest_query_id:
		return None
	try:
		return client.call("answerGuestQuery", answer_payload(guest_query_id, text, result_id))
	except TelegramApiError as exc:
		frappe.logger("huf").warning(f"Telegram guest reply failed: {client.redact(exc)}")
		return None


def guest_query_id_of(raw_payload: Mapping[str, Any]) -> str:
	"""Query id for a stored event's raw payload (``""`` when the event is not a guest message)."""
	return str(_map(_map(raw_payload).get("guest_message")).get("guest_query_id") or "")


def is_guest_event(raw_payload: Mapping[str, Any]) -> bool:
	return bool(_map(_map(raw_payload).get("telegram_meta")).get("guest"))


# -- handler --------------------------------------------------------------------------------------


def handle_guest(gateway, adapter, parsed, request) -> dict | None:
	update = getattr(parsed, "raw", None)
	g = parse_guest_update(update) if isinstance(update, Mapping) and "guest_message" in update else None
	if g is None:
		if isinstance(update, Mapping) and "guest_message" in update:
			return ing._ack("guest_message", "malformed guest message dropped")
		return None
	name = gateway.name
	if rate_limited(name, g["guest_id"], g["chat_id"]):
		if _claim_once(f"huf:tg_guest:{name}:rl:{g['guest_id']}", WINDOW_SECONDS):
			reply_for_guest(adapter.client, g["guest_query_id"], RATE_TEXT)
		return ing._ack("guest_message", "rate limited")
	if (getattr(gateway, "direct_policy", None) or "") != OPEN_POLICY:
		if _claim_once(f"huf:tg_guest:{name}:deny:{g['guest_id']}", DENY_ONCE_SECONDS):
			reply_for_guest(adapter.client, g["guest_query_id"], DENIED_TEXT)
		return ing._ack("guest_message", "guests not allowed by gateway policy")
	if not g["text"].strip():
		return ing._ack("guest_message", "no text")
	from huf.ai.gateway_service import ingest_gateway_event
	from huf.ai.gateway_webhook import touch_last_event

	raw = dict(update)
	raw["telegram_meta"] = {
		"update_kind": "guest_message",
		"guest": True,
		"guest_query_id": g["guest_query_id"],
		"chat_type": str(_map(_map(update["guest_message"]).get("chat")).get("type") or ""),
	}
	context = {
		"kind": "message",
		"sender_id": g["guest_id"],
		"conversation_id": GUEST_CONV_PREFIX + g["chat_id"],
		"thread_id": g["message_id"] or None,
		"message_text": g["text"],
		"is_room": False,
		"mentioned": True,
		"display_name": g["display_name"],
	}
	result = ingest_gateway_event(name, g["update_id"], context, verified_sender=True, raw_payload=raw)
	if not result.get("duplicate"):
		touch_last_event(gateway)
	return {"success": True, **result}
