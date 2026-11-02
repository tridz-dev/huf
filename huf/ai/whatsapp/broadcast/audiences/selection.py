# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Audience selection helpers shared by the preview endpoints and ``set_broadcast_audiences``."""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.whatsapp.broadcast import policy
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast.audiences.common import _parse_list

NO_INCLUDE = "Pick at least one audience to include."
WRONG_GATEWAY = "Every audience must belong to the same WhatsApp gateway as the broadcast."


def parse_selection(selection: Any) -> list[dict]:
	items = _parse_list(selection, "selection")
	max_items = policy.get("audience_max_selection_items")
	if len(items) > max_items:
		raise ValueError(f"Pick at most {max_items} audiences.")
	if not all(isinstance(i, dict) and i.get("audience") for i in items):
		raise ValueError("Each pick needs an audience.")
	return items


def check_selection(gateway: str, items: list[dict]) -> str | None:
	"""Error text when the picks are unusable for ``gateway`` (no include, unknown or foreign audience)."""
	if not any(not aud._truthy(i.get("exclude")) for i in items):
		return NO_INCLUDE
	for item in items:
		other = frappe.db.get_value(aud.AUDIENCE, item.get("audience"), "gateway")
		if other != gateway:
			return WRONG_GATEWAY
	return None


def blocked_entries(result: dict, audiences: dict, category: str | None) -> list[dict]:
	needed = aud.purpose_for_category(category)
	return [
		{
			"code": "audience_purpose_mismatch",
			"audience": name,
			"message": f"{audiences[name]['title']} was not collected for {needed} messages.",
		}
		for name in result["blocked_audiences"]
	]


def expand(gateway: str, items: list[dict], category: str | None) -> tuple[dict, dict, list[dict]]:
	"""(expand_selection result, audience rows, blocked entries) for already validated picks."""
	audiences, members = aud.load_inputs(items)
	everyone = {m["recipient"] for rows in members.values() for m in rows}
	suppressed = aud.suppression_map(gateway, everyone, marketing=str(category or "").upper() == "MARKETING")
	result = aud.expand_selection(items, audiences, members, suppressed, category)
	return result, audiences, blocked_entries(result, audiences, category)


def preview_payload(gateway: str, items: list[dict], category: str | None) -> dict[str, Any]:
	result, _audiences, blocked = expand(gateway, items, category)
	return {
		"success": True,
		"counts": result["counts"],
		"per_audience": result["per_audience"],
		"blocked": blocked,
		"category": category,
		"purpose_required": aud.purpose_for_category(category),
	}
