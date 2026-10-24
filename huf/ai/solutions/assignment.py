"""Conversation Assignment helpers: which solution owns one chat (gateway + contact).

All functions are idempotent and never raise on a missing row. None of them commit;
the caller owns the transaction.
"""

from datetime import timedelta

import frappe
from frappe.utils import get_datetime, now_datetime

DT = "Conversation Assignment"
_SET_BY = ("rule", "triage", "handoff", "referral")


def _now(now):
	return get_datetime(now) if now else now_datetime()


def _row_name(gateway, contact):
	if not gateway or not contact:
		return None
	return frappe.db.get_value(DT, {"gateway": gateway, "contact": str(contact).strip()}, "name")


def _row(gateway, contact):
	name = _row_name(gateway, contact)
	if not name:
		return None
	return frappe.db.get_value(
		DT,
		name,
		["name", "solution", "expires_at", "set_by", "source_binding", "triage_pending_until"],
		as_dict=True,
	)


def get_pin(gateway, contact, now=None):
	"""Live pin as a dict, or None when missing/expired/empty. Expired rows are left in place."""
	row = _row(gateway, contact)
	if not row or not row.solution or not row.expires_at:
		return None
	if get_datetime(row.expires_at) <= _now(now):
		return None
	return {
		"solution": row.solution,
		"expires_at": get_datetime(row.expires_at),
		"set_by": row.set_by,
		"triage_pending_until": get_datetime(row.triage_pending_until) if row.triage_pending_until else None,
		"source_binding": row.source_binding,
	}


def get_triage_pending(gateway, contact, now=None):
	"""Datetime until which a triage answer is accepted, or None when not pending/expired."""
	row = _row(gateway, contact)
	if not row or not row.triage_pending_until:
		return None
	until = get_datetime(row.triage_pending_until)
	return until if until > _now(now) else None


def set_pin(gateway, contact, solution, set_by, source_binding=None, ttl_hours=24, now=None):
	"""Upsert the single (gateway, contact) row. A new pin ends any open triage menu."""
	contact = str(contact).strip()
	if set_by not in _SET_BY:
		set_by = "rule"
	expires = _now(now) + timedelta(hours=ttl_hours if ttl_hours else 24)
	values = {
		"solution": solution,
		"expires_at": expires,
		"set_by": set_by,
		"source_binding": source_binding or None,
		"triage_pending_until": None,
	}
	name = _row_name(gateway, contact)
	if name:
		frappe.db.set_value(DT, name, values, update_modified=True)
	else:
		doc = frappe.get_doc({"doctype": DT, "gateway": gateway, "contact": contact, **values})
		doc.insert(ignore_permissions=True)
	return {"solution": solution, "expires_at": expires, "set_by": set_by, "source_binding": source_binding}


def mark_triage_pending(gateway, contact, until):
	contact = str(contact).strip()
	name = _row_name(gateway, contact)
	if name:
		frappe.db.set_value(DT, name, "triage_pending_until", until, update_modified=True)
		return
	# no pin yet: the row exists only to remember the open menu
	doc = frappe.get_doc(
		{"doctype": DT, "gateway": gateway, "contact": contact, "triage_pending_until": until}
	)
	doc.insert(ignore_permissions=True, ignore_mandatory=True)


def clear_triage_pending(gateway, contact):
	name = _row_name(gateway, contact)
	if name:
		frappe.db.set_value(DT, name, "triage_pending_until", None, update_modified=True)


def clear_pin(gateway, contact):
	"""Drop the pin but keep the row (and any open triage menu)."""
	name = _row_name(gateway, contact)
	if name:
		frappe.db.set_value(
			DT,
			name,
			{"solution": None, "expires_at": None, "set_by": None, "source_binding": None},
			update_modified=True,
		)


def current_solution(gateway, contact, now=None):
	pin = get_pin(gateway, contact, now=now)
	return pin["solution"] if pin else None
