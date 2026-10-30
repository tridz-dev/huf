"""BE-WIDGETS: click-to-chat link, widget snippet, [ref:...] opt-in hook."""

from __future__ import annotations

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.ai.channels import widgets
from huf.ai.gateway_adapters.tests.test_gateway_pairing_hardening import _GatewayFixture

PHONE = "15551240001"
FRESH = "15551240002"


class TestWidgetUrls(IntegrationTestCase):
	def test_url_encoding_and_ref(self):
		self.assertEqual(widgets.build_wa_me_url("15551234567"), "https://wa.me/15551234567")
		self.assertEqual(
			widgets.build_wa_me_url("15551234567", "Hi & hello", "site-1"),
			"https://wa.me/15551234567?text=Hi%20%26%20hello%20%5Bref%3Asite-1%5D",
		)

	def test_bad_ref_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			widgets.build_wa_me_url("1555", None, "a b]")


class TestWidgetApi(_GatewayFixture, IntegrationTestCase):
	def tearDown(self):
		for name in self.gateways:
			frappe.db.delete("Gateway Consent", {"gateway": name})
		frappe.set_user("Administrator")
		super().tearDown()

	def rows(self, gateway, sender):
		return frappe.get_all("Gateway Consent", filters={"gateway": gateway, "sender_id": sender, "category": "marketing_messages"},
			fields=["value", "source"])

	def test_digits_normalisation_and_snippet(self):
		frappe.set_user("Administrator")
		gw = self.make_gateway("W", policy="Allow list")
		out = widgets.get_click_to_chat(gw, prefill="Hello", ref="ad1", phone="+1 (555) 123-4567")
		self.assertTrue(out["wa_me_url"].startswith("https://wa.me/15551234567?text="))
		self.assertIsNone(out["qr_svg"])
		snip = widgets.get_widget_snippet(gw, ref="ad1", label='A"B', phone="00 1 555 123 4567")["snippet"]
		self.assertIn("/assets/huf/js/huf-wa-widget.js", snip)
		self.assertIn('data-number="15551234567"', snip)
		self.assertIn("&quot;", snip)

	def test_permission(self):
		gw = self.make_gateway("W", policy="Allow list")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			widgets.get_click_to_chat(gw, phone="15551234567")

	def test_ref_message_records_widget_opt_in(self):
		gw = self.make_gateway("W", policy="Allow list")
		widgets.ref_opt_in_hook({"gateway": gw, "context": {"sender_id": FRESH, "message_text": "Hi [ref:ad1]"}})
		rows = self.rows(gw, FRESH)
		self.assertEqual([(r["value"], r["source"]) for r in rows], [("resume", "widget")])

	def test_no_ref_no_row_and_returns_none(self):
		gw = self.make_gateway("W", policy="Allow list")
		self.assertIsNone(widgets.ref_opt_in_hook({"gateway": gw, "context": {"sender_id": FRESH, "message_text": "hi"}}))
		self.assertEqual(self.rows(gw, FRESH), [])

	def test_stopped_number_not_reopted(self):
		gw = self.make_gateway("W", policy="Allow list")
		self.make_entry(gw, PHONE, state="Approved")
		self.ingest(gw, PHONE, "STOP")
		self.assertTrue(gsvc.is_opted_out(gw, PHONE))
		widgets.ref_opt_in_hook({"gateway": gw, "context": {"sender_id": PHONE, "message_text": "[ref:x]"}})
		self.assertTrue(gsvc.is_opted_out(gw, PHONE))
		self.assertEqual(self.rows(gw, PHONE), [])
