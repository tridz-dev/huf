# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram voice-reply hooks (imported from ``telegram_hooks``)."""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def voice_reply(event, gateway, response, send_text):
	from huf.ai.gateway_adapters import telegram_voice

	return telegram_voice.deliver(event, gateway, response, send_text)


def voice_input(event) -> bool:
	from huf.ai.gateway_adapters import telegram_voice

	return telegram_voice.is_voice_input(event)


provider_hooks.register(PROVIDER, "voice_reply", voice_reply)
provider_hooks.register(PROVIDER, "voice_input", voice_input)
