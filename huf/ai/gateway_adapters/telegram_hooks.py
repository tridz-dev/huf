# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram provider hooks (skeleton). Later work packages add one import line per module below.

Only pure hooks live here; pipeline hooks (send_reply, typing, callback, media_save) stay
unregistered until their work package lands, so call sites keep the generic behaviour.
"""

from __future__ import annotations

from huf.ai.gateway_adapters import provider_hooks

PROVIDER = "Telegram"


def error_text(exc: BaseException) -> str:
	from huf.ai.gateway_adapters.telegram_client import TelegramApiError

	if isinstance(exc, TelegramApiError):
		if exc.blocked_by_user:
			return "Telegram delivery failed: the user blocked the bot"
		if exc.chat_not_found:
			return "Telegram delivery failed: chat not found"
		if exc.flood_control:
			return "Telegram delivery failed: rate limited"
		return f"Telegram delivery failed: {exc.description}"
	return str(exc) or "Telegram delivery failed"


def normalize_sender(entry_type: str, external_id) -> str:
	return str(external_id)


def consent_required() -> bool:
	return False


provider_hooks.register(PROVIDER, "error_text", error_text)
provider_hooks.register(PROVIDER, "normalize_sender", normalize_sender)
provider_hooks.register(PROVIDER, "consent_required", consent_required)
import huf.ai.gateway_adapters.telegram_pipeline_hooks  # noqa: E402,F401  (WP-1b)
import huf.ai.gateway_adapters.telegram_ingest_hooks  # noqa: E402,F401  (WP-1c)
import huf.ai.gateway_adapters.telegram_voice_hooks  # noqa: E402,F401  (WP-7)
import huf.ai.gateway_adapters.telegram_buttons_hooks  # noqa: E402,F401  (WP-5)
import huf.ai.gateway_adapters.telegram_inline_hooks  # noqa: E402,F401  (WP-8a)
import huf.ai.gateway_adapters.telegram_guest_hooks  # noqa: E402,F401  (WP-8b)
import huf.ai.gateway_adapters.telegram_business_hooks  # noqa: E402,F401  (WP-8d)
import huf.ai.gateway_adapters.telegram_stream_hooks  # noqa: E402,F401  (WP-6)
import huf.ai.gateway_adapters.telegram_groups_hooks  # noqa: E402,F401  (WP-8c)
