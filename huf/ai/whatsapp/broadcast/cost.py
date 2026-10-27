# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-12: cost estimate for a WhatsApp Broadcast before it is started.

The estimate is computed from the rate card in ``rates.json``
(source URL and retrieval date are stored there). Recipients are bucketed by
market, derived from the E.164 dialling code. Unknown markets, unknown
categories and null rates produce warnings and a null total.

Billing is done by Meta. This module never reads or writes billing state.
"""

from __future__ import annotations

import json
import os
from typing import Any

import frappe

RATES_PATH = os.path.join(os.path.dirname(__file__), "rates.json")

# Recipient statuses that are still going to be sent (or retried).
PENDING_STATUSES = ("queued", "deferred")

UNKNOWN_MARKET = "UNKNOWN"


def _load_rates() -> dict[str, Any]:
	with open(RATES_PATH, encoding="utf-8") as fh:
		return json.load(fh)


def _digits(recipient: str) -> str:
	"""Digits of a phone-number recipient, or "" if the value is not a plain phone number (e.g. a BSUID)."""
	stripped = (recipient or "").strip()
	if stripped.startswith("+"):
		stripped = stripped[1:]
	stripped = "".join(ch for ch in stripped if ch not in " -()")
	return stripped if stripped.isdigit() else ""


def market_for_recipient(recipient: str, dialling_codes: dict[str, str] | None = None) -> str:
	"""Return the market code for a recipient, or ``UNKNOWN``.

	Uses longest-prefix match over the dialling codes. BSUIDs and any value
	without digits are not resolvable to a country and return ``UNKNOWN``.
	"""
	if dialling_codes is None:
		dialling_codes = _load_rates()["dialling_codes"]
	number = _digits(recipient)
	if not number:
		return UNKNOWN_MARKET
	for code in sorted(dialling_codes, key=len, reverse=True):
		if number.startswith(code):
			return dialling_codes[code]
	return UNKNOWN_MARKET


def _pending_rows(broadcast: str) -> list[dict[str, Any]]:
	return frappe.get_all(
		"WhatsApp Broadcast Recipient",
		filters={"broadcast": broadcast, "status": ["in", list(PENDING_STATUSES)]},
		fields=["recipient", "status"],
		limit_page_length=0,
	)


def _category(broadcast: str) -> str | None:
	return frappe.db.get_value("WhatsApp Broadcast", broadcast, "category")


def confirm_token(broadcast: str) -> str:
	"""Exact number of recipients that will be sent, as a string, for typed-count confirmation."""
	return str(len(_pending_rows(broadcast)))


def estimate(broadcast: str) -> dict[str, Any]:
	"""Estimate the Meta charge for the pending recipients of a broadcast.

	Returns ``total`` as ``None`` when any bucket has no verified rate. The
	``by_country`` buckets still carry counts so the UI can show what is missing.
	"""
	rates_doc = _load_rates()
	dialling_codes = rates_doc["dialling_codes"]
	rate_table = rates_doc["rates"]
	currency = rates_doc["currency"]
	warnings: list[str] = []

	category = (_category(broadcast) or "").lower() or None
	if category is None:
		warnings.append("category_missing")
	elif category not in rate_table:
		warnings.append(f"category_unsupported:{category}")

	counts: dict[str, int] = {}
	for row in _pending_rows(broadcast):
		market = market_for_recipient(row.get("recipient"), dialling_codes)
		counts[market] = counts.get(market, 0) + 1

	by_country: dict[str, dict[str, Any]] = {}
	total: float | None = 0.0
	for market in sorted(counts):
		count = counts[market]
		rate = None
		if market == UNKNOWN_MARKET:
			warnings.append(f"market_unknown:{count}_recipients")
		elif category in rate_table:
			rate = rate_table[category].get(market)
			if rate is None:
				warnings.append(f"rate_unavailable:{category}:{market}")
		subtotal = None if rate is None else round(rate * count, 6)
		by_country[market] = {"count": count, "rate": rate, "subtotal": subtotal}
		if subtotal is None:
			total = None
		elif total is not None:
			total += subtotal

	if total is not None:
		total = round(total, 6)
	if not counts:
		total = 0.0

	return {
		"currency": currency,
		"total": total,
		"by_country": by_country,
		"category": category,
		"basis": f"rate_card_{rates_doc['retrieved']}",
		"rates_verified": bool(rates_doc.get("rates_verified")),
		"warnings": warnings,
		"disclaimer": rates_doc["disclaimer"],
	}
