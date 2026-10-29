import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from huf.ai.channels import analytics

GW = "GW-ANALYTICS-TEST"


class TestAnalytics(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.today = nowdate()
		self.span = (add_days(self.today, -6), self.today)

	def _conv(self, status="ai", **kw):
		d = frappe.get_doc(
			{"doctype": "Channel Conversation", "channel": "whatsapp", "contact_handle": frappe.generate_hash(length=8), "status": status, **kw}
		)
		d.flags.ignore_links = True
		d.insert(ignore_permissions=True)
		return d

	def _broadcast(self, **kw):
		counts = {k: kw.pop(k) for k in ("sent", "delivered", "read", "failed") if k in kw}
		d = frappe.get_doc(
			{"doctype": "WhatsApp Broadcast", "title": "t", "category": "marketing", "template": "tpl", "template_name": "tpl", **kw}
		)
		d.flags.ignore_links = True
		d.insert(ignore_permissions=True)
		for k, v in counts.items():
			frappe.db.set_value("WhatsApp Broadcast", d.name, k, v, update_modified=False)
		return d

	def _recipient(self, bc, phone, status="delivered"):
		d = frappe.get_doc(
			{"doctype": "WhatsApp Broadcast Recipient", "broadcast": bc, "recipient": phone, "status": status, "sent_at": f"{self.today} 10:00:00"}
		)
		d.flags.ignore_links = True
		frappe.flags.in_broadcast_api = True
		self.addCleanup(setattr, frappe.flags, "in_broadcast_api", False)
		d.insert(ignore_permissions=True)

	def test_aggregates(self):
		self._conv("ai", gateway=GW)
		self._conv("handed_off", gateway=GW)
		self._conv("closed", gateway=GW)
		self._conv("ai", gateway="OTHER-GW")
		self._broadcast(gateway=GW, sent=10, delivered=8, read=5, failed=2)
		res = analytics.get_analytics(GW, *self.span)
		self.assertEqual(len(res["volume_by_day"]), 7)
		self.assertEqual(res["volume_by_day"][-1]["conversations"], 3)
		self.assertAlmostEqual(res["handoff_rate"], 0.3333, places=3)
		self.assertAlmostEqual(res["ai_resolution_rate"], 0.6667, places=3)
		self.assertEqual(res["broadcast_funnel"], {"sent": 10, "delivered": 8, "read": 5, "failed": 2})
		self.assertTrue(res["estimated_spend"]["is_estimate"])

	def test_empty_rates_null(self):
		res = analytics.get_analytics(GW, *self.span)
		self.assertIsNone(res["ai_resolution_rate"])
		self.assertIsNone(res["median_first_response_seconds"])

	def test_spend_null_without_rates(self):
		bc = self._broadcast(gateway=GW)
		self._recipient(bc.name, "+919876543210")
		analytics.save_rate_card("", [])
		spend = analytics.get_analytics(GW, *self.span)["estimated_spend"]
		self.assertIsNone(spend["amount"])
		self.assertTrue(spend["missing_rates"])

	def test_spend_with_rates(self):
		bc = self._broadcast(gateway=GW)
		self._recipient(bc.name, "+919876543210")
		self._recipient(bc.name, "+919876543211", "read")
		self._recipient(bc.name, "+919876543212", "failed")
		analytics.save_rate_card("usd", [{"market": "in", "category": "marketing", "rate": 0.5}])
		spend = analytics.get_analytics(GW, *self.span)["estimated_spend"]
		self.assertEqual(spend["amount"], 1.0)
		self.assertEqual(spend["currency"], "USD")
		self.assertFalse(spend["missing_rates"])
		self.assertTrue(spend["is_estimate"])
		self._recipient(bc.name, "+14155550100")
		spend = analytics.get_analytics(GW, *self.span)["estimated_spend"]
		self.assertIsNone(spend["amount"])
		self.assertTrue(spend["missing_rates"])

	def test_rate_card_validation(self):
		with self.assertRaises(frappe.ValidationError):
			analytics.save_rate_card("USD", [{"market": "IN", "category": "bogus", "rate": 1}])
		with self.assertRaises(frappe.ValidationError):
			analytics.save_rate_card("USD", [{"market": "IN", "category": "utility", "rate": -1}])

	def test_effective_from(self):
		rows = [
			{"market": "IN", "category": "utility", "rate": 1.0, "effective_from": "2026-01-01"},
			{"market": "IN", "category": "utility", "rate": 2.0, "effective_from": "2026-06-01"},
		]
		self.assertEqual(analytics._rate_for(rows, "IN", "utility", "2026-03-01"), 1.0)
		self.assertEqual(analytics._rate_for(rows, "IN", "utility", "2026-07-01"), 2.0)
		self.assertIsNone(analytics._rate_for(rows, "IN", "utility", "2025-01-01"))

	def test_permission(self):
		user = "analytics-noperm@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "NoPerm", "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		frappe.set_user(user)
		for fn, args in ((analytics.get_analytics, (GW,)), (analytics.get_rate_card, ()), (analytics.save_rate_card, ("USD", []))):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)
