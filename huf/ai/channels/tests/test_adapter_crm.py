"""BE-ADAPT-CRM: CRM adapter logic (frappe patched) + integration when the crm app is installed."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import adapters
from huf.ai.channels.adapters import crm


class TestCrmAdapterLogic(unittest.TestCase):
	def test_normalize_phone(self):
		self.assertEqual(crm.normalize_phone("+1 (555) 010-2030"), "15550102030")
		self.assertEqual(crm.normalize_phone(None), "")

	def test_registered(self):
		self.assertEqual(adapters.ADAPTER_MODULES["crm"], "huf.ai.channels.adapters.crm")
		self.assertEqual(crm.Adapter().name, "crm")
		self.assertFalse(crm.Adapter().on_human_reply(None, None))

	def test_find_lead_matches_digits(self):
		with patch.object(crm, "_has", return_value=True), patch.object(
			crm.frappe, "get_all", return_value=[{"name": "CRM-LEAD-1", "mobile_no": "+1 555 010 2030"}]
		):
			self.assertEqual(crm.find_lead("15550102030"), "CRM-LEAD-1")
		self.assertIsNone(crm.find_lead(""))

	def test_find_lead_no_fields(self):
		with patch.object(crm, "_has", return_value=False):
			self.assertIsNone(crm.find_lead("15550102030"))

	def test_create_lead_guards_fields_and_source(self):
		captured = {}
		doc = MagicMock()
		doc.name = "CRM-LEAD-9"

		def fake_get_doc(values):
			captured.update(values)
			return doc

		with patch.object(crm, "_has", side_effect=lambda dt, f: f != "email"), patch.object(
			crm, "_source_exists", side_effect=lambda s: s == "WhatsApp"
		), patch.object(crm.frappe, "get_doc", side_effect=fake_get_doc):
			self.assertEqual(crm.create_lead("15550102030", "Ann", "a@b.c"), "CRM-LEAD-9")
		self.assertEqual(captured["source"], "WhatsApp")
		self.assertEqual(captured["mobile_no"], "+15550102030")
		self.assertNotIn("email", captured)

	def test_create_lead_referral_source(self):
		captured = {}
		doc = MagicMock()
		doc.name = "L"
		with patch.object(crm, "_has", return_value=True), patch.object(crm, "_source_exists", return_value=True), patch.object(
			crm.frappe, "get_doc", side_effect=lambda v: captured.update(v) or doc
		):
			crm.create_lead("15550102030", None, referral={"headline": "Sale"})
		self.assertEqual(captured["source"], "Advertisement")

	def test_handoff_creates_lead_and_note(self):
		conv = MagicMock()
		conv.get.side_effect = lambda k, d=None: {"contact_name": "Ann", "handoff_doctype": None}.get(k, d)
		conv.contact_handle = "15550102030"
		with patch.object(crm, "find_lead", return_value=None), patch.object(crm, "create_lead", return_value="CRM-LEAD-2"), patch.object(
			crm, "referral_for", return_value={}
		), patch.object(crm, "add_note") as add_note:
			self.assertEqual(crm.Adapter().handoff(conv, "wants a quote", "high"), ("CRM Lead", "CRM-LEAD-2"))
		self.assertIn("wants a quote", add_note.call_args[0][2])

	def test_append_inbound_noop_without_link(self):
		conv = MagicMock()
		conv.get.return_value = None
		with patch.object(crm, "add_note") as add_note:
			crm.Adapter().append_inbound(conv, "hi")
		add_note.assert_not_called()


@unittest.skipUnless("crm" in frappe.get_installed_apps(), "Frappe CRM not installed")
class TestCrmAdapterIntegration(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)

	def test_create_then_find_lead(self):
		phone = "9" + str(int(frappe.generate_hash(length=7), 16) % 10**9).zfill(9)
		name = crm.create_lead(phone, "Test WA")
		self.assertEqual(crm.find_lead(phone), name)
		crm.add_note(name, "t", "<p>x</p>")
