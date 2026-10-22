# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram agent-context hook (WP-C). Imported last from ``telegram_hooks`` so it overrides buttons."""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def agent_instructions(gateway=None):
	from huf.ai.gateway_adapters import telegram_agent_context

	return telegram_agent_context.build_instructions(gateway)


provider_hooks.register(PROVIDER, "agent_instructions", agent_instructions)
