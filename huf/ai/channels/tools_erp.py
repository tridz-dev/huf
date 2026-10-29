"""ERPNext agent tools for channel runs: customer lookup, draft Sales Order, order status.

Every tool is bound to the current conversation's customer; no cross-customer reads. Orders are only
ever created as drafts (docstatus 0) and stamped with the Channel Conversation (run_as.stamp_audit).
"""

from __future__ import annotations

import json

import frappe

from huf.ai.channels import run_as
from huf.ai.channels.adapters.erpnext import erpnext_installed, find_customer_by_phone

NOT_INSTALLED = {"success": False, "error": "ERPNext is not installed on this site; this tool is unavailable."}


def _conversation_handle() -> str | None:
	name = run_as.current_conversation()
	if not name:
		return None
	return frappe.db.get_value("Channel Conversation", name, "contact_handle")


def _conversation_customer() -> tuple[str | None, dict | None]:
	"""(customer, error) for the current conversation."""
	handle = _conversation_handle()
	if not handle:
		return None, {"success": False, "error": "No active channel conversation; cannot identify the customer."}
	found = find_customer_by_phone(handle)
	if not found:
		return None, {"success": False, "error": "No ERPNext customer matches this conversation's phone number."}
	return found["customer"], None


def lookup_customer(phone: str | None = None) -> dict:
	"""Find the ERPNext customer/contact for a phone (default: the conversation sender)."""
	if not erpnext_installed():
		return dict(NOT_INSTALLED)
	phone = phone or _conversation_handle()
	if not phone:
		return {"success": False, "error": "No phone given and no active channel conversation."}
	found = find_customer_by_phone(phone)
	if not found:
		return {"success": True, "found": False}
	return {"success": True, "found": True, **found}


def _default_company() -> str | None:
	return (
		frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)


def create_order(items=None, delivery_date: str | None = None) -> dict:
	"""Create a DRAFT Sales Order for the conversation's customer. Never submitted."""
	if not erpnext_installed():
		return dict(NOT_INSTALLED)
	if isinstance(items, str):
		try:
			items = json.loads(items)
		except ValueError:
			return {"success": False, "error": "items must be a list of {item_code, qty}."}
	if not items or not isinstance(items, list):
		return {"success": False, "error": "items is required: a list of {item_code, qty}."}
	customer, err = _conversation_customer()
	if err:
		return err
	rows = []
	for it in items:
		code, qty = (it or {}).get("item_code"), (it or {}).get("qty")
		try:
			qty = float(qty)
		except (TypeError, ValueError):
			qty = 0
		if not code or qty <= 0:
			return {"success": False, "error": "Each item needs an item_code and a positive qty."}
		if not frappe.db.exists("Item", code):
			return {"success": False, "error": f"Item {code} does not exist."}
		row = {"item_code": code, "qty": qty}
		rate = frappe.db.get_value("Item Price", {"item_code": code, "selling": 1}, "price_list_rate")
		if rate is not None:
			row["rate"] = rate
		rows.append(row)
	company = _default_company()
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": customer,
			"transaction_date": frappe.utils.nowdate(),
			"delivery_date": delivery_date or frappe.utils.add_days(frappe.utils.nowdate(), 7),
			"items": rows,
			"docstatus": 0,
		}
	)
	doc.flags.ignore_permissions = False
	try:
		doc.run_method("set_missing_values")  # price list / currency / rates, as the desk form does
		doc.insert()  # draft only: never submit
	except frappe.ValidationError as exc:
		return {"success": False, "error": f"Could not create the order: {str(exc)[:200]}"}
	return {"success": True, "order": doc.name, "status": "Draft", "customer": customer}


def order_status(order_name: str | None = None) -> dict:
	"""Status/delivery/billing of the conversation customer's recent orders."""
	if not erpnext_installed():
		return dict(NOT_INSTALLED)
	customer, err = _conversation_customer()
	if err:
		return err
	filters = {"customer": customer}
	if order_name:
		filters["name"] = order_name
	rows = frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=["name", "status", "docstatus", "transaction_date", "delivery_date", "per_delivered", "per_billed", "grand_total"],
		order_by="creation desc",
		limit=1 if order_name else 5,
	)
	if order_name and not rows:
		return {"success": False, "error": "No such order for this customer."}
	return {"success": True, "customer": customer, "orders": rows}
