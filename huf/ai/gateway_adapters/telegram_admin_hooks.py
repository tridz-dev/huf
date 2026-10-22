# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the admin cockpit update handlers (WP-9). Imported once from ``telegram_hooks``.

The handlers return None for anything that is not a cockpit command / ``adm:`` callback, so the normal
ingest path (buttons, agent routing) keeps working. A handler already registered for the same key is
chained, not replaced.
"""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_ingest as ing


def _chain(key: str, fn) -> None:
	previous = ing._UPDATE_HANDLERS.get(key)
	if previous is None:
		ing.register_update_handler(key, fn)
		return

	def chained(gateway, adapter, parsed, request):
		handled = fn(gateway, adapter, parsed, request)
		return handled if handled is not None else previous(gateway, adapter, parsed, request)

	ing.register_update_handler(key, chained)


def handle_message(gateway, adapter, parsed, request):
	from huf.ai import telegram_admin

	return telegram_admin.handle_message(gateway, adapter, parsed, request)


def handle_callback(gateway, adapter, parsed, request):
	from huf.ai import telegram_admin

	return telegram_admin.handle_callback(gateway, adapter, parsed, request)


_chain("message", handle_message)
_chain("callback_query", handle_callback)
