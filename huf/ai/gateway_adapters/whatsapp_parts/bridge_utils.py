# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Small pure helpers split out of ``whatsapp_bridge`` (template status parsing / button signatures)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _parse_ts(value: Any) -> datetime | None:
	try:
		dt = datetime.fromisoformat(str(value))
	except (TypeError, ValueError):
		return None
	return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clean_reason(reason: Any) -> str:
	text = str(reason or "").strip()
	return "" if text.upper() == "NONE" else text


def _button_sig(rows: list[dict[str, Any]]) -> list[tuple]:
	return [
		(
			r.get("button_type") or "",
			r.get("button_label") or "",
			r.get("website_url") or "",
			r.get("phone_number") or "",
		)
		for r in rows
	]
