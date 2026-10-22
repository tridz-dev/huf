# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram threads, topics, group addressing and ephemeral commands (WP-8e, R9). Pure helpers, no Frappe.

Bot API facts (core.telegram.org/bots/api, Bot API 10.x):

* ``message_thread_id`` identifies a forum topic in supergroups AND a topic in private chats of bots with
  topic mode enabled (``getMe.has_topics_enabled``; ``allows_users_to_create_topics``). Every send/draft/
  chat-action method accepts it. ``is_topic_message`` is true for messages inside a topic.
* In non-forum supergroups ``message_thread_id`` also appears on plain reply chains (``is_topic_message``
  absent); sending it back fails with "message thread not found", so replies only carry it for real topics.
* The General topic of a forum has no ``message_thread_id``; omit it.
* Ephemeral commands (``BotCommand.is_ephemeral``) arrive as messages with ``ephemeral_message_id`` /
  ``receiver_user``; the reply must use ``ephemeral_message_parameters.receiver_user_id`` and may quote with
  ``reply_parameters.ephemeral_message_id``.
"""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.gateway_adapters.telegram_inbound import _utf16_slice

PRIVATE = "private"


def _map(value: Any) -> Mapping[str, Any]:
	return value if isinstance(value, Mapping) else {}


def conversation_key(chat_id: Any, thread_id: Any = None) -> str:
	"""Agent conversation key: one conversation per chat, or per topic when a thread id is present."""
	chat = str(chat_id or "").strip()
	thread = str(thread_id or "").strip()
	if not chat:
		return ""
	return f"{chat}:{thread}" if thread and thread != "0" else chat


def thread_id_for_reply(message: Mapping[str, Any]) -> str | None:
	"""Thread id a reply to ``message`` must carry (None = send without ``message_thread_id``)."""
	msg = _map(message)
	if msg.get("message_thread_id") is None:
		return None
	thread = str(msg["message_thread_id"])
	if msg.get("is_topic_message") or _map(msg.get("chat")).get("type") == PRIVATE:
		return thread
	return None


def with_thread(payload: dict[str, Any], thread_id: Any) -> dict[str, Any]:
	"""Return ``payload`` with ``message_thread_id`` set when a thread id is given."""
	if thread_id not in (None, "", "0", 0):
		payload["message_thread_id"] = int(thread_id)
	return payload


def is_ephemeral(message: Mapping[str, Any]) -> bool:
	msg = _map(message)
	return msg.get("ephemeral_message_id") is not None or bool(msg.get("receiver_user"))


def ephemeral_reply_params(message: Mapping[str, Any]) -> dict[str, Any]:
	"""Extra send params to answer an ephemeral command privately ({} when the message is not ephemeral)."""
	msg = _map(message)
	if not is_ephemeral(msg):
		return {}
	receiver = _map(msg.get("receiver_user")).get("id") or _map(msg.get("from")).get("id")
	if receiver is None:
		return {}
	params: dict[str, Any] = {"ephemeral_message_parameters": {"receiver_user_id": int(receiver)}}
	if msg.get("ephemeral_message_id") is not None:
		params["reply_parameters"] = {"ephemeral_message_id": int(msg["ephemeral_message_id"])}
	return params


def is_addressed_to_bot(message: Mapping[str, Any], bot_username: str, bot_id: Any = None) -> bool:
	"""Private chats always; groups need an @mention / text_mention, a reply to our bot, or ``/cmd@bot``."""
	msg = _map(message)
	if _map(msg.get("chat")).get("type") == PRIVATE:
		return True
	uname = str(bot_username or "").lstrip("@").lower()
	bid = str(bot_id) if bot_id not in (None, "") else ""
	replied = _map(msg.get("reply_to_message"))
	rfrom = _map(replied.get("from"))
	if rfrom and ((bid and str(rfrom.get("id")) == bid) or (uname and str(rfrom.get("username", "")).lower() == uname)):
		return True
	for source, key in (("text", "entities"), ("caption", "caption_entities")):
		text = str(msg.get(source) or "")
		for ent in msg.get(key) or []:
			ent = _map(ent)
			etype = ent.get("type")
			if etype == "text_mention":
				if bid and str(_map(ent.get("user")).get("id")) == bid:
					return True
				continue
			if etype not in ("mention", "bot_command"):
				continue
			chunk = _utf16_slice(text, int(ent.get("offset", 0)), int(ent.get("length", 0))).lower()
			if etype == "mention" and uname and chunk == "@" + uname:
				return True
			if etype == "bot_command" and uname and chunk.endswith("@" + uname):
				return True
	return False


def create_topic_payload(chat_id: Any, name: str, *, icon_color: int | None = None, icon_custom_emoji_id: str | None = None) -> dict:
	"""``createForumTopic`` payload (supergroups need can_manage_topics; private chats need topic mode)."""
	name = str(name or "").strip()
	if not 1 <= len(name) <= 128:
		raise ValueError("Topic name must be 1-128 characters")
	payload: dict[str, Any] = {"chat_id": chat_id, "name": name}
	if icon_color is not None:
		payload["icon_color"] = int(icon_color)
	if icon_custom_emoji_id:
		payload["icon_custom_emoji_id"] = icon_custom_emoji_id
	return payload


def create_topic(client: Any, chat_id: Any, name: str, **kw: Any) -> Any:
	return client.call("createForumTopic", create_topic_payload(chat_id, name, **kw))
