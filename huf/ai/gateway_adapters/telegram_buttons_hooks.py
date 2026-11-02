# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram button hooks (WP-5). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def agent_instructions(gateway=None):
	from huf.ai.gateway_adapters import telegram_buttons

	return telegram_buttons.AGENT_INSTRUCTIONS


provider_hooks.register(PROVIDER, "agent_instructions", agent_instructions)
