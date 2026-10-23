# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram inbound hooks (WP-1c). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters import telegram_ingest as ing

PROVIDER = "Telegram"


def inbound_kind(event):
	"""Media type of the inbound message (None = no media). Update classification: ``telegram_ingest.classify``."""
	return ing.inbound_media_type(event)


def typing(event, gateway):
	"""Owner of the Telegram ``typing`` hook. The gate and addressed rule live in ``send_typing_for_event``."""
	ing.send_typing_for_event(event, gateway)


def reply_finished(event, gateway):
	"""Stop the typing keepalive for this chat (reply starting, suppressed or failed)."""
	from huf.ai.gateway_adapters import telegram_typing_keepalive as ka
	from huf.ai.gateway_adapters.telegram_threads import thread_id_for_reply

	try:
		raw = ing._raw(event)
		msg = ing._message(raw) or (raw.get("callback_query") or {}).get("message") or {}
		ka.stop(ka.key_for(gateway.name, str(event.conversation_id or ""), thread_id_for_reply(msg)))
	except Exception:
		pass


def mark_read_typing(adapter, provider_event_id, chat_id=None, thread_id=None):
	"""Telegram has no read receipts; typing needs a chat id (``provider_event_id`` is an update id)."""
	if not chat_id:
		return False
	return bool(adapter.send_typing(chat_id, "typing", thread_id))


provider_hooks.register(PROVIDER, "ingest_update", ing.handle_update)
provider_hooks.register(PROVIDER, "inbound_kind", inbound_kind)
provider_hooks.register(PROVIDER, "media_save", ing.save_media)
provider_hooks.register(PROVIDER, "typing", typing)
provider_hooks.register(PROVIDER, "mark_read_typing", mark_read_typing)
provider_hooks.register(PROVIDER, "extra_event_fields", ing.extra_fields)
provider_hooks.register(PROVIDER, "reply_finished", reply_finished)
