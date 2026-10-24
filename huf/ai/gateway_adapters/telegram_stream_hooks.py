# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram streaming hooks (WP-6). Imported once from ``telegram_hooks``.

``agent_runner(event, gateway)`` returns a ``run_agent_sync``-compatible callable (or None to keep the
default). It is only consulted if ``gateway_service`` calls it (see the call-site note in the WP-6 report).
"""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def agent_runner(event, gateway):
	"""Streaming runner for private chats when the gateway enables ``telegram_streaming``; else None. Never raises."""
	try:
		from huf.ai.gateway_adapters import telegram_pipeline, telegram_stream
		from huf.ai.gateway_webhook import event_contact_name, get_gateway_adapter

		if not telegram_stream.streaming_enabled(telegram_stream.event_chat_type(event), gateway):
			return None
		adapter = get_gateway_adapter(gateway, event_contact_name(event))
		thread_id, _ = telegram_pipeline.reply_target(event)
		return telegram_stream.make_runner(
			telegram_pipeline.build_sender(adapter),
			event.conversation_id,
			event.name,
			gateway.name,
			thread_id=thread_id,
		)
	except Exception:
		return None


def _register_stop_handler():
	from huf.ai.gateway_adapters import telegram_ingest, telegram_stream

	telegram_ingest.register_update_handler("stopped_message_generation", telegram_stream.handle_stopped)
	# parse_update reports unknown update types as kind "unsupported"; route only our update there.
	previous = telegram_ingest._UPDATE_HANDLERS.get("unsupported")

	def unsupported(gateway, adapter, parsed, request):
		if isinstance(getattr(parsed, "raw", None), dict) and "stopped_message_generation" in parsed.raw:
			return telegram_stream.handle_stopped(gateway, adapter, parsed, request)
		return previous(gateway, adapter, parsed, request) if previous else None

	telegram_ingest.register_update_handler("unsupported", unsupported)


provider_hooks.register(PROVIDER, "agent_runner", agent_runner)
_register_stop_handler()
