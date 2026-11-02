"""Inbound WhatsApp ``order`` messages (customer sent a catalog cart) -> structured data + an order record.

With ERPNext installed and the sender matched to a Customer, a DRAFT Sales Order is created through the ERP
tool path (``tools_erp.create_order``, never submitted, stamped with the Channel Conversation). Otherwise a
``WhatsApp Order`` is stored. Either way the structured cart is attached to the Gateway Event
(``raw_payload.commerce_order``) and the agent-visible message text names the saved order.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from huf.ai.channels import run_as
from huf.ai.channels.adapters.erpnext import erpnext_installed, find_customer_by_phone

MAX_ITEMS = 50


def _num(value: Any) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def parse_order(msg: Any) -> dict[str, Any] | None:
	"""Structured cart from a Meta inbound ``order`` message, or None when it is not one / has no usable item.

	Meta shape: ``order.catalog_id``, ``order.text``, ``order.product_items[{product_retailer_id, quantity,
	item_price, currency}]``.
	"""
	if not isinstance(msg, dict) or msg.get("type") != "order" or not isinstance(msg.get("order"), dict):
		return None
	order = msg["order"]
	items = []
	for it in (order.get("product_items") or [])[:MAX_ITEMS]:
		if not isinstance(it, dict):
			continue
		rid = str(it.get("product_retailer_id") or "").strip()
		qty = _num(it.get("quantity"))
		if not rid or qty <= 0:
			continue
		items.append(
			{
				"retailer_id": rid,
				"qty": qty,
				"price": _num(it.get("item_price")),
				"currency": str(it.get("currency") or "").strip()[:8],
			}
		)
	if not items:
		return None
	currency = next((i["currency"] for i in items if i["currency"]), "")
	return {
		"catalog_id": str(order.get("catalog_id") or ""),
		"text": str(order.get("text") or "").strip(),
		"items": items,
		"currency": currency,
		"total": round(sum(i["qty"] * i["price"] for i in items), 2),
	}


def _event_message(event) -> dict:
	raw = getattr(event, "raw_payload", None)
	if isinstance(raw, (str, bytes)):
		try:
			raw = json.loads(raw)
		except ValueError:
			raw = {}
	return raw if isinstance(raw, dict) else {}


def _create_draft_sales_order(conversation, items: list[dict]) -> dict | None:
	"""Draft SO through the ERP tool path; None when ERPNext is absent, the customer unknown or the tool refuses."""
	if not erpnext_installed() or not find_customer_by_phone(conversation.contact_handle):
		return None
	from huf.ai.channels.tools import erp as tools_erp

	token = run_as.set_current_conversation(conversation.name)
	try:
		res = tools_erp.create_order([{"item_code": i["retailer_id"], "qty": i["qty"]} for i in items])
	finally:
		run_as.reset_current_conversation(token)
	return res if res.get("success") else None


def _create_whatsapp_order(gateway: str, conversation, handle: str, cart: dict, message_id: str) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Order",
			"gateway": gateway,
			"conversation": conversation.name if conversation else None,
			"contact_handle": handle,
			"status": "Draft",
			"currency": cart["currency"],
			"customer_note": cart["text"],
			"source_message_id": message_id,
			"items": [
				{"retailer_id": i["retailer_id"], "item_name": i["retailer_id"], "qty": i["qty"], "price": i["price"], "currency": i["currency"]}
				for i in cart["items"]
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def summary_text(cart: dict, record: dict) -> str:
	lines = ", ".join(f"{i['retailer_id']} x{i['qty']:g}" for i in cart["items"])
	total = f" total {cart['total']:g} {cart['currency']}".rstrip() if cart["total"] else ""
	note = f' Note: "{cart["text"]}".' if cart["text"] else ""
	return f"Customer sent cart: {lines};{total}.{note} Saved as {record['doctype']} {record['name']} (draft)."


def handle_inbound_order(gateway: str, event, context: dict | None = None) -> dict[str, Any] | None:
	"""Process an admitted inbound ``order`` event. Returns the structured result, or None for non-orders.

	Idempotent per provider message id. Never raises into ingest.
	"""
	raw = _event_message(event)
	cart = parse_order(raw.get("message"))
	if not cart:
		return None
	if raw.get("commerce_order"):
		return raw["commerce_order"]
	message_id = str(getattr(event, "provider_event_id", "") or (raw.get("message") or {}).get("id") or "")
	try:
		existing = message_id and frappe.db.get_value("WhatsApp Order", {"source_message_id": message_id}, "name")
		handle = str((context or {}).get("sender_id") or getattr(event, "sender_id", "") or "")
		from huf.ai.channels import conversation as conv

		conversation = conv.get_or_create_conversation(gateway, handle) if handle else None
		if existing:
			record = {"doctype": "WhatsApp Order", "name": existing}
		else:
			so = _create_draft_sales_order(conversation, cart["items"]) if conversation else None
			if so:
				record = {"doctype": "Sales Order", "name": so["order"]}
			else:
				record = {"doctype": "WhatsApp Order", "name": _create_whatsapp_order(gateway, conversation, handle, cart, message_id)}
		result = {**cart, "record": record, "summary": summary_text(cart, record)}
		raw["commerce_order"] = result
		event.db_set("raw_payload", json.dumps(raw, default=str), update_modified=False)
		event.db_set("message_text", result["summary"][:1000], update_modified=False)
		return result
	except Exception:
		frappe.log_error(title="WhatsApp inbound order not saved")
		return None
