# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram Guard Mini App page (served at /tg_guard). Static shell only: the question and the answer check
live in ``huf.ai.telegram_guard`` and are authenticated by Telegram initData, so no data is rendered here."""

no_cache = 1
sitemap = 0


def get_context(context):
	context.no_cache = 1
	context.show_sidebar = False
	context.no_header = 1
	context.no_breadcrumbs = 1
	return context
