# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Two WhatsApp gateways on one site: signatures, message log and management lists never cross.

Reuses the two-gateway fixture of ``TestWhatsAppMultiGateway`` (real doctypes, fake Meta only), so it
needs frappe_whatsapp and is skipped otherwise.
"""

from __future__ import annotations

import frappe

from huf.ai.whatsapp import management as mgmt
from huf.ai.tests import test_whatsapp_full_stack as fs


class TestWhatsAppGatewayIsolation(fs.TestWhatsAppMultiGateway):
	# Inherit the fixtures and helpers only; the base class's own tests already run in its module.
	for _name in [n for n in dir(fs.TestWhatsAppMultiGateway) if n.startswith("test_")]:
		locals()[_name] = None
	del _name

	def _inbound(self, label, wamid):
		gateway, phone, waba, secret = (
			(self.gateway_a, self.PHONE_A, self.WABA_A, self.SECRET_A)
			if label == "A"
			else (self.gateway_b, self.PHONE_B, self.WABA_B, self.SECRET_B)
		)
		return self._post(gateway, self._inbound_payload(phone, waba, wamid), secret)

	def test_signature_of_a_is_rejected_on_b_and_vice_versa(self):
		for target, other_secret, wamid in (
			(self.gateway_b, self.SECRET_A, "wamid.XB"),
			(self.gateway_a, self.SECRET_B, "wamid.XA"),
		):
			phone, waba = (
				(self.PHONE_B, self.WABA_B) if target is self.gateway_b else (self.PHONE_A, self.WABA_A)
			)
			result = self._post(target, self._inbound_payload(phone, waba, wamid), other_secret)
			self.assertEqual(result, {"success": False, "error": "Provider verification failed"})
			self.assertEqual(frappe.local.response.http_status_code, 401)
			self.assertEqual(self._events(target), [])
			self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": wamid}), 0)
			self.assertTrue(frappe.db.get_value("Gateway", target.name, "last_signature_failure_at"))
		# the matching secrets still work afterwards
		self.assertTrue(self._inbound("A", "wamid.OKA")["success"])
		self.assertTrue(self._inbound("B", "wamid.OKB")["success"])

	def test_failed_signature_on_one_gateway_leaves_the_other_untouched(self):
		self._post(self.gateway_b, self._inbound_payload(self.PHONE_B, self.WABA_B, "wamid.F"), self.SECRET_A)
		self.assertFalse(frappe.db.get_value("Gateway", self.gateway_a.name, "last_signature_failure_at"))

	def test_message_log_is_scoped_per_gateway(self):
		self._inbound("A", "wamid.LOGA")
		self._inbound("B", "wamid.LOGB")
		log_a = {i["message_id"] for i in mgmt.list_message_log(gateway_name=self.gateway_a.name)["items"]}
		log_b = {i["message_id"] for i in mgmt.list_message_log(gateway_name=self.gateway_b.name)["items"]}
		self.assertIn("wamid.LOGA", log_a)
		self.assertNotIn("wamid.LOGB", log_a)
		self.assertIn("wamid.LOGB", log_b)
		self.assertNotIn("wamid.LOGA", log_b)

	def test_message_log_search_cannot_reach_the_other_gateway(self):
		self._inbound("B", "wamid.SECRETB")
		found = mgmt.list_message_log(gateway_name=self.gateway_a.name, q="wamid.SECRETB")
		self.assertEqual(found["items"], [])
		by_phone = mgmt.list_message_log(gateway_name=self.gateway_a.name, phone=fs.SENDER)
		self.assertNotIn("wamid.SECRETB", {i["message_id"] for i in by_phone["items"]})

	def test_message_and_conversation_lists_are_scoped_per_gateway(self):
		self._inbound("A", "wamid.MA")
		self._inbound("B", "wamid.MB")
		for gateway, mine, theirs in ((self.gateway_a, "wamid.MA", "wamid.MB"), (self.gateway_b, "wamid.MB", "wamid.MA")):
			ids = {m["message_id"] for m in mgmt.list_messages(gateway_name=gateway.name)["messages"]}
			self.assertIn(mine, ids)
			self.assertNotIn(theirs, ids)
			accounts = {
				c["last_message"]["whatsapp_account"] for c in mgmt.list_conversations(gateway_name=gateway.name)["conversations"]
			}
			self.assertEqual(accounts, {self.account_a.name if gateway is self.gateway_a else self.account_b.name})

	def test_setup_status_reports_each_gateways_own_state(self):
		self._post(self.gateway_b, self._inbound_payload(self.PHONE_B, self.WABA_B, "wamid.S"), self.SECRET_A)
		gw_a = mgmt.get_setup_status(gateway_name=self.gateway_a.name)["gateway"]
		gw_b = mgmt.get_setup_status(gateway_name=self.gateway_b.name)["gateway"]
		self.assertIn("MG%20A", gw_a["webhook_url"])
		self.assertIn("MG%20B", gw_b["webhook_url"])
		self.assertEqual(gw_b["health"], "blocked")
		self.assertIsNone(gw_a["last_signature_failure_at"])
		self.assertNotEqual(gw_a["phone_number_id"], gw_b["phone_number_id"])
