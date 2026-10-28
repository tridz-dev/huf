# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""CSV / row-dict parsing and column mapping for audience imports."""

from __future__ import annotations

import csv
import io
from typing import Any

from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast import recipients as broadcast_recipients
from huf.ai.whatsapp.management import _error, _parse_json_arg

_AUTO_HEADERS = {
	"phone": broadcast_recipients.PHONE_HEADERS,
	"name": {"name", "display_name", "full_name", "contact", "customer"},
	"tags": {"tags", "tag", "segment", "segments", "labels"},
	"consent_source": {"consent_source"},
	"consent_at": {"consent_at", "consent_date", "consented_at"},
}



# --- CSV / mapping ---------------------------------------------------------------------------------
def mapped_rows(csv_text: Any, rows: Any, mapping: Any) -> list[dict] | dict[str, Any]:
	"""Rows in ``import_rows`` shape, or an error dict."""
	if csv_text and rows:
		return _error("invalid", "Send either csv_text or rows, not both.")
	if csv_text:
		if len(str(csv_text).encode("utf-8")) > aud.LIMIT_MAX_CSV_BYTES:
			return _error("csv_too_large", f"The file is larger than {aud.LIMIT_MAX_CSV_BYTES // (1024 * 1024)} MB.")
		reader = csv.reader(io.StringIO(str(csv_text).lstrip("﻿")))
		table = [cells for cells in reader if any(c.strip() for c in cells)]
		if not table:
			return []
		headers = [h.strip() for h in table[0]]
		records = [dict(zip(headers, row + [""] * (len(headers) - len(row)), strict=False)) for row in table[1:]]
	else:
		records = _parse_list(rows, "rows")
		if not all(isinstance(r, dict) for r in records):
			return _error("invalid", "rows must be a list of objects.")
		headers = list(records[0].keys()) if records else []
	if len(records) > aud.LIMIT_MAX_IMPORT_ROWS:
		return _error("too_many", f"Import at most {aud.LIMIT_MAX_IMPORT_ROWS} contacts at a time.")
	columns = resolve_mapping(headers, mapping)
	if isinstance(columns, dict) and columns.get("error"):
		return columns
	out = []
	for rec in records:
		item: dict[str, Any] = {"recipient": rec.get(columns["phone"])}
		for field, key in (("display_name", "name"), ("tags", "tags"), ("consent_source", "consent_source"), ("consent_at", "consent_at")):
			if columns.get(key):
				item[field] = rec.get(columns[key])
		if columns.get("params"):
			item["params"] = {"body": [str(rec.get(c) if rec.get(c) is not None else "") for c in columns["params"]]}
		out.append(item)
	return out


def resolve_mapping(headers: list[str], mapping: Any) -> dict[str, Any]:
	lowered = {h.strip().lower().replace("-", "_"): h for h in headers}
	cols: dict[str, Any] = {}
	if mapping:
		if not isinstance(mapping, dict):
			return _error("invalid", "mapping must be an object.")
		cols = {("phone" if k == "recipient" else k): v for k, v in mapping.items()}
		wanted = [v for k, v in cols.items() if k != "params" and v] + list(cols.get("params") or [])
		missing = [c for c in wanted if c not in headers]
		if missing:
			return _error("unknown_column", f"These columns are not in the file: {', '.join(map(str, missing))}")
	for key, names in _AUTO_HEADERS.items():
		if not cols.get(key):
			found = next((lowered[n] for n in lowered if n in names), None)
			if found:
				cols[key] = found
	if not cols.get("phone"):
		return _error("mapping_missing_phone", "Choose which column holds the phone number.")
	return cols



def _parse_list(value: Any, label: str) -> list:
	parsed = _parse_json_arg(value, label)
	if parsed in (None, ""):
		return []
	if not isinstance(parsed, list):
		raise ValueError(f"{label} must be a list")
	return parsed
