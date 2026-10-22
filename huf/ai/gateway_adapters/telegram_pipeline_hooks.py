# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram reply-pipeline hooks (imported from ``telegram_hooks``)."""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def send_reply(event, gateway, agent_run_id, text):
	from huf.ai import gateway_service

	return gateway_service._send_telegram_reply(event, gateway, agent_run_id, text)


def send_parts(gateway, event, parts, quote):
	from huf.ai.gateway_adapters import telegram_pipeline

	return telegram_pipeline.send_parts(gateway, event, parts, quote)


def attempt_reply_parts(event, gateway, parts, attempt):
	from huf.ai.gateway_adapters import telegram_pipeline

	return telegram_pipeline.attempt_parts(event, gateway, parts, attempt)


def send_errors():
	from huf.ai.gateway_adapters.telegram_client import TelegramApiError
	from huf.ai.gateway_adapters.telegram_pipeline import TelegramPartsError

	return (TelegramApiError, TelegramPartsError)


def error_text(exc):
	from huf.ai.gateway_adapters import telegram_hooks
	from huf.ai.gateway_adapters.telegram_pipeline import TelegramPartsError

	return telegram_hooks.error_text(exc.cause if isinstance(exc, TelegramPartsError) else exc)


def reply_target(event):
	from huf.ai.gateway_adapters import telegram_pipeline

	return telegram_pipeline.reply_target(event)


def recover_reply_parts(response):
	from huf.ai.gateway_adapters import telegram_pipeline

	return telegram_pipeline.make_parts(response)


def typing(event, gateway):
	from huf.ai.gateway_adapters import telegram_pipeline

	telegram_pipeline.send_typing(gateway, event)


for _name, _fn in (
	("send_reply", send_reply), ("send_parts", send_parts), ("attempt_reply_parts", attempt_reply_parts),
	("send_errors", send_errors), ("error_text", error_text), ("reply_target", reply_target),
	("recover_reply_parts", recover_reply_parts), ("typing", typing),
):
	provider_hooks.register(PROVIDER, _name, _fn)
