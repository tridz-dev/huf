# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt
# ruff: noqa: I001  (import order is significant: hook registrations override earlier ones)

"""Registers the group / join-request update handlers (WP-8c). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_groups as groups, telegram_ingest as ing


def _chained(fn, previous):
	"""``previous`` (another module's handler for the same key) gets the update when ``fn`` declines it."""

	def handler(gateway, adapter, parsed, request):
		handled = fn(gateway, adapter, parsed, request)
		if handled is None and previous is not None:
			return previous(gateway, adapter, parsed, request)
		return handled

	return handler


# ``parse_update`` has no branch for chat_join_request yet (kind == "unsupported"), so the join handler is
# also keyed "unsupported"; it returns None for anything that is not a join request.
ing.register_update_handler("chat_join_request", groups.handle_join_request)
ing.register_update_handler(
	"unsupported", _chained(groups.handle_join_request, ing._UPDATE_HANDLERS.get("unsupported"))
)
for _key in ("chat_member", "my_chat_member"):
	ing.register_update_handler(_key, _chained(groups.handle_membership, ing._UPDATE_HANDLERS.get(_key)))
ing.register_update_handler(
	"message", _chained(groups.handle_service_message, ing._UPDATE_HANDLERS.get("message"))
)
