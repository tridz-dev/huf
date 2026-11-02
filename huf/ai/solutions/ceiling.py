"""The daily send ceiling of a WhatsApp number (A4).

Order of truth: Meta's ``messaging_limit_tier`` when the last token check (cached by
``huf.ai.whatsapp.token_check``, 10 minute TTL) reported one; else the gateway's own
``agent_send_cap_per_day`` when > 0 (0 means no limit); else no ceiling.
"""

from __future__ import annotations

import re
from typing import Optional

import frappe

UNLIMITED = "unlimited"
_TIER = re.compile(r"^TIER_(\d+)(K|M)?$")


def parse_tier(tier) -> "int | str | None":
	"""TIER_1K -> 1000, TIER_UNLIMITED -> UNLIMITED, anything unrecognised (or 0) -> None."""
	if not isinstance(tier, str):
		return None
	text = tier.strip().upper()
	if text == "TIER_UNLIMITED":
		return UNLIMITED
	match = _TIER.match(text)
	if not match:
		return None
	value = int(match.group(1)) * {"K": 1000, "M": 1_000_000, None: 1}[match.group(2)]
	return value or None


def _cached_tier(gateway: str) -> Optional[str]:
	"""Meta's tier from the cached token check; cache only, never a network call."""
	try:
		from huf.ai.whatsapp.token_check import _result_key

		cached = frappe.cache().get_value(_result_key(gateway), expires=True)
		phone = cached.get("phone") if isinstance(cached, dict) else None
		tier = phone.get("tier") if isinstance(phone, dict) else None
		return tier if isinstance(tier, str) else None
	except Exception:
		return None


def _gateway_cap(gateway: str):
	try:
		return frappe.db.get_value("Gateway", gateway, "agent_send_cap_per_day")
	except Exception:
		return None


def ceiling_for_gateway(gateway) -> tuple[Optional[int], str]:
	"""(ceiling, source). TIER_UNLIMITED is ``(None, "meta_tier")``: Meta set no limit."""
	if not gateway:
		return None, "none"
	parsed = parse_tier(_cached_tier(gateway))
	if parsed == UNLIMITED:
		return None, "meta_tier"
	if isinstance(parsed, int):
		return parsed, "meta_tier"
	try:
		cap = int(_gateway_cap(gateway) or 0)
	except (TypeError, ValueError):
		cap = 0
	if cap > 0:
		return cap, "gateway_cap"
	return None, "none"
