"""ERPNext adapter (P1): customer lookup only. ERPNext has no human reply surface, so handoff is unsupported."""

from __future__ import annotations

import re
from typing import Any

import frappe

from huf.ai.channels.adapters import ChannelAdapter

NOTE = "ERPNext has no human reply surface; handoff falls back to none."


def erpnext_installed() -> bool:
	return "erpnext" in frappe.get_installed_apps() and bool(frappe.db.exists("DocType", "Sales Order"))


def _digits(phone: str | None) -> str:
	return re.sub(r"\D", "", phone or "")


def _phone_matches(a: str, b: str) -> bool:
	a, b = _digits(a), _digits(b)
	if not a or not b:
		return False
	return a == b or (min(len(a), len(b)) >= 7 and (a.endswith(b) or b.endswith(a)))


def find_customer_by_phone(phone: str) -> dict[str, Any] | None:
	"""Contact (mobile_no or phone_nos row) matching ``phone`` that is Dynamic-Linked to a Customer."""
	digits = _digits(phone)
	if not digits or not frappe.db.exists("DocType", "Contact"):
		return None
	tail = digits[-9:]
	candidates: set[str] = set()
	for dt, field in (("Contact", "mobile_no"), ("Contact Phone", "phone")):
		if not frappe.db.exists("DocType", dt):
			continue
		filters = {field: ["like", f"%{tail}"]}
		if dt == "Contact Phone":
			filters["parenttype"] = "Contact"
			rows = frappe.get_all(dt, filters=filters, fields=["parent as name", f"{field} as phone"])
		else:
			rows = frappe.get_all(dt, filters=filters, fields=["name", f"{field} as phone"])
		candidates.update(r["name"] for r in rows if _phone_matches(r["phone"], phone))
	for contact in sorted(candidates):
		links = frappe.get_all(
			"Dynamic Link",
			filters={"parent": contact, "parenttype": "Contact", "link_doctype": "Customer"},
			fields=["link_name"],
			limit=1,
		)
		if links:
			return {"customer": links[0]["link_name"], "contact": contact}
	return None


class Adapter(ChannelAdapter):
	name = "erpnext"
	handoff_note = NOTE

	def handoff(self, conversation, summary: str = "", priority: str = "normal"):
		frappe.logger("huf").info(NOTE)
		return None, None

	def lookup_customer(self, phone: str) -> dict[str, Any] | None:
		if not erpnext_installed():
			return None
		found = find_customer_by_phone(phone)
		if not found:
			return None
		return {"doctype": "Customer", "name": found["customer"], **found}
