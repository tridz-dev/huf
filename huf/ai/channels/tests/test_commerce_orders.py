"""Inbound WhatsApp ``order`` parsing and order records (WhatsApp Order when ERP absent, draft SO otherwise)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.commerce import orders

OR = "huf.ai.channels.commerce.orders"

MSG = {
	"id": "wamid.ORDER1", "from": "15550001111", "type": "order",
	"order": {
		"catalog_id": "CAT1", "text": "deliver friday",
		"product_items": [
			{"product_retailer_id": "A-1", "quantity": 2, "item_price": 5.5, "currency": "USD"},
			{"product_retailer_id": "B-2", "quantity": "1", "item_price": 10, "currency": "USD"},
			{"product_retailer_id": "", "quantity": 1},
			{"product_retailer_id": "Z", "quantity": 0},
		],
	},
}


def _event(msg=MSG):
	ev = MagicMock()
	ev.raw_payload = {"message": msg}
	ev.provider_event_id = msg["id"]
	ev.sender_id = msg["from"]
	return ev


class TestParseOrder(IntegrationTestCase):
	def test_structured(self):
		cart = orders.parse_order(MSG)
		self.assertEqual(cart["catalog_id"], "CAT1")
		self.assertEqual(cart["text"], "deliver friday")
		self.assertEqual(cart["items"], [
			{"retailer_id": "A-1", "qty": 2.0, "price": 5.5, "currency": "USD"},
			{"retailer_id": "B-2", "qty": 1.0, "price": 10.0, "currency": "USD"},
		])
		self.assertEqual((cart["total"], cart["currency"]), (21.0, "USD"))

	def test_non_orders(self):
		self.assertIsNone(orders.parse_order({"type": "text", "text": {"body": "hi"}}))
		self.assertIsNone(orders.parse_order({"type": "order", "order": {"product_items": []}}))
		self.assertIsNone(orders.parse_order(None))

	def test_handle_ignores_non_order(self):
		ev = MagicMock()
		ev.raw_payload = json.dumps({"message": {"type": "text"}})
		self.assertIsNone(orders.handle_inbound_order("GW", ev, {}))


class TestOrderRecords(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		sfx = frappe.generate_hash(length=6)
		phone = "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)
		settings = frappe.get_doc({
			"doctype": "Integration Settings", "service": "whatsapp",
			"credentials": [
				{"key": "phone_number_id", "value": phone}, {"key": "access_token", "value": "tok"},
				{"key": "webhook_verify_token", "value": "verify"}, {"key": "app_secret", "value": "sec"},
			],
		}).insert(ignore_permissions=True)
		self.gw = frappe.get_doc({
			"doctype": "Gateway", "gateway_name": f"Ord {sfx}", "provider": "WhatsApp", "is_enabled": 1,
			"integration_settings": settings.name, "execution_user": "Administrator", "direct_policy": "Allow list",
		}).insert(ignore_permissions=True)

	def test_whatsapp_order_when_erp_absent(self):
		ev = _event()
		with patch(f"{OR}.erpnext_installed", return_value=False):
			res = orders.handle_inbound_order(self.gw.name, ev, {"sender_id": "15550001111"})
		self.assertEqual(res["record"]["doctype"], "WhatsApp Order")
		doc = frappe.get_doc("WhatsApp Order", res["record"]["name"])
		self.assertEqual((doc.gateway, doc.contact_handle, doc.status, doc.source_message_id), (self.gw.name, "15550001111", "Draft", "wamid.ORDER1"))
		self.assertEqual([(r.retailer_id, r.qty, r.price, r.currency) for r in doc.items], [("A-1", 2, 5.5, "USD"), ("B-2", 1, 10, "USD")])
		self.assertEqual(doc.total, 21)
		self.assertTrue(doc.conversation)
		# agent-visible text and structured data land on the event
		saved = {c.args[0]: c.args[1] for c in ev.db_set.call_args_list}
		self.assertIn("Customer sent cart", saved["message_text"])
		self.assertIn(doc.name, saved["message_text"])
		self.assertEqual(json.loads(saved["raw_payload"])["commerce_order"]["items"][0]["retailer_id"], "A-1")

	def test_idempotent_per_message(self):
		with patch(f"{OR}.erpnext_installed", return_value=False):
			a = orders.handle_inbound_order(self.gw.name, _event(), {"sender_id": "15550001111"})
			b = orders.handle_inbound_order(self.gw.name, _event(), {"sender_id": "15550001111"})
		self.assertEqual(a["record"], b["record"])
		self.assertEqual(frappe.db.count("WhatsApp Order", {"source_message_id": "wamid.ORDER1"}), 1)

	def test_draft_sales_order_via_erp_path(self):
		conv = MagicMock()
		conv.name, conv.contact_handle = "CONV1", "15550001111"
		ev = _event()
		with (
			patch(f"{OR}.erpnext_installed", return_value=True),
			patch(f"{OR}.find_customer_by_phone", return_value={"customer": "CUST-A", "contact": "C"}),
			patch("huf.ai.channels.conversation.get_or_create_conversation", return_value=conv),
			patch("huf.ai.channels.tools.erp.create_order", return_value={"success": True, "order": "SO-9", "status": "Draft"}) as co,
			patch(f"{OR}._create_whatsapp_order") as wo,
		):
			res = orders.handle_inbound_order("GW", ev, {"sender_id": "15550001111"})
		self.assertEqual(res["record"], {"doctype": "Sales Order", "name": "SO-9"})
		co.assert_called_once_with([{"item_code": "A-1", "qty": 2.0}, {"item_code": "B-2", "qty": 1.0}])
		wo.assert_not_called()

	def test_erp_unknown_customer_falls_back_to_whatsapp_order(self):
		conv = MagicMock()
		conv.name, conv.contact_handle = "CONV1", "15550001111"
		with (
			patch(f"{OR}.erpnext_installed", return_value=True),
			patch(f"{OR}.find_customer_by_phone", return_value=None),
			patch("huf.ai.channels.conversation.get_or_create_conversation", return_value=conv),
			patch(f"{OR}._create_whatsapp_order", return_value="WAO-1") as wo,
		):
			res = orders.handle_inbound_order("GW", _event(), {"sender_id": "15550001111"})
		self.assertEqual(res["record"], {"doctype": "WhatsApp Order", "name": "WAO-1"})
		wo.assert_called_once()

	def test_conversation_audit_context_reset(self):
		from huf.ai.channels import run_as

		conv = MagicMock()
		conv.name, conv.contact_handle = "CONV1", "1"
		seen = {}
		def fake(items):
			seen["conv"] = run_as.current_conversation()
			return {"success": True, "order": "SO-1"}
		with (
			patch(f"{OR}.erpnext_installed", return_value=True),
			patch(f"{OR}.find_customer_by_phone", return_value={"customer": "C"}),
			patch("huf.ai.channels.conversation.get_or_create_conversation", return_value=conv),
			patch("huf.ai.channels.tools.erp.create_order", side_effect=fake),
		):
			orders.handle_inbound_order("GW", _event(), {"sender_id": "1"})
		self.assertEqual(seen["conv"], "CONV1")
		self.assertIsNone(run_as.current_conversation())
