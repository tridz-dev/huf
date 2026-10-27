# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram web-access launcher (served at /tg_open). Static shell only: the gateway and target path are
read client-side from the query string and sent to ``huf.ai.telegram_web_access.exchange``, which verifies
Telegram initData. Nothing from the request is rendered server-side, so the gateway name is never echoed."""

import frappe

no_cache = 1
sitemap = 0


def get_context(context):
	# A web view that already holds a Telegram session (an earlier tap) is a logged-in request, so Frappe
	# requires its CSRF token on the exchange POST; guests need none. Re-entry must work like first entry.
	context.csrf_token = ""
	if frappe.session.user != "Guest":
		from frappe.sessions import get_csrf_token

		context.csrf_token = get_csrf_token()
	context.no_cache = 1
	context.show_sidebar = False
	context.no_header = 1
	context.no_breadcrumbs = 1
	return context
