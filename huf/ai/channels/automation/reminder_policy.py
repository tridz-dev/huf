"""Shared gates and DB-backed throttle for proactive (non-reply) WhatsApp reminders."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

LOG = "Channel Reminder Log"


def kill_switch_active(gateway: str | None = None) -> bool:
	"""Site-wide broadcast emergency stop (the only persistent stop flag; per-gateway pause only pauses broadcasts)."""
	from huf.ai.whatsapp.broadcast.schedule import emergency_stop_active

	return emergency_stop_active()


def has_marketing_opt_in(gateway: str, phone: str) -> bool:
	"""Recorded marketing opt-in (latest Gateway Consent row is ``resume``) and not STOP-opted-out."""
	from huf.ai import gateway_service
	from huf.ai.whatsapp import account_events as events

	key = events._norm_sender(phone)
	if not gateway or not key or gateway_service.is_opted_out(gateway, phone):
		return False
	return events._latest_consent(gateway, key, events.MARKETING) == "resume"


def may_send_proactive(gateway: str, phone: str) -> bool:
	return not kill_switch_active(gateway) and has_marketing_opt_in(gateway, phone)


def recently_sent(kind: str, reference_doctype: str, reference_name: str, within_days: float) -> bool:
	since = add_to_date(now_datetime(), days=-within_days)
	return bool(frappe.db.exists(LOG, {"kind": kind, "reference_doctype": reference_doctype, "reference_name": reference_name, "sent_at": [">=", since]}))


def record(gateway: str, recipient: str, kind: str, reference_doctype: str, reference_name: str) -> None:
	frappe.get_doc({
		"doctype": LOG, "gateway": gateway, "recipient": recipient, "kind": kind,
		"reference_doctype": reference_doctype, "reference_name": reference_name, "sent_at": now_datetime(),
	}).insert(ignore_permissions=True)


def count(kind: str, reference_doctype: str, reference_name: str) -> int:
	return int(frappe.db.count(LOG, {"kind": kind, "reference_doctype": reference_doctype, "reference_name": reference_name}) or 0)
