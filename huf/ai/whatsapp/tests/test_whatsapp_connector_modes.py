# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Inbound, outbound and template sync with and without the frappe_whatsapp connector.

The same scenarios run in both modes with mode-specific expectations: ``TestConnectorMode`` needs
frappe_whatsapp (real doctypes, only Meta faked) and ``TestDirectMode`` needs it absent. Run the module on
both sites (core and full). Window rules are event-based, so they must behave identically in both modes.
"""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_webhook
from huf.ai.whatsapp import management as mgmt
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp import WhatsAppWindowClosed
from huf.ai.gateway_service import process_gateway_event
from huf.ai.whatsapp.tests import test_whatsapp_full_stack as fs


class _Scenarios:
	"""Mode-independent scenarios. Concrete classes provide gateway/phone/secret and helpers."""

	connector = False
	STRANGER = "15559990000"

	def _wamid_posts(self):
		raise NotImplementedError

	def _inbound_event(self, wamid, text="hello"):
		self.assertTrue(self._deliver(wamid, text)["success"])
		return self._events(self.gateway, wamid)[0]

	def _mirrored_rows(self, wamid):
		if not frappe.db.exists("DocType", "WhatsApp Message"):
			return None
		return frappe.db.count("WhatsApp Message", {"message_id": wamid})

	def test_inbound_is_ingested_and_mirrored_only_with_the_connector(self):
		self._inbound_event("wamid.M1")
		self.assertEqual(len(self._events(self.gateway, "wamid.M1")), 1)
		self.assertEqual(self._mirrored_rows("wamid.M1"), 1 if self.connector else None)
		# replays never double up in either mode
		self.assertTrue(self._deliver("wamid.M1")["duplicates"])
		self.assertEqual(len(self._events(self.gateway, "wamid.M1")), 1)
		self.assertEqual(self._mirrored_rows("wamid.M1"), 1 if self.connector else None)

	def test_inbound_opens_the_24h_window_in_both_modes(self):
		self.assertFalse(bridge.window_state(self.gateway.name, fs.SENDER)["open"])
		self._inbound_event("wamid.W1")
		self.assertTrue(bridge.window_state(self.gateway.name, fs.SENDER)["open"])

	def test_reply_goes_out_by_the_mode_specific_path(self):
		name = self._inbound_event("wamid.R1")
		process_gateway_event(name)
		frappe.set_user("Administrator")
		posts = self._wamid_posts()
		self.assertEqual(len(posts), 1, posts)
		self.assertTrue(posts[0]["url"].endswith(f"/{self.PHONE}/messages"))
		self.assertEqual((posts[0]["body"]["to"], posts[0]["body"]["text"]["body"]), (fs.SENDER, "reply 1"))
		outgoing = (
			frappe.db.count("WhatsApp Message", {"type": "Outgoing"})
			if frappe.db.exists("DocType", "WhatsApp Message")
			else None
		)
		if self.connector:
			self.assertGreaterEqual(outgoing, 1)  # sent through frappe_whatsapp, so the row exists
		else:
			self.assertIsNone(outgoing)  # direct Graph call: nothing is mirrored
		self.assertEqual(frappe.db.get_value("Gateway Event", name, "reply_status"), "sent")

	def test_closed_window_refuses_free_form_in_both_modes(self):
		adapter = gateway_webhook.get_gateway_adapter(frappe.get_doc("Gateway", self.gateway.name))
		from huf.ai.gateway_adapters.types import GatewayReply

		with self.assertRaises(WhatsAppWindowClosed):
			adapter.send_reply(GatewayReply(conversation_id=self.STRANGER, text="hello?"))
		self.assertEqual(self._wamid_posts(), [])

	def test_template_sync_availability_follows_the_connector(self):
		raise NotImplementedError


class TestConnectorMode(_Scenarios, fs.TestWhatsAppMultiGateway):
	connector = True
	for _name in [n for n in dir(fs.TestWhatsAppMultiGateway) if n.startswith("test_")]:
		locals()[_name] = None
	del _name

	def setUp(self):
		super().setUp()
		self.gateway, self.PHONE = self.gateway_a, self.PHONE_A

	def _deliver(self, wamid, text="hello"):
		return self._post(self.gateway_a, self._inbound_payload(self.PHONE_A, self.WABA_A, wamid, text), self.SECRET_A)

	def _wamid_posts(self):
		return [
			p
			for p in self.meta.posts("/messages")
			if isinstance(p["body"], dict) and p["body"].get("type") in ("text", "template")
		]

	def _meta_templates(self):
		# template_name is unique site-wide in frappe_whatsapp, so keep the name per-run
		self.tpl = f"cmode_{self.suffix.lower()}"
		self.meta.template_list = {
			"data": [
				{
					"name": self.tpl, "language": "en_US", "status": "APPROVED", "category": "UTILITY", "id": "t-1",
					"components": [{"type": "BODY", "text": "Hello {{1}}", "example": {"body_text": [["Ann"]]}}],
				}
			]
		}

	def test_template_sync_availability_follows_the_connector(self):
		self._meta_templates()
		first = mgmt.sync_templates(gateway_name=self.gateway_a.name)
		self.assertTrue(first["success"], first)
		self.assertEqual((first["imported"], first["updated"]), (1, 0), first)
		listed = mgmt.list_templates(gateway_name=self.gateway_a.name)["templates"]
		self.assertIn(self.tpl, [t["name"].rsplit("-en_US", 1)[0] for t in listed])
		# a second sync neither re-imports nor re-pushes anything to Meta
		again = mgmt.sync_templates(gateway_name=self.gateway_a.name)
		self.assertEqual((again["imported"], again["updated"], again["unchanged"]), (0, 0, 1), again)
		self.assertEqual(self.meta.posts("/message_templates"), [])
		other = mgmt.list_templates(gateway_name=self.gateway_b.name)["templates"]
		self.assertNotIn(self.tpl, [t["name"].rsplit("-en_US", 1)[0] for t in other])

	def test_approved_template_is_sent_through_the_connector_with_a_closed_window(self):
		self._meta_templates()
		mgmt.sync_templates(gateway_name=self.gateway_a.name)
		self.assertFalse(bridge.window_state(self.gateway_a.name, self.STRANGER)["open"])
		result = mgmt.send_template_message(
			gateway_name=self.gateway_a.name, to=self.STRANGER, template_name=self.tpl, language_code="en_US", body_params='["Ann"]'
		)
		self.assertTrue(result["success"], result)
		sent = [p for p in self._wamid_posts() if p["body"]["type"] == "template"]
		self.assertEqual(len(sent), 1)
		self.assertEqual((sent[0]["body"]["to"], sent[0]["body"]["template"]["name"]), (self.STRANGER, self.tpl))


class TestDirectMode(_Scenarios, IntegrationTestCase):
	"""Core-only site: Huf calls the Graph API itself with the integration's credentials."""

	PHONE, SECRET = "5550003333", "direct-secret"

	def setUp(self):
		if bridge.is_available():
			self.skipTest("frappe_whatsapp is installed; the direct-mode assertions cover the core-only site")
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", fs.EXEC_USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": fs.EXEC_USER, "first_name": "WA Exec", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Huf Gateway User")
		suffix = frappe.generate_hash(length=6)
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"WA Direct Agent {suffix}",
				"agent_modality": "Both",
				"instructions": "Direct-mode fixture.",
				"allowed_users": [{"user": fs.EXEC_USER}],
			}
		).insert(ignore_permissions=True)
		integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": self.PHONE},
					{"key": "access_token", "value": "direct-token"},
					{"key": "webhook_verify_token", "value": "verify"},
					{"key": "app_secret", "value": self.SECRET},
				],
			}
		).insert(ignore_permissions=True)
		self.gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"Direct {suffix}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"integration_settings": integration.name,
				"execution_user": fs.EXEC_USER,
				"direct_policy": "Allow list",
				"default_target_type": "Agent",
				"default_agent": agent.name,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Gateway Access Entry",
				"gateway": self.gateway.name,
				"entry_type": "Sender",
				"provider": "WhatsApp",
				"external_id": fs.SENDER,
				"state": "Approved",
			}
		).insert(ignore_permissions=True)
		self.graph_calls = []
		self.agent_calls = []

		def fake_post(url, *, json, headers, timeout):
			self.graph_calls.append({"url": url, "body": json, "headers": headers})
			return fs._Resp({"messages": [{"id": f"wamid.OUT{len(self.graph_calls)}"}]})

		def fake_run(**kwargs):
			self.agent_calls.append(kwargs)
			return {"response": f"reply {len(self.agent_calls)}", "agent_run_id": f"fake-run-{len(self.agent_calls)}"}

		for target, new in (
			("frappe.utils.get_url", lambda *a, **k: "http://gw-wa-core.localhost"),
			# the adapter's default http_post is bound at import, so patch the call it makes
			("requests.post", lambda url, json=None, headers=None, timeout=None, **kw: fake_post(url, json=json, headers=headers, timeout=timeout)),
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
			("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None),
			("huf.ai.agent.integration.run_agent_sync", fake_run),
		):
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)
		prev_ip = getattr(frappe.local, "request_ip", None)
		frappe.local.request_ip = "127.0.0.1"
		self.addCleanup(setattr, frappe.local, "request_ip", prev_ip)
		for target in (patch.object(frappe.db, "commit"), patch("frappe.enqueue")):
			target.start()
			self.addCleanup(target.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _events(self, gateway, wamid=None):
		filters = {"gateway": gateway.name}
		if wamid:
			filters["provider_event_id"] = wamid
		return frappe.get_all("Gateway Event", filters=filters, pluck="name")

	def _deliver(self, wamid, text="hello"):
		import hashlib
		import hmac
		import json
		from types import SimpleNamespace

		from huf.ai.gateway_adapters import GatewayInboundRequest

		raw = json.dumps(fs._payload([fs._text_msg(wamid, text)]) | {}).encode()
		raw = raw.replace(fs.PHONE_ID.encode(), self.PHONE.encode())
		sig = "sha256=" + hmac.new(self.SECRET.encode(), raw, hashlib.sha256).hexdigest()
		request = GatewayInboundRequest(raw, headers={"X-Hub-Signature-256": sig}, query={}, method="POST")
		prev = getattr(frappe.local, "request", None)
		frappe.local.request = SimpleNamespace(args={"gateway_name": self.gateway.name})
		self.addCleanup(setattr, frappe.local, "request", prev)
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
			return gateway_webhook.handle_gateway_webhook()

	def _wamid_posts(self):
		return [c for c in self.graph_calls if c["body"].get("type") in ("text", "template")]

	def test_direct_reply_authenticates_with_the_integration_token(self):
		process_gateway_event(self._inbound_event("wamid.T1"))
		frappe.set_user("Administrator")
		self.assertEqual(self._wamid_posts()[0]["headers"]["Authorization"], "Bearer direct-token")

	def test_direct_template_send_ignores_the_window(self):
		adapter = gateway_webhook.get_gateway_adapter(frappe.get_doc("Gateway", self.gateway.name))
		delivery = adapter.send_template(self.STRANGER, "welcome", "en_US", ["Ann"])
		self.assertTrue(delivery.provider_message_id.startswith("wamid.OUT"))
		body = self._wamid_posts()[0]["body"]
		self.assertEqual((body["type"], body["template"]["name"], body["to"]), ("template", "welcome", self.STRANGER))

	def test_template_sync_availability_follows_the_connector(self):
		self.assertEqual(mgmt.sync_templates(), {"success": False, "error": "bridge_unavailable"})
		self.assertEqual(mgmt.list_templates(), {"success": False, "error": "bridge_unavailable"})
		self.assertEqual(
			mgmt.send_template_message(gateway_name=self.gateway.name, to=self.STRANGER, template_name="welcome"),
			{"success": False, "error": "bridge_unavailable"},
		)
		self.assertEqual(self.graph_calls, [])
