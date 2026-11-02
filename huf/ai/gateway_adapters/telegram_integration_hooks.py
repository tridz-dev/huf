# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Cross-feature Telegram hooks owned by the coordinator (conversation keys, guest replies)."""

from __future__ import annotations

import json
from typing import Any

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def _raw(event: Any) -> dict:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return {}
	return raw if isinstance(raw, dict) else {}


def conversation_key(event: Any) -> str | None:
	"""One agent conversation per chat, or per forum/private topic (not per inbound message)."""
	from huf.ai.gateway_adapters import telegram_pipeline, telegram_threads

	chat_id = getattr(event, "conversation_id", "") or ""
	if not chat_id:
		return None
	return telegram_threads.conversation_key(chat_id, telegram_pipeline.forum_thread_id(event))


def guest_reply(event: Any, gateway: Any, response: str) -> dict | None:
	"""Answer a guest-mode message through ``answerGuestQuery``; None when the event is not a guest event."""
	from huf.ai.gateway_adapters import telegram_guest
	from huf.ai.gateway_webhook import get_gateway_adapter

	raw = _raw(event)
	if not telegram_guest.is_guest_event(raw):
		return None
	query_id = telegram_guest.guest_query_id_of(raw)
	adapter = get_gateway_adapter(gateway)
	sent = telegram_guest.reply_for_guest(adapter.client, query_id, response) if query_id else None
	if sent is None:
		event.db_set({"status": "Failed", "error_message": "Guest reply could not be delivered"})
		return {"event_name": event.name, "status": "Failed", "guest": True}
	event.db_set({"status": "Succeeded", "delivery_error": ""})
	return {
		"event_name": event.name,
		"status": "Succeeded",
		"agent_run_id": getattr(event, "agent_run", None),
		"guest": True,
	}


provider_hooks.register(PROVIDER, "conversation_key", conversation_key)
provider_hooks.register(PROVIDER, "guest_reply", guest_reply)
