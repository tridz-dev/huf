# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast recipient intake: normalize, validate, filter and store recipient rows.

:func:`prepare` turns raw rows into ``WhatsApp Broadcast Recipient`` rows. Each row is ``queued`` or,
when policy refuses it, ``skipped`` with ``skip_reason``. Numbers that are not valid E.164 digits are
not stored; they are reported in ``invalid``. Opt-out checks reuse the outbound policy choke point
(:func:`outbound_policy.check_recipient`, which covers STOP and BSUID) and the marketing preference
from :func:`account_events.is_marketing_allowed`; nothing is reimplemented here.
"""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import frappe

from huf.ai.whatsapp.broadcast import params as broadcast_params, policy

RECIPIENT_DOCTYPE = "WhatsApp Broadcast Recipient"
PHONE_HEADERS = {"phone", "recipient", "phone_number", "phone number", "mobile", "wa_id", "whatsapp", "number"}


def normalize_recipient(raw: Any) -> str | None:
	"""Return the recipient as E.164 digits (no +), a BSUID verbatim, or None when invalid."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if raw is None or not str(raw).strip():
		return None
	if bridge.is_bsuid(raw):
		return str(raw).strip()
	digits = bridge.normalize_phone(raw)
	if not digits.isdigit() or not (policy.get("min_phone_digits") <= len(digits) <= policy.get("max_phone_digits")):
		return None
	return digits


def _row_name(broadcast: str, recipient: str) -> str:
	# Mirrors WhatsApp Broadcast Recipient.autoname so duplicates are detected before insert.
	return f"{broadcast}-{recipient}"[:140]


def _is_us_plus_one(recipient: str) -> bool:
	return recipient.isdigit() and len(recipient) == 11 and recipient.startswith("1")


def _load_broadcast(broadcast: str):
	return frappe.get_doc("WhatsApp Broadcast", broadcast)


def _existing_names(broadcast: str) -> set[str]:
	return set(
		frappe.get_all(RECIPIENT_DOCTYPE, filters={"broadcast": broadcast}, pluck="name", limit_page_length=0)
	)


def _active_count(broadcast: str) -> int:
	return frappe.db.count(RECIPIENT_DOCTYPE, {"broadcast": broadcast, "status": ["!=", "skipped"]})


def _total_count(broadcast: str) -> int:
	return int(frappe.db.count(RECIPIENT_DOCTYPE, {"broadcast": broadcast}) or 0)


def _insert_row(
	broadcast: str,
	recipient: str,
	status: str,
	skip_reason: str | None,
	params: dict | None,
	consent_source: str | None,
	consent_at: str | None,
) -> None:
	frappe.get_doc(
		{
			"doctype": RECIPIENT_DOCTYPE,
			"broadcast": broadcast,
			"recipient": recipient,
			"status": status,
			"skip_reason": skip_reason,
			"params": json.dumps(params) if params else None,
			"consent_source": consent_source,
			"consent_at": consent_at,
		}
	).insert(ignore_permissions=True)


def _policy_reason(gateway: str, recipient: str, is_marketing: bool) -> str | None:
	"""Skip reason from policy, or None when the recipient may be queued."""
	from huf.ai.whatsapp import account_events as events
	from huf.ai.whatsapp.outbound_policy import OutboundRefused, check_recipient

	try:
		check_recipient(gateway, recipient)  # STOP (opted_out) and BSUID (bsuid_recipient)
	except OutboundRefused as exc:
		return exc.code
	if is_marketing:
		if not events.is_marketing_allowed(gateway, recipient):
			return "marketing_opted_out"
		if _is_us_plus_one(recipient):
			return "us_plus_one_marketing"
	return None


def effective_cap(doc) -> int | None:
	"""Recipients a broadcast may hold: its own cap, else the default, bounded by the ceiling (None = no limit)."""
	cap = policy.get("max_recipients_default", doc)
	ceiling = policy.get("max_recipients_ceiling")
	if cap is None:
		return ceiling
	return cap if ceiling is None else min(int(cap), int(ceiling))


