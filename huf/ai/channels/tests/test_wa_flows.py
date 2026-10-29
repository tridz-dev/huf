"""WhatsApp Flows: list/sync, send payload, nfm_reply recording + summary, permission."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels import wa_flows
from huf.ai.gateway_adapters import whatsapp_inbound as inbound
from huf.ai.gateway_adapters import whatsapp_messages as wm


def _resp(body, status=200):
	r = MagicMock()
	r.status_code = status
	r.json.return_value = body
	return r


class TestWaFlows(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": "555" + str(int(frappe.generate_hash(length=7), 16) % 10**8).zfill(8)},
					{"key": "access_token", "value": "tok"},
					{"key": "business_account_id", "value": "waba1"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": "sec"},
				],
			}
		).insert(ignore_permissions=True)
		self.gw = frappe.get_doc(
			{
				"doctype": "Gateway", "gateway_name": "Flows " + frappe.generate_hash(length=6), "provider": "WhatsApp",
				"is_enabled": 1, "integration_settings": settings.name, "execution_user": "Administrator",
				"direct_policy": "Allow list",
			}
		).insert(ignore_permissions=True)

	def _flow(self, fid="F1", name="Signup", status="PUBLISHED"):
		return frappe.get_doc(
			{"doctype": "WhatsApp Flow", "gateway": self.gw.name, "flow_id": fid, "flow_name": name, "status": status}
		).insert(ignore_permissions=True)

	def test_list_syncs_cache(self):
		self._flow("OLD", "Gone")
		calls = []

		def http_get(url, params=None, headers=None):
			calls.append(url)
			return _resp({"data": [{"id": "F1", "name": "Signup", "status": "PUBLISHED", "categories": ["SIGN_UP"]}]})

		rows = wa_flows.sync_flows(self.gw.name, http_get=http_get)
		self.assertTrue(calls[0].endswith("/waba1/flows"))
		self.assertEqual([r["flow_id"] for r in rows], ["F1"])
		self.assertEqual(rows[0]["categories"], "SIGN_UP")
		self.assertFalse(frappe.db.exists("WhatsApp Flow", {"flow_id": "OLD"}))

	def test_list_requires_admin(self):
		user = "flows-nobody@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "N", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			wa_flows.list_wa_flows(self.gw.name)

	def test_payload_shape(self):
		payload, errors = wm.build_flow_payload(
			"15550001111", "Fill in", flow_id="F1", flow_cta="Open", flow_token="t", screen="S1", flow_data={"a": 1}
		)
		self.assertFalse(errors)
		inter = payload["interactive"]
		self.assertEqual(inter["type"], "flow")
		params = inter["action"]["parameters"]
		self.assertEqual(inter["action"]["name"], "flow")
		self.assertEqual((params["flow_id"], params["flow_cta"], params["flow_token"]), ("F1", "Open", "t"))
		self.assertEqual(params["flow_action_payload"], {"screen": "S1", "data": {"a": 1}})

	def test_send_flow_builds_spec_and_gates(self):
		self._flow()
		sent = {}

		def send(acct, to, kind, spec):
			sent.update(kind=kind, spec=spec)
			return {"message_id": "wamid.1"}

		with (
			patch("huf.ai.whatsapp.management._free_form_gate", return_value=None),
			patch("huf.ai.whatsapp.management._resolve_account_name", return_value="acct"),
			patch("huf.ai.whatsapp.outbound_policy.check_recipient"),
		):
			out = wa_flows.send_flow(self.gw.name, "15550001111", "Signup", "Open", screen="S1", data={"x": 1}, send=send)
		self.assertTrue(out["success"])
		self.assertEqual(sent["kind"], "flow")
		self.assertEqual(sent["spec"]["flow_id"], "F1")
		self.assertTrue(sent["spec"]["flow_token"].startswith("huf:F1:"))
		with patch("huf.ai.whatsapp.management._free_form_gate", return_value={"success": False, "error": "window_closed"}), patch(
			"huf.ai.whatsapp.outbound_policy.check_recipient"
		):
			self.assertEqual(wa_flows.send_flow(self.gw.name, "15550001111", "Signup", "Open")["error"], "window_closed")
		self.assertEqual(wa_flows.send_flow(self.gw.name, "15550001111", "Nope", "Open")["error"], "flow_not_found")

	def test_nfm_reply_summary_text(self):
		msg = {"type": "interactive", "interactive": {"type": "nfm_reply", "nfm_reply": {
			"name": "flow", "response_json": json.dumps({"flow_token": "huf:F1:abc", "city": "Pune", "n": 2})}}}
		self.assertEqual(inbound.render_message_text(msg), "Form submitted: city=Pune, n=2")

	def test_nfm_reply_hook_records_response(self):
		flow = self._flow()
		conv = frappe.get_doc(
			{"doctype": "Channel Conversation", "gateway": self.gw.name, "channel": "whatsapp", "contact_handle": "15550003333"}
		).insert(ignore_permissions=True)
		nfm = {"name": "flow", "response_json": json.dumps({"flow_token": "huf:F1:abc", "city": "Pune"})}
		event = frappe.get_doc(
			{
				"doctype": "Gateway Event", "gateway": self.gw.name, "idempotency_key": frappe.generate_hash(length=12),
				"status": "Queued", "target_type": "Agent", "target_agent": "Fake", "message_text": "x",
				"sender_id": "15550003333", "channel_conversation": conv.name,
				"raw_payload": json.dumps({"message": {"interactive": {"type": "nfm_reply", "nfm_reply": nfm}}}),
			}
		)
		event.insert(ignore_permissions=True, ignore_links=True)
		self.assertIsNone(wa_flows.flow_response_hook({"gateway": self.gw.name, "event": event.name}))
		row = frappe.get_all("WhatsApp Flow Response", {"gateway": self.gw.name}, ["conversation", "flow", "flow_token", "response"])
		self.assertEqual(len(row), 1)
		self.assertEqual((row[0].conversation, row[0].flow, row[0].flow_token), (conv.name, flow.name, "huf:F1:abc"))
		self.assertEqual(json.loads(row[0].response)["city"], "Pune")
