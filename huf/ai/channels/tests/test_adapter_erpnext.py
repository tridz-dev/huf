"""ERPNext adapter + channel tools: logic tests with frappe patched, plus an integration class."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import tools_erp
from huf.ai.channels.adapters import ADAPTER_MODULES, get_adapter
from huf.ai.channels.adapters import erpnext as erp

ERP = "huf.ai.channels.tools_erp"


class TestErpLogic(IntegrationTestCase):
	def test_registered(self):
		self.assertEqual(ADAPTER_MODULES["erpnext"], "huf.ai.channels.adapters.erpnext")

	def test_handoff_unsupported(self):
		self.assertEqual(erp.Adapter().handoff(MagicMock()), (None, None))

	def test_absent_app_result(self):
		with patch(f"{ERP}.erpnext_installed", return_value=False):
			for res in (tools_erp.lookup_customer("1"), tools_erp.create_order([{"item_code": "A", "qty": 1}]), tools_erp.order_status()):
				self.assertFalse(res["success"])
				self.assertIn("not installed", res["error"])
		with patch.object(erp, "erpnext_installed", return_value=False):
			self.assertIsNone(erp.Adapter().lookup_customer("123456789"))

	def test_phone_match(self):
		self.assertTrue(erp._phone_matches("+91 98765 43210", "9876543210"))
		self.assertFalse(erp._phone_matches("9876543210", "9876543211"))

	def test_create_order_is_draft_and_never_submitted(self):
		doc = MagicMock(name="SO")
		doc.name = "SO-1"
		with (
			patch(f"{ERP}.erpnext_installed", return_value=True),
			patch(f"{ERP}._conversation_customer", return_value=("CUST-A", None)),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", return_value=10),
			patch(f"{ERP}._default_company", return_value="Co"),
			patch("frappe.utils.nowdate", return_value="2026-01-01"),
			patch("frappe.utils.add_days", return_value="2026-01-08"),
			patch.object(frappe, "get_doc", return_value=doc) as gd,
		):
			res = tools_erp.create_order([{"item_code": "I", "qty": 2}])
		self.assertTrue(res["success"])
		spec = gd.call_args[0][0]
		self.assertEqual(spec["docstatus"], 0)
		self.assertEqual(spec["customer"], "CUST-A")
		doc.insert.assert_called_once()
		doc.submit.assert_not_called()

	def test_create_order_validates_items(self):
		with patch(f"{ERP}.erpnext_installed", return_value=True), patch(f"{ERP}._conversation_customer", return_value=("C", None)):
			self.assertFalse(tools_erp.create_order([])["success"])
			self.assertFalse(tools_erp.create_order([{"item_code": "I", "qty": 0}])["success"])

	def test_order_status_customer_isolation(self):
		with (
			patch(f"{ERP}.erpnext_installed", return_value=True),
			patch(f"{ERP}._conversation_customer", return_value=("CUST-A", None)),
			patch.object(frappe, "get_all", return_value=[]) as ga,
		):
			res = tools_erp.order_status("SO-OTHER")
		self.assertFalse(res["success"])
		self.assertEqual(ga.call_args.kwargs["filters"], {"customer": "CUST-A", "name": "SO-OTHER"})

	def test_no_conversation_no_customer(self):
		with patch(f"{ERP}.erpnext_installed", return_value=True), patch(f"{ERP}._conversation_handle", return_value=None):
			self.assertFalse(tools_erp.order_status()["success"])

	def test_lookup_defaults_to_sender(self):
		with (
			patch(f"{ERP}.erpnext_installed", return_value=True),
			patch(f"{ERP}._conversation_handle", return_value="999"),
			patch(f"{ERP}.find_customer_by_phone", return_value={"customer": "C", "contact": "K"}) as f,
		):
			res = tools_erp.lookup_customer()
		f.assert_called_once_with("999")
		self.assertEqual(res["customer"], "C")

	def test_get_adapter_without_app_falls_back(self):
		with patch.object(frappe, "get_installed_apps", return_value=["frappe"]):
			self.assertEqual(get_adapter("erpnext").name, "none")


@unittest.skipUnless("erpnext" in frappe.get_installed_apps(), "erpnext not installed")
class TestErpIntegration(IntegrationTestCase):
	def test_lookup_unknown_phone(self):
		self.assertIsNone(erp.Adapter().lookup_customer("+000000000000001"))
