"""Explicit opt-in capture for WhatsApp gateways (BE-OPTIN): import with attestation, and the API source.

Both entry points write ``Gateway Consent`` rows for the marketing category (value ``resume``) and never
re-opt-in a contact who is currently opted out: a STOP (Gateway Access Entry ``Opted out``) or a Meta
marketing stop always wins. Both are gated on ``system.integrations.manage``.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import frappe
from frappe import _

from huf.permissions import has_capability

API_SOURCES = ("api", "manual", "widget")
_PHONE_HEADERS = {"phone", "phone_number", "wa_id", "mobile", "whatsapp"}
_MIN_DIGITS, _MAX_DIGITS = 7, 15  # E.164 length bounds


def _require_manage() -> None:
	if not has_capability(frappe.session.user, "system.integrations.manage"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_whatsapp_gateway(gateway: str) -> None:
	provider = frappe.db.get_value("Gateway", gateway, "provider") if gateway else None
	if provider != "WhatsApp":
		frappe.throw(_("Choose a WhatsApp gateway."), frappe.ValidationError)


def _phone(raw: Any) -> str | None:
	"""Digits-only phone, or None when the value is not a usable phone number (BSUIDs are not phones)."""
	from huf.ai.gateway_adapters import whatsapp_bridge as bridge

	value = str(raw or "").strip()
	if not value or bridge.is_bsuid(value):
		return None
	digits = bridge.normalize_phone(value)
	if not digits.isdigit() or not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
		return None
	return digits


def _raw_items(rows: Any) -> list[Any]:
	"""CSV text (first column is the phone, optional header) or a list of phones / dicts with a phone key."""
	if isinstance(rows, str):
		items = [record[0] for record in csv.reader(io.StringIO(rows)) if record]
	elif isinstance(rows, (list, tuple)):
		items = []
		for item in rows:
			if isinstance(item, dict):
				items.append(item.get("phone") or item.get("wa_id") or item.get("mobile") or "")
			else:
				items.append(item)
	else:
		frappe.throw(_("Rows must be CSV text or a list."), frappe.ValidationError)
	if items and str(items[0] or "").strip().lower() in _PHONE_HEADERS:
		items = items[1:]
	return items


def _record(gateway: str, phone: str, source: str, attested_by: str, note: str | None) -> str:
	"""Write one marketing opt-in row unless the contact is opted out. Returns created | updated | skipped_opted_out."""
	from huf.ai import gateway_service
	from huf.ai.whatsapp import account_events as events

	if gateway_service.is_opted_out(gateway, phone) or events._latest_consent(gateway, phone, events.MARKETING) == "stop":
		return "skipped_opted_out"
	status = "updated" if events._latest_consent(gateway, phone, events.MARKETING) == "resume" else "created"
	events._insert_consent(
		gateway,
		phone,
		events.MARKETING,
		"resume",
		detail=f"opt-in via {source}",
		source=source,
		attested_by=attested_by,
		attestation_note=note,
	)
	return status


@frappe.whitelist(methods=["POST"])
def import_opt_ins(gateway: str, rows: Any, attestation_note: str | None = None) -> dict[str, Any]:
	"""Record marketing opt-ins for a list of phones, attested by the calling user.

	``attestation_note`` is required and says where and how the opt-ins were collected. Numbers that are opted
	out (STOP or Meta marketing stop) are skipped. Duplicate numbers in one input are counted once.
	"""
	_require_manage()
	note = (attestation_note or "").strip()
	if not note:
		frappe.throw(_("An attestation note is required: say where and how these opt-ins were collected."), frappe.ValidationError)
	_require_whatsapp_gateway(gateway)
	attester = frappe.session.user
	counts = {"created": 0, "updated": 0, "skipped_opted_out": 0, "invalid": 0}
	seen: set[str] = set()
	for raw in _raw_items(rows):
		phone = _phone(raw)
		if phone is None:
			counts["invalid"] += 1
			continue
		if phone in seen:
			continue
		seen.add(phone)
		counts[_record(gateway, phone, "import", attester, note)] += 1
	return {"success": True, "gateway": gateway, **counts}


@frappe.whitelist(methods=["POST"])
def record_opt_in(gateway: str, phone: str, source: str = "api", note: str | None = None) -> dict[str, Any]:
	"""Record one marketing opt-in from an API caller (or a manual/widget capture). Same STOP protection as import."""
	_require_manage()
	if source not in API_SOURCES:
		frappe.throw(_("Source must be one of: {0}.").format(", ".join(API_SOURCES)), frappe.ValidationError)
	_require_whatsapp_gateway(gateway)
	number = _phone(phone)
	if number is None:
		return {"success": False, "gateway": gateway, "status": "invalid"}
	status = _record(gateway, number, source, frappe.session.user, (note or "").strip() or None)
	return {"success": status != "skipped_opted_out", "gateway": gateway, "status": status}
