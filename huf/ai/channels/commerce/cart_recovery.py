"""Hourly cart recovery: one ``cart_reminder`` template per unpaid Draft WhatsApp Order."""

from __future__ import annotations

import frappe
from frappe.utils import add_to_date, now_datetime

ORDER = "WhatsApp Order"
TEMPLATE = "cart_reminder"


def run_cart_recovery() -> int:
	"""Scheduler entry. Returns the number of reminders sent."""
	if not frappe.db.exists("DocType", ORDER) or not frappe.db.has_column(ORDER, "reminder_sent_at"):
		return 0
	sent = 0
	for gw in frappe.get_all("Gateway", filters={"is_enabled": 1, "cart_recovery_hours": [">", 0]}, fields=["name", "cart_recovery_hours"]):
		cutoff = add_to_date(now_datetime(), hours=-int(gw.cart_recovery_hours))
		orders = frappe.get_all(
			ORDER,
			filters={"status": "Draft", "creation": ["<=", cutoff], "reminder_sent_at": ["is", "not set"]},
			fields=["name", "conversation", "total", "currency", "payment_status"],
			limit_page_length=200,
		)
		for o in orders:
			if o.payment_status == "Paid" or not o.conversation:
				continue
			if _remind(gw.name, o):
				sent += 1
	return sent


def _remind(gateway: str, order) -> bool:
	conv = frappe.db.get_value("Channel Conversation", order.conversation, ["gateway", "contact_handle"], as_dict=True)
	if not conv or conv.gateway != gateway:
		return False
	from huf.ai import gateway_service
	from huf.ai.channels import reply_api

	if gateway_service.is_opted_out(gateway, conv.contact_handle):
		return False
	res = reply_api.deliver_reply(order.conversation, template=TEMPLATE, params=[order.name, f"{order.currency} {order.total}"])
	if res.get("status") != "sent":
		return False
	frappe.db.set_value(ORDER, order.name, "reminder_sent_at", now_datetime())
	return True
