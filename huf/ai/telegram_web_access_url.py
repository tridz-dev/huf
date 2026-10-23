# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Builds the launch URL for the Telegram web-access page (``/tg_open``)."""

from __future__ import annotations

from urllib.parse import urlencode

from huf.ai import telegram_public_url


def web_access_url(gateway: str, to: str = "") -> str:
	"""``<public_base>/tg_open?gw=<gateway>[&to=<path>]``; both values are URL-encoded."""
	params = {"gw": str(gateway or "")}
	if to:
		params["to"] = str(to)
	return telegram_public_url.public_url("/tg_open?" + urlencode(params))
