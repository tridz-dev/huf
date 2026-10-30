"""Hourly cart recovery: one ``cart_reminder`` template per unpaid Draft WhatsApp Order.

Marketing-category send: needs a recorded marketing opt-in, honours STOP and the emergency stop. A failed send is
stamped (``reminder_attempted_at``) and retried at most once, no sooner than 24h later.
"""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.channels.automation import reminder_policy

ORDER = "WhatsApp Order"
TEMPLATE = "cart_reminder"
FAILED_KIND = "cart_recovery_failed"
RETRY_AFTER_HOURS = 24


def run_cart_recovery() -> int:
	"""Scheduler entry. Returns the number of reminders sent."""
	if not frappe.db.exists("DocType", ORDER) or not all(frappe.db.has_column(ORDER, c) for c in ("reminder_sent_at", "reminder_attempted_at")):
		return 0
	if reminder_policy.kill_switch_active():
		return 0
	sent = 0
	now = now_datetime()
	retry_before = add_to_date(now, hours=-RETRY_AFTER_HOURS)
	for gw in frappe.get_all("Gateway", filters={"is_enabled": 1, "cart_recovery_hours": [">", 0]}, fields=["name", "cart_recovery_hours"]):
		cutoff = add_to_date(now, hours=-int(gw.cart_recovery_hours))
		orders = frappe.get_all(
			ORDER,
			filters={"gateway": gw.name, "status": "Draft", "creation": ["<=", cutoff], "reminder_sent_at": ["is", "not set"]},
			or_filters=[["reminder_attempted_at", "is", "not set"], ["reminder_attempted_at", "<=", retry_before]],
			fields=["name", "conversation", "total", "currency", "payment_status", "reminder_attempted_at"],
			limit_page_length=200,
		)
		for o in orders:
			if o.payment_status == "Paid" or not o.conversation:
				continue
			if o.reminder_attempted_at and reminder_policy.count(FAILED_KIND, ORDER, o.name) >= 2:
				continue  # first send + one retry already failed
			if _remind(gw.name, o):
				sent += 1
	return sent


def _remind(gateway: str, order) -> bool:
	conv = frappe.db.get_value("Channel Conversation", order.conversation, ["gateway", "contact_handle"], as_dict=True)
	if not conv or conv.gateway != gateway:
		return False
	if not reminder_policy.may_send_proactive(gateway, conv.contact_handle):
		return False
	from huf.ai.channels import reply_api

	res = reply_api.deliver_reply(
		order.conversation, template=TEMPLATE, params=[order.name, f"{order.currency} {order.total}"], category="marketing"
	)
	if res.get("status") != "sent":
		frappe.db.set_value(ORDER, order.name, "reminder_attempted_at", now_datetime())
		reminder_policy.record(gateway, conv.contact_handle, FAILED_KIND, ORDER, order.name)
		return False
	frappe.db.set_value(ORDER, order.name, "reminder_sent_at", now_datetime())
	return True
