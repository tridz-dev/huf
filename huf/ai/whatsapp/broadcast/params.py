# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast header / button parameter checks and merging.

Shapes (same as ``create_broadcast``): header ``["text" | "https link" | {"type": "location", latitude,
longitude, name?, address?}]``; buttons ``[{"index": 0, "sub_type": "url", "text": suffix}, {"index": 1,
"sub_type": "copy_code", "code": "SAVE10"}]``. Used when a broadcast is created, when recipients are
added (per-recipient values) and when a row is sent.
"""

from __future__ import annotations

import re
from typing import Any

LOCATION_TEXT_MAX = 1000
URL_SUFFIX_MAX = 2000
COPY_CODE_MAX = 15
HEADER_TEXT_MAX = 60
_CODE_RE = re.compile(r"^[A-Za-z0-9]+$")


def _num(value: Any, low: float, high: float) -> float | None:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if low <= number <= high and number == number else None


def location_error(item: dict[str, Any]) -> str | None:
	if _num(item.get("latitude"), -90, 90) is None:
		return "latitude must be a number between -90 and 90"
	if _num(item.get("longitude"), -180, 180) is None:
		return "longitude must be a number between -180 and 180"
	for key in ("name", "address"):
		if len(str(item.get(key) or "")) > LOCATION_TEXT_MAX:
			return f"location {key} is limited to {LOCATION_TEXT_MAX} characters"
	return None


def header_error(header: Any) -> str | None:
	"""First problem in a header value (``None`` when fine or empty)."""
	items = [header] if isinstance(header, (dict, str)) else list(header or [])
	if len(items) > 1:
		return "a header takes at most one value"
	for item in items:
		if isinstance(item, dict):
			if str(item.get("type") or "").lower() == "location":
				return location_error(item)
			link = str(item.get("link") or "")
			if link and not link.lower().startswith("https://"):
				return "a media header link must start with https://"
		elif isinstance(item, str):
			text = item.strip()
			if text.lower().startswith("http://"):
				return "a media header link must start with https://"
			if not text.lower().startswith("https://") and len(text) > HEADER_TEXT_MAX:
				return f"header text is limited to {HEADER_TEXT_MAX} characters"
	return None


def button_error(buttons: Any) -> str | None:
	for item in buttons if isinstance(buttons, list) else []:
		if not isinstance(item, dict):
			continue
		kind = str(item.get("sub_type") or item.get("type") or "url").lower()
		if kind == "copy_code":
			code = str(item.get("code") if item.get("code") is not None else item.get("text") or "")
			if not code or len(code) > COPY_CODE_MAX or not _CODE_RE.match(code):
				return f"a copy code needs 1 to {COPY_CODE_MAX} letters or digits"
		elif kind == "url":
			text = str(item.get("text") or "")
			if "://" in text or len(text) > URL_SUFFIX_MAX:
				return f"a link suffix must not include a scheme and is limited to {URL_SUFFIX_MAX} characters"
	return None


def params_error(params: Any) -> str | None:
	"""First problem in a recipient's ``params`` (``{"body", "header", "button"}``), or ``None``."""
	if not isinstance(params, dict):
		return None
	return header_error(params.get("header")) or button_error(params.get("button"))


def merge_buttons(default: Any, mine: Any) -> Any:
	"""Recipient button values replace the default of the same ``index``; other defaults stay."""
	if not isinstance(default, list) or not isinstance(mine, list):
		return mine
	by_index = {int(b.get("index", i)): b for i, b in enumerate(default) if isinstance(b, dict)}
	for i, b in enumerate(mine):
		if isinstance(b, dict):
			by_index[int(b.get("index", i))] = b
	return [by_index[k] for k in sorted(by_index)]
