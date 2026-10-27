# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram inline-mode update handlers (WP-8a). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_ingest, telegram_inline

telegram_ingest.register_update_handler("inline_query", telegram_inline.handle_inline_query)
telegram_ingest.register_update_handler("chosen_inline_result", telegram_inline.handle_chosen_inline_result)
# parse_update has no inline branch yet (kind == "unsupported"); dispatch on the raw update meanwhile.
telegram_ingest.register_update_handler("unsupported", telegram_inline.dispatch)
telegram_ingest.register_update_handler("callback_query", telegram_inline.handle_inline_callback)
