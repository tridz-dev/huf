# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Builds the launch URL for the Telegram web-access page (``/tg_open``)."""

from __future__ import annotations

from urllib.parse import urlencode

import frappe

from huf.ai import telegram_public_url


def web_access_url(gateway: str, to: str = "") -> str:
	"""``<public_base>/tg_open?gw=<gateway>[&to=<path>]``; both values are URL-encoded."""
	params = {"gw": str(gateway or "")}
	if to:
		params["to"] = str(to)
	return telegram_public_url.public_url("/tg_open?" + urlencode(params))


@frappe.whitelist()
def get_web_access_url(gateway: str, to: str = "") -> dict[str, str]:
	"""Ready-to-use Mini App link for the settings screen (signed-in users only)."""
	if not frappe.db.exists("Gateway", gateway):
		frappe.throw(frappe._("Gateway not found."), frappe.DoesNotExistError)
	return {"url": web_access_url(gateway, to)}
