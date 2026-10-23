# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Wires Secretary-mode agent flow (WP-B). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_business as biz
from huf.ai.gateway_adapters import telegram_business_agent as agent
from huf.ai.gateway_adapters import telegram_ingest as ing

biz.register_business_policy(agent.policy)
biz.register_draft_producer(agent.draft_producer)

for _kind in ("business_message",):
	ing.register_update_handler(_kind, agent.chain_business_message(ing._UPDATE_HANDLERS.get(_kind)))

_previous_message = ing._UPDATE_HANDLERS.get("message")


def _message(gateway, adapter, parsed, request=None):
	handled = agent.handle_owner_message(gateway, adapter, parsed, request)
	if handled is not None:
		return handled
	return _previous_message(gateway, adapter, parsed, request) if _previous_message else None


ing.register_update_handler("message", _message)

if not getattr(biz.handle_draft_callback, "_huf_wp_b", False):
	biz.handle_draft_callback = agent.wrap_draft_callback(biz.handle_draft_callback)
