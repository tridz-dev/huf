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
from typing import Any

import frappe

RECIPIENT_DOCTYPE = "WhatsApp Broadcast Recipient"
DEFAULT_MAX_RECIPIENTS = 1000
MAX_RECIPIENTS_CEILING = 10000  # highest max_recipients a broadcast may be given
MAX_ROWS_PER_BROADCAST = 50000  # hard ceiling on stored rows (skipped rows count)
MAX_ROWS_PER_REQUEST = 10000  # recipients accepted in one add call
MAX_CSV_BYTES = 2 * 1024 * 1024
RETURNED_LIST_LIMIT = 200  # skipped/invalid entries echoed back; totals are always exact
MIN_DIGITS = 8
MAX_DIGITS = 15  # E.164 upper bound
PHONE_HEADERS = {"phone", "recipient", "phone_number", "phone number", "mobile", "wa_id", "whatsapp", "number"}


def normalize_recipient(raw: Any) -> str | None:
	"""Return the recipient as E.164 digits (no +), a BSUID verbatim, or None when invalid."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	if raw is None or not str(raw).strip():
		return None
	if bridge.is_bsuid(raw):
		return str(raw).strip()
	digits = bridge.normalize_phone(raw)
	if not digits.isdigit() or not (MIN_DIGITS <= len(digits) <= MAX_DIGITS):
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


def prepare(broadcast: str, rows: list[dict]) -> dict:
	"""Validate and store recipient rows for ``broadcast``.

	``rows`` is ``[{"recipient": ..., "params": {...}?, "consent_source"?, "consent_at"?}]``.
	Returns ``{"added": n, "skipped": [{"recipient", "reason"}], "invalid": [{"recipient", "reason"}]}``
	and recounts the broadcast counters. Does not commit; the caller owns the transaction.
	"""
	doc = _load_broadcast(broadcast)
	is_marketing = str(doc.category or "").upper() == "MARKETING"
	cap = min(int(doc.max_recipients or DEFAULT_MAX_RECIPIENTS), MAX_RECIPIENTS_CEILING)
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

		name = _row_name(broadcast, recipient)
		if name in seen:
			skipped.append({"recipient": recipient, "reason": "duplicate"})
			continue
		seen.add(name)

		if active >= cap:
			# Checked BEFORE policy-skipped rows are stored, so they cannot bypass the cap.
			# Not stored: a later run with a higher max_recipients can still add this contact.
			skipped.append({"recipient": recipient, "reason": "max_recipients"})
			continue
		if total >= MAX_ROWS_PER_BROADCAST:
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
		"skipped": skipped[:RETURNED_LIST_LIMIT],
		"skipped_total": len(skipped),
		"invalid": invalid[:RETURNED_LIST_LIMIT],
		"invalid_total": len(invalid),
	}


def parse_csv(text: str) -> list[dict]:
	"""Parse CSV text into prepare() rows.

	The recipient column is the first header matching a known phone header (``phone``, ``recipient``,
	``phone_number``, ``mobile``, ``wa_id``, ``whatsapp``, ``number``; case, spaces and dashes ignored).
	A leading UTF-8 BOM is stripped. Every other column becomes ``params["body"]`` in column order.
	Blank lines are skipped. Raises ValueError when no phone header is present.
	"""
	text = (text or "").lstrip("﻿")
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
	body_idx = [i for i in range(len(header)) if i != phone_idx]

	out: list[dict] = []
	for cells in reader:
		if not any(c.strip() for c in cells):
			continue
		padded = cells + [""] * (len(header) - len(cells))
		out.append({"recipient": padded[phone_idx].strip(), "params": {"body": [padded[i] for i in body_idx]}})
	return out
