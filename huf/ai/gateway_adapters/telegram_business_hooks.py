# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Registers the Telegram Business update handlers (WP-8d). Imported once from ``telegram_hooks``."""

from __future__ import annotations

from huf.ai.gateway_adapters import telegram_business as biz, telegram_ingest as ing

ing.register_update_handler("business_connection", biz.handle_business_connection)
ing.register_update_handler("business_message", biz.handle_business_message)
ing.register_update_handler("edited_business_message", biz.handle_business_message)
ing.register_update_handler("deleted_business_messages", biz.handle_deleted_business_messages)
