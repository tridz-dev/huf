# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt
# ruff: noqa: I001  (import order is significant: hook registrations override earlier ones)

"""Registers the Telegram guest-mode update handler (WP-8b). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_guest as guest, telegram_ingest as ing


def _chain(previous):
	def handler(gateway, adapter, parsed, request):
		handled = guest.handle_guest(gateway, adapter, parsed, request)
		if handled is None and previous is not None:
			return previous(gateway, adapter, parsed, request)
		return handled

	return handler


# parse_update reports Update.guest_message as kind "unsupported"; the handler only acts on raw guest_message.
ing.register_update_handler("guest_message", guest.handle_guest)
ing.register_update_handler("unsupported", _chain(ing._UPDATE_HANDLERS.get("unsupported")))