def prepare(broadcast: str, rows: list[dict]) -> dict:
	"""Validate and store recipient rows for ``broadcast``.

	``rows`` is ``[{"recipient": ..., "params": {...}?, "consent_source"?, "consent_at"?}]``.
	Returns ``{"added": n, "skipped": [{"recipient", "reason"}], "invalid": [{"recipient", "reason"}]}``
	and recounts the broadcast counters. Does not commit; the caller owns the transaction.
	"""
	doc = _load_broadcast(broadcast)
	is_marketing = str(doc.category or "").upper() == "MARKETING"
	cap = effective_cap(doc)
	max_rows = policy.get("max_rows_per_broadcast")
	list_limit = policy.get("returned_list_limit")
	seen = _existing_names(broadcast)
	active = _active_count(broadcast)
	total = _total_count(broadcast)

	added = 0
	skipped: list[dict[str, Any]] = []
	invalid: list[dict[str, Any]] = []

	for row in rows or []:
		raw = row.get("recipient") if isinstance(row, dict) else None
		recipient = normalize_recipient(raw)
		if recipient is None:
			invalid.append({"recipient": raw, "reason": "invalid_number"})
			continue
		problem = broadcast_params.params_error(row.get("params"))
		if problem:
			invalid.append({"recipient": raw, "reason": f"invalid_params: {problem}"})
			continue

		name = _row_name(broadcast, recipient)
		if name in seen:
			skipped.append({"recipient": recipient, "reason": "duplicate"})
			continue
		seen.add(name)

		if cap is not None and active >= cap:
			# Checked BEFORE policy-skipped rows are stored, so they cannot bypass the cap.
			# Not stored: a later run with a higher max_recipients can still add this contact.
			skipped.append({"recipient": recipient, "reason": "max_recipients"})
			continue
		if total >= max_rows:
			skipped.append({"recipient": recipient, "reason": "row_ceiling"})
			continue

		reason = _policy_reason(doc.gateway, recipient, is_marketing)
		if reason is not None:
			_insert_row(broadcast, recipient, "skipped", reason, None, None, None)
			total += 1
			skipped.append({"recipient": recipient, "reason": reason})
			continue

		params = row.get("params") if isinstance(row.get("params"), dict) else None
		_insert_row(
			broadcast,
			recipient,
			"queued",
			None,
			params,
			row.get("consent_source") or None,
			row.get("consent_at") or None,
		)
		active += 1
		total += 1
		added += 1

	doc.recount()
	return {
		"added": added,
		"skipped": skipped[:list_limit],
		"skipped_total": len(skipped),
		"invalid": invalid[:list_limit],
		"invalid_total": len(invalid),
	}


def parse_csv(text: str) -> list[dict]:
	"""Parse CSV text into prepare() rows.

	The recipient column is the first header matching a known phone header (``phone``, ``recipient``,
	``phone_number``, ``mobile``, ``wa_id``, ``whatsapp``, ``number``; case, spaces and dashes ignored).
	A leading UTF-8 BOM is stripped. Named columns set per-recipient header and button values:
	``header`` (text, or an https link for a media header), ``header_lat`` / ``header_lng`` /
	``header_name`` / ``header_address`` (location header), ``button_url_<n>`` (link suffix) and
	``button_code_<n>`` (copy code) where ``n`` is the button index from 0. Every other column becomes
	``params["body"]`` in column order. An empty cell uses the broadcast default. Blank lines are skipped.
	Raises ValueError when no phone header is present.
	"""
	text = (text or "").lstrip("\ufeff")
	reader = csv.reader(io.StringIO(text))
	header = None
	for cells in reader:
		if any(c.strip() for c in cells):
			header = cells
			break
	if header is None:
		return []

	keys = [h.strip().lower().replace("-", "_") for h in header]
	phone_idx = next((i for i, k in enumerate(keys) if k in PHONE_HEADERS), None)
	if phone_idx is None:
		raise ValueError("CSV needs a 'phone' or 'recipient' column")
	named = {i: k for i, k in enumerate(keys) if k in _HEADER_COLUMNS or _BUTTON_COLUMN.match(k)}
	body_idx = [i for i in range(len(header)) if i != phone_idx and i not in named]

	out: list[dict] = []
	for cells in reader:
		if not any(c.strip() for c in cells):
			continue
		padded = cells + [""] * (len(header) - len(cells))
		params: dict[str, Any] = {"body": [padded[i] for i in body_idx]}
		_apply_named_columns(params, {k: padded[i].strip() for i, k in named.items() if padded[i].strip()})
		out.append({"recipient": padded[phone_idx].strip(), "params": params})
	return out


_HEADER_COLUMNS = {"header", "header_lat", "header_lng", "header_name", "header_address"}
_BUTTON_COLUMN = re.compile(r"^button_(url|code)_(\d)$")


def _apply_named_columns(params: dict[str, Any], values: dict[str, str]) -> None:
	if any(k in values for k in ("header_lat", "header_lng")):
		params["header"] = [{
			"type": "location", "latitude": values.get("header_lat"), "longitude": values.get("header_lng"),
			**{k: values[f"header_{k}"] for k in ("name", "address") if f"header_{k}" in values},
		}]
	elif "header" in values:
		params["header"] = [values["header"]]
	buttons = []
	for key, value in sorted(values.items()):
		m = _BUTTON_COLUMN.match(key)
		if m:
			kind, index = m.groups()
			buttons.append({"index": int(index), "sub_type": "url", "text": value} if kind == "url"
				else {"index": int(index), "sub_type": "copy_code", "code": value})
	if buttons:
		params["button"] = sorted(buttons, key=lambda b: b["index"])
