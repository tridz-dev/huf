"""HUFCRM-04a: per-channel (sms/email) consent."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import channel_consent as cc

PHONE = "+1 (555) 123-0099"
EMAIL = "Buyer.N04a@Example.com"
NOTE = "Signed form at store opening"


class TestChannelConsent(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._clean()

	def tearDown(self):
		self._clean()

	def _clean(self):
		frappe.db.delete(cc.DOCTYPE, {"recipient": ["in", ["15551230099", "buyer.n04a@example.com", "15551230098"]]})

	def test_marketing_needs_opt_in_utility_does_not(self):
		self.assertEqual(cc.has_consent("sms", PHONE, "marketing"), (False, "no_opt_in"))
		self.assertEqual(cc.has_consent("sms", PHONE, "utility"), (True, "ok"))
		cc.record_opt_in("sms", PHONE, "api", NOTE)
		self.assertEqual(cc.has_consent("sms", "15551230099", "marketing"), (True, "ok"))

	def test_email_normalized(self):
		cc.record_opt_in("email", EMAIL, "manual", NOTE)
		self.assertEqual(cc.has_consent("email", "buyer.n04a@example.com", "marketing"), (True, "ok"))

	def test_channels_are_independent(self):
		cc.record_opt_in("sms", PHONE)
		self.assertFalse(cc.has_consent("email", "x@y.co", "marketing")[0])
		self.assertEqual(cc.has_consent("email", PHONE, "utility"), (False, "invalid_recipient"))

	def test_stop_blocks_all_and_import_does_not_override(self):
		cc.record_opt_in("sms", PHONE)
		cc.record_opt_out("sms", PHONE, "all")
		self.assertEqual(cc.has_consent("sms", PHONE, "utility"), (False, "opted_out"))
		self.assertEqual(cc.has_consent("sms", PHONE, "marketing"), (False, "opted_out"))
		out = cc.import_opt_ins("sms", [PHONE, "15551230098", "bad"], NOTE)
		self.assertEqual((out["skipped_opted_out"], out["created"], out["invalid"]), (1, 1, 1))
		self.assertFalse(cc.has_consent("sms", PHONE, "utility")[0])

	def test_marketing_opt_out_keeps_utility(self):
		cc.record_opt_in("email", EMAIL)
		cc.record_opt_out("email", EMAIL, "marketing")
		self.assertEqual(cc.has_consent("email", EMAIL, "marketing"), (False, "marketing_opted_out"))
		self.assertEqual(cc.has_consent("email", EMAIL, "utility"), (True, "ok"))

	def test_invalid_inputs_and_attestation(self):
		self.assertEqual(cc.has_consent("fax", PHONE, "marketing"), (False, "invalid_channel"))
		self.assertEqual(cc.has_consent("sms", PHONE, "spam"), (False, "invalid_purpose"))
		with self.assertRaises(frappe.ValidationError):
			cc.import_opt_ins("sms", [PHONE], "")
		row = frappe.get_all(cc.DOCTYPE, filters={"recipient": "15551230099"}, fields=["source"])
		self.assertEqual(row, [])
