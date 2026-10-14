# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp integration tests against a real local fake of the Meta Graph API.

Nothing in the code under test is patched at the HTTP layer: the WhatsApp Account
``url`` and the Integration Settings ``graph_api_url`` point at
:class:`~huf.ai.tests.fake_graph_server.FakeGraphServer`, so genuine ``requests``
calls are made (by Huf and by frappe_whatsapp). The fake validates every request
against Meta's documented schema, and each test fails if it recorded a violation.

Direct-mode tests run on any site; bridge-mode tests need frappe_whatsapp and are
skipped without it.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service, gateway_webhook, whatsapp_management as mgmt
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge
from huf.ai.gateway_adapters.types import GatewayAttachment, GatewayReply
from huf.ai.gateway_adapters.whatsapp import WhatsAppWindowClosed
from huf.ai.tests import fake_graph_server as fake
from huf.ai.tools import whatsapp as wa_tool

SENDER = "15551234567"
EXEC_USER = "wa-fakegraph-exec@example.com"
PNG = (
	b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
	b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeGraphCase(IntegrationTestCase):
	"""Shared server + fixtures."""

	MODE = "direct"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.server = fake.FakeGraphServer().start()
		cls.receiver = fake.WebhookReceiver().start()
		cls._prev_hosts = getattr(frappe.flags, "whatsapp_test_media_hosts", None)
		frappe.flags.whatsapp_test_media_hosts = {cls.server.host}

	@classmethod
	def tearDownClass(cls):
		frappe.flags.whatsapp_test_media_hosts = cls._prev_hosts
		cls.server.stop()
		cls.receiver.stop()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self.server.requests.clear()
		self.server.sent.clear()
		self.server.templates.clear()
		self.server.violations.clear()
		self.receiver.received.clear()
		self._build_fixtures()
		for target, new in (
			("huf.ai.gateway_webhook._ingest_rate_gate", lambda: None),
		):
			patcher = patch(target, new)
			patcher.start()
			self.addCleanup(patcher.stop)
		self._prev_request = getattr(frappe.local, "request", None)
		self._prev_ip = getattr(frappe.local, "request_ip", None)
		frappe.local.request_ip = "127.0.0.1"
		if not getattr(frappe.local, "response", None):
			frappe.local.response = frappe._dict()
		self.addCleanup(self._restore)
		for target in (frappe.db, "commit"), (frappe, "enqueue"):
			patcher = patch.object(*target)
			patcher.start()
			self.addCleanup(patcher.stop)

	def tearDown(self):
		try:
			self.server.assert_clean()  # a schema violation fails the test even if it was swallowed
		finally:
			frappe.db.rollback()

	def _restore(self):
		frappe.local.request = self._prev_request
		frappe.local.request_ip = self._prev_ip

	# ------------------------------------------------------------- fixtures
	def _build_fixtures(self):
		srv = self.server
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		if not frappe.db.exists("User", EXEC_USER):
			user = frappe.get_doc(
				{"doctype": "User", "email": EXEC_USER, "first_name": "FG Exec", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
			user.add_roles("Huf Gateway User")
		suffix = frappe.generate_hash(length=6)
		self.account = None
		if bridge.is_available():
			self.account = frappe.get_doc(
				{
					"doctype": "WhatsApp Account",
					"account_name": f"FG Account {suffix}",
					"status": "Active",
					"url": srv.url,
					"version": srv.version,
					"phone_id": srv.phone_id,
					"business_id": srv.waba_id,
					"app_id": srv.app_id,
					"token": srv.token,
					"webhook_verify_token": "verify-me",
					"is_default_outgoing": 1,
				}
			).insert(ignore_permissions=True)
		# one enabled gateway per phone number id (the Gateway rejects a second): only the mode under test is enabled
		self.direct_gateway = self._make_gateway(f"FG Direct {suffix}", None) if self.MODE == "direct" else None
		self.bridge_gateway = (
			self._make_gateway(f"FG Bridge {suffix}", self.account.name) if self.account and self.MODE == "bridge" else None
		)

	def _make_gateway(self, name, account):
		srv = self.server
		integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": srv.phone_id},
					{"key": "access_token", "value": srv.token},
					{"key": "webhook_verify_token", "value": "verify-me"},
					{"key": "app_secret", "value": fake.APP_SECRET},
					{"key": "graph_api_url", "value": srv.url},
				],
			}
		).insert(ignore_permissions=True)
		values = {
			"doctype": "Gateway",
			"gateway_name": name,
			"provider": "WhatsApp",
			"is_enabled": 1,
			"integration_settings": integration.name,
			"execution_user": EXEC_USER,
			"direct_policy": "Allow list",
		}
		if account:
			values["whatsapp_account"] = account
		gateway = frappe.get_doc(values).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Gateway Access Entry",
				"gateway": gateway.name,
				"entry_type": "Sender",
				"provider": "WhatsApp",
				"external_id": SENDER,
				"state": "Approved",
			}
		).insert(ignore_permissions=True)
		return gateway

	# -------------------------------------------------------------- helpers
	def _deliver_webhook(self, gateway, payload, signature=None):
		"""POST over real HTTP to the stand-in receiver, then run the captured request through Huf."""
		resp = fake.post_signed_webhook(self.receiver.url, payload, fake.APP_SECRET, signature)
		self.assertEqual(resp.status_code, 200)
		captured = self.receiver.take()
		request = GatewayInboundRequest(
			captured["body"], headers=captured["headers"], query={"gateway_name": gateway.name}, method="POST"
		)
		frappe.local.request = SimpleNamespace(args={"gateway_name": gateway.name}, host="localhost", path="/", method="POST")
		try:
			with patch("huf.ai.gateway_webhook._inbound_request", return_value=request):
				return gateway_webhook.handle_gateway_webhook()
		finally:
			frappe.local.request = self._prev_request

	def _inbound(self, gateway, wamid="wamid.IN1", text="hello"):
		result = self._deliver_webhook(gateway, fake.inbound_text_webhook(self.server.phone_id, SENDER, wamid, text))
		self.assertTrue(result["success"], result)
		return frappe.get_doc(
			"Gateway Event", frappe.get_all("Gateway Event", filters={"gateway": gateway.name, "provider_event_id": wamid}, pluck="name")[0]
		)

	def _need_bridge(self):
		if not self.account:
			self.skipTest("frappe_whatsapp is not installed on this site")

	def _make_template(self, **overrides):
		payload = {
			"template_name": "fg_order_update",
			"category": "UTILITY",
			"language_code": "en_US",
			"body": "Hi {{1}}, order ships {{2}}",
			"sample_values": "Ann,tomorrow",
			"header_type": "TEXT",
			"header": "Order {{1}}",
			"sample": "A-100",
			"footer": "Thanks for shopping",
			"buttons": [
				{"type": "URL", "text": "Track order", "url": "https://shop.example.com/track/{{1}}", "example": "https://shop.example.com/track/A-100"},
				{"type": "PHONE_NUMBER", "text": "Call us", "phone_number": "+15550001234"},
			],
		}
		payload.update(overrides)
		return mgmt.create_template(account=self.account.name, payload=json.dumps(payload))


class TestDirectMode(FakeGraphCase):
	MODE = "direct"

	def test_text_reply(self):
		event = self._inbound(self.direct_gateway)
		delivery = gateway_webhook.send_gateway_reply(self.direct_gateway, event, "agent answer")
		self.assertTrue(delivery.provider_message_id.startswith("wamid.FAKE"))
		sent = self.server.sent[-1]
		self.assertEqual((sent["to"], sent["type"], sent["text"]["body"]), (SENDER, "text", "agent answer"))
		self.assertEqual(sent["context"], {"message_id": "wamid.IN1"})
		self.assertEqual(self.server.requests_to("POST", "/messages")[0]["headers"]["authorization"], f"Bearer {self.server.token}")

	def test_rejected_message_surfaces_meta_error(self):
		# an invalid recipient is rejected by the fake exactly as Meta would; the error reaches the caller
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		with self.assertRaises(ValueError) as cm:
			adapter._graph_send({"messaging_product": "whatsapp", "to": "abc", "type": "text", "text": {"body": "x"}})
		self.assertIn("'to' is required", str(cm.exception))
		self.assertEqual(len(self.server.violations), 1)
		self.server.violations.clear()  # expected; do not fail tearDown

	def test_template_with_header_and_button_params(self):
		self.server.templates[("fg_direct", "en_US")] = {
			"id": "1", "name": "fg_direct", "language": "en_US", "category": "UTILITY", "status": "APPROVED", "components": [],
			"spec": {
				"HEADER": {"format": "TEXT", "text": "Order {{1}}"},
				"BODY": {"text": "Hi {{1}}"},
				"BUTTONS": {"buttons": [{"type": "URL", "text": "Track", "url": "https://x.example/{{1}}"}]},
			},
		}
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		delivery = adapter.send_template(
			SENDER, "fg_direct", "en_US", ["Ann"], header_params=["A-100"],
			button_params=[{"index": 0, "sub_type": "url", "text": "A-100"}],
		)
		self.assertTrue(delivery.provider_message_id)
		comps = self.server.sent[-1]["template"]["components"]
		self.assertEqual([c["type"] for c in comps], ["header", "body", "button"])
		self.assertEqual(comps[2], {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "A-100"}]})
		# structured validation error before any request
		before = len(self.server.requests)
		with self.assertRaises(bridge.BridgeError) as cm:
			adapter.send_template(SENDER, "fg_direct", "en_US", ["bad\ntext"])
		self.assertEqual(cm.exception.payload["error"], "validation_failed")
		self.assertEqual(len(self.server.requests), before)

	def test_media_send_kinds_and_window(self):
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		with self.assertRaises(WhatsAppWindowClosed):
			adapter.send_media(SENDER, "image", link="https://cdn.example/a.png")
		self.assertEqual(self.server.requests, [])
		self._inbound(self.direct_gateway)
		adapter.send_media(SENDER, "image", link="https://cdn.example/a.png", caption="pic")
		adapter.send_media(SENDER, "document", link="https://cdn.example/a.pdf", caption="doc", filename="a.pdf")
		adapter.send_media(SENDER, "audio", media_id="MEDIA123")
		adapter.send_media(SENDER, "video", link="https://cdn.example/a.mp4")
		sent = self.server.sent
		self.assertEqual(sent[0]["image"], {"link": "https://cdn.example/a.png", "caption": "pic"})
		self.assertEqual(sent[1]["document"], {"link": "https://cdn.example/a.pdf", "caption": "doc", "filename": "a.pdf"})
		self.assertEqual(sent[2]["audio"], {"id": "MEDIA123"})
		self.assertEqual(sent[3]["type"], "video")
		with self.assertRaises(bridge.BridgeError) as cm:
			adapter.send_media(SENDER, "audio", link="https://cdn.example/a.mp3", caption="not allowed")
		self.assertEqual(cm.exception.payload["errors"][0]["code"], "not_allowed")

	def test_reply_with_attachment_uses_media_path(self):
		self.assertTrue(gateway_webhook.get_gateway_adapter(self.direct_gateway).capabilities.supports_media_reply)
		self._inbound(self.direct_gateway)
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		adapter.send_reply(
			GatewayReply(
				conversation_id=SENDER, text="here you go",
				attachments=(GatewayAttachment(url="https://cdn.example/a.png", kind="image", mime_type="image/png"),),
			)
		)
		self.assertEqual(self.server.sent[-1]["image"], {"link": "https://cdn.example/a.png", "caption": "here you go"})

	def test_inbound_media_download_direct_mode(self):
		self.server.add_media("MID-D1", "image/png", PNG)
		payload = fake.inbound_media_webhook(self.server.phone_id, SENDER, "wamid.MEDIA1", "image", "MID-D1", "image/png", "look")
		result = self._deliver_webhook(self.direct_gateway, payload)
		self.assertTrue(result["success"], result)
		event = frappe.get_doc("Gateway Event", frappe.get_all("Gateway Event", filters={"gateway": self.direct_gateway.name, "provider_event_id": "wamid.MEDIA1"}, pluck="name")[0])
		saved = gateway_service._save_whatsapp_media(event, self.direct_gateway)
		self.assertEqual(len(saved), 1, "direct-mode gateways must download media with their own credentials")
		file_doc = frappe.get_doc("File", {"file_url": saved[0]})
		self.assertEqual(open(file_doc.get_full_path(), "rb").read(), PNG)
		self.assertEqual(file_doc.is_private, 1)

	def test_media_download_allowlist_is_not_weakened(self):
		self.server.add_media("MID-X", "image/png", PNG)
		creds = {"token": self.server.token, "url": self.server.url}
		self.assertEqual(bridge.download_media(None, "MID-X", credentials=creds)["content"], PNG)
		allowed = frappe.flags.whatsapp_test_media_hosts
		frappe.flags.whatsapp_test_media_hosts = set()
		try:
			with self.assertRaisesRegex(ValueError, "media_url_host_not_allowed"):
				bridge.download_media(None, "MID-X", credentials=creds)
		finally:
			frappe.flags.whatsapp_test_media_hosts = allowed
		frappe.flags.in_test = False  # outside tests the override flags are ignored
		try:
			self.assertFalse(bridge._is_media_host(f"{self.server.url}/media/MID-X"))
			self.assertEqual(bridge.graph_base_url(self.server.url), "https://graph.facebook.com")
		finally:
			frappe.flags.in_test = True
		self.assertFalse(bridge._is_media_host("https://evil.example/media/x"))
		self.assertTrue(bridge._is_media_host("https://lookaside.fbsbx.com/x"))
		self.server.add_media("MID-PDF", "application/zip", b"PK")
		with self.assertRaisesRegex(ValueError, "mime_not_allowed"):
			bridge.download_media(None, "MID-PDF", credentials=creds)

	def test_signed_webhook_forged_signature_and_status(self):
		forged = self._deliver_webhook(
			self.direct_gateway, fake.inbound_text_webhook(self.server.phone_id, SENDER, "wamid.FORGED", "x"),
			signature="sha256=" + "0" * 64,
		)
		self.assertFalse(forged["success"])
		self.assertEqual(frappe.local.response.http_status_code, 401)
		self.assertFalse(frappe.get_all("Gateway Event", filters={"provider_event_id": "wamid.FORGED"}))
		event = self._inbound(self.direct_gateway, "wamid.OK1", "hi there")
		self.assertEqual((event.sender_id, event.message_text, event.verified_sender), (SENDER, "hi there", 1))
		ack = self._deliver_webhook(
			self.direct_gateway, fake.message_status_webhook(self.server.phone_id, "wamid.FAKE000001", "delivered", SENDER)
		)
		self.assertTrue(ack["success"])
		self.assertEqual(ack["messages"], 0)

	def test_agent_tool_send_media_gating(self):
		args = {"to": SENDER, "kind": "image", "link": "https://cdn.example/a.png", "caption": "x", "gateway_name": self.direct_gateway.name}
		refused = json.loads(wa_tool.handle_action("send_media", **args))
		self.assertEqual(refused["error"], "proactive_send_not_permitted")
		self.assertEqual(self.server.requests, [])
		self._inbound(self.direct_gateway)
		with patch.object(wa_tool, "_get_whatsapp_credentials", return_value=(self.server.phone_id, self.server.token)):
			ok = json.loads(wa_tool.handle_action("send_media", **args))
			self.assertTrue(ok["success"], ok)
			bad = json.loads(wa_tool.handle_action("send_media", **{**args, "kind": "sticker"}))
		self.assertEqual(bad["error"], "validation_failed")
		self.assertEqual(self.server.sent[-1]["image"]["link"], "https://cdn.example/a.png")


class TestBridgeMode(FakeGraphCase):
	MODE = "bridge"

	def setUp(self):
		super().setUp()
		self._need_bridge()

	def test_text_reply_creates_one_whatsapp_message_and_one_graph_post(self):
		event = self._inbound(self.bridge_gateway)
		delivery = gateway_webhook.send_gateway_reply(self.bridge_gateway, event, "bridge answer")
		posts = self.server.requests_to("POST", "/messages")
		self.assertEqual(len(posts), 1)
		self.assertEqual(self.server.sent[-1]["text"]["body"], "bridge answer")
		row = frappe.get_doc("WhatsApp Message", {"message_id": delivery.provider_message_id})
		self.assertEqual((row.type, row.to, row.whatsapp_account), ("Outgoing", SENDER, self.account.name))

	def test_rich_template_create_list_sync_approve_send(self):
		created = self._make_template()
		self.assertTrue(created["success"], created)
		stored = self.server.templates[("fg_order_update", "en_US")]
		comps = {c["type"].upper(): c for c in stored["components"]}
		self.assertEqual(comps["HEADER"]["format"], "TEXT")
		self.assertEqual(comps["HEADER"]["example"], {"header_text": ["A-100"]})
		self.assertEqual(comps["BODY"]["example"], {"body_text": [["Ann", "tomorrow"]]})
		self.assertEqual(comps["FOOTER"]["text"], "Thanks for shopping")
		self.assertEqual(
			comps["BUTTONS"]["buttons"],
			[
				{"type": "URL", "text": "Track order", "url": "https://shop.example.com/track/{{1}}", "example": ["https://shop.example.com/track/A-100"]},
				{"type": "PHONE_NUMBER", "text": "Call us", "phone_number": "+15550001234"},
			],
		)
		# doctype mapping
		doc = frappe.get_doc("WhatsApp Templates", created["name"])
		self.assertEqual((doc.header_type, doc.header, doc.sample, doc.footer), ("TEXT", "Order {{1}}", "A-100", "Thanks for shopping"))
		self.assertEqual([(b.button_type, b.url_type) for b in doc.buttons], [("Visit Website", "Dynamic"), ("Call Phone", "Static")])
		self.assertEqual(doc.status, "PENDING")

		listed = mgmt.list_templates(account=self.account.name)["templates"]
		row = next(t for t in listed if t["name"] == created["name"])
		self.assertEqual((row["status"], row["header_type"], row["footer"]), ("PENDING", "TEXT", "Thanks for shopping"))

		# Meta has not approved it yet: sending is rejected by Meta's rules (fake), and surfaces as a structured error
		early = mgmt.send_template_message(
			to=SENDER, template_name="fg_order_update", body_params=json.dumps(["Ann", "today"]),
			header_params=json.dumps(["A-100"]), button_params=json.dumps([{"index": 0, "sub_type": "url", "text": "A-100"}]),
			gateway_name=self.bridge_gateway.name,
		)
		self.assertEqual(early["error"], "send_failed")
		self.assertIn("APPROVED", early["message"])
		self.server.violations.clear()  # expected rejection

		self.server.approve("fg_order_update")
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertTrue(synced["success"], synced)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "status"), "APPROVED")

		sent = mgmt.send_template_message(
			to="+1 555 123 4567", template_name="fg_order_update", body_params=json.dumps(["Ann", "today"]),
			header_params=json.dumps(["A-100"]), button_params=json.dumps([{"index": 0, "sub_type": "url", "text": "A-100"}]),
			gateway_name=self.bridge_gateway.name,
		)
		self.assertTrue(sent["success"], sent)
		body = self.server.sent[-1]
		self.assertEqual(body["to"], SENDER)
		self.assertEqual(body["template"]["name"], "fg_order_update")
		self.assertEqual(body["template"]["language"], {"code": "en_US"})
		by_type = {c["type"]: c for c in body["template"]["components"]}
		self.assertEqual(by_type["header"]["parameters"], [{"type": "text", "text": "A-100"}])
		self.assertEqual(by_type["body"]["parameters"], [{"type": "text", "text": "Ann"}, {"type": "text", "text": "today"}])
		self.assertEqual(by_type["button"]["parameters"], [{"type": "text", "text": "A-100"}])
		# exactly one Graph send, mirrored once into WhatsApp Message with the same wamid
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": body["_wamid"]}), 1)

		# missing dynamic-URL param is a structured error, no request made
		before = len(self.server.requests_to("POST", "/messages"))
		missing = mgmt.send_template_message(
			to=SENDER, template_name="fg_order_update", body_params=json.dumps(["Ann", "today"]),
			header_params=json.dumps(["A-100"]), gateway_name=self.bridge_gateway.name,
		)
		self.assertEqual(missing["error"], "validation_failed")
		self.assertEqual(missing["errors"][0]["field"], "button_params")
		self.assertEqual(len(self.server.requests_to("POST", "/messages")), before)

		# a template that was already sent is referenced by WhatsApp Message rows: refuse BEFORE
		# frappe_whatsapp deletes it on Meta, so Meta and Huf stay in sync
		linked = mgmt.delete_template(name=created["name"])
		self.assertEqual(linked["error"], "template_in_use")
		spare = self._make_template(template_name="fg_spare", header_type=None, header=None, sample=None, footer=None, buttons=None)
		self.assertTrue(spare["success"], spare)
		deleted = mgmt.delete_template(name=spare["name"])
		self.assertTrue(deleted["success"], deleted)
		self.assertNotIn(("fg_spare", "en_US"), self.server.templates)
		self.assertIn(("fg_order_update", "en_US"), self.server.templates)

	def test_sync_imports_preexisting_meta_template_then_send_works(self):
		# fg_preexisting exists on Meta only: no local row, nothing seeded in Huf
		self.server.add_template("fg_preexisting", "en_US", "UTILITY", "APPROVED")
		self.assertFalse(frappe.db.exists("WhatsApp Templates", {"whatsapp_account": self.account.name}))
		synced = mgmt.sync_templates(account=self.account.name)
		self.assertEqual(
			(synced["success"], synced["imported"], synced["updated"], synced["unchanged"]), (True, 1, 0, 0), synced
		)
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])  # import never pushes to Meta
		row = frappe.get_doc("WhatsApp Templates", "fg_preexisting-en_US")
		self.assertEqual(
			(row.actual_name, row.language_code, row.status, row.category, row.header_type, row.header, row.whatsapp_account),
			("fg_preexisting", "en_US", "APPROVED", "UTILITY", "TEXT", "Hello World", self.account.name),
		)
		self.assertEqual(row.footer, "WhatsApp Business Platform sample message")
		self.assertTrue(row.id)

		# second sync: nothing to do
		again = mgmt.sync_templates(account=self.account.name)
		self.assertEqual((again["imported"], again["updated"], again["unchanged"]), (0, 0, 1))
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])

		sent = mgmt.send_template_message(to=SENDER, template_name="fg_preexisting", gateway_name=self.bridge_gateway.name)
		self.assertTrue(sent["success"], sent)
		self.assertEqual(self.server.sent[-1]["template"]["name"], "fg_preexisting")
		self.assertEqual(self.server.sent[-1]["template"]["language"], {"code": "en_US"})
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])

	def test_image_header_template_uploads_sample_and_sends_media_link(self):
		sample = self.server.add_file("samples/header.png", "image/png", PNG)
		created = self._make_template(
			template_name="fg_promo_image", header_type="IMAGE", header=None, sample=sample,
			body="Sale for {{1}}", sample_values="Ann", buttons=[
				{"type": "QUICK_REPLY", "text": "Yes"}, {"type": "QUICK_REPLY", "text": "No"},
			],
		)
		self.assertTrue(created["success"], created)
		self.assertEqual(len(self.server.requests_to("POST", "/uploads")), 1)
		comps = {c["type"].upper(): c for c in self.server.templates[("fg_promo_image", "en_US")]["components"]}
		self.assertEqual(comps["HEADER"]["format"], "IMAGE")
		self.assertTrue(comps["HEADER"]["example"]["header_handle"][0].startswith("4:"))
		self.assertEqual([b["type"] for b in comps["BUTTONS"]["buttons"]], ["QUICK_REPLY", "QUICK_REPLY"])
		self.server.approve("fg_promo_image")
		# media header with no link is a structured error
		no_link = mgmt.send_template_message(to=SENDER, template_name="fg_promo_image", body_params=json.dumps(["Ann"]), gateway_name=self.bridge_gateway.name)
		# an IMAGE header falls back to the template's own sample link (frappe_whatsapp behaviour)
		self.assertTrue(no_link["success"], no_link)
		self.assertEqual(self.server.sent[-1]["template"]["components"][1]["parameters"][0]["image"]["link"], sample)
		ok = mgmt.send_template_message(
			to=SENDER, template_name="fg_promo_image", body_params=json.dumps(["Ann"]), gateway_name=self.bridge_gateway.name,
			header_params=json.dumps([{"type": "image", "link": f"{self.server.url}/files/samples/header.png"}]),
		)
		self.assertTrue(ok["success"], ok)
		by_type = {}
		for c in self.server.sent[-1]["template"]["components"]:
			by_type.setdefault(c["type"], []).append(c)
		self.assertEqual(by_type["header"][0]["parameters"][0]["image"]["link"], f"{self.server.url}/files/samples/header.png")
		self.assertNotIn("button", by_type)  # quick replies need no send-time parameters

	def test_plain_template_send_goes_through_frappe_whatsapp(self):
		created = self._make_template(
			template_name="fg_plain", header_type=None, header=None, sample=None, footer=None, buttons=None,
			body="Hello {{1}}", sample_values="Ann",
		)
		self.assertTrue(created["success"], created)
		self.server.approve("fg_plain")
		mgmt.sync_templates(account=self.account.name)
		result = mgmt.send_template_message(to=SENDER, template_name="fg_plain", body_params=json.dumps(["Zed"]), gateway_name=self.bridge_gateway.name)
		self.assertTrue(result["success"], result)
		self.assertEqual(self.server.sent[-1]["template"]["components"], [{"type": "body", "parameters": [{"type": "text", "text": "Zed"}]}])

	def test_invalid_templates_return_structured_errors_without_calling_meta(self):
		cases = {
			"too_many_quick_replies": {"buttons": [{"type": "QUICK_REPLY", "text": f"b{i}"} for i in range(4)]},
			"too_many_cta_buttons": {"buttons": [
				{"type": "URL", "text": "a", "url": "https://a.example"}, {"type": "URL", "text": "b", "url": "https://b.example"},
				{"type": "PHONE_NUMBER", "text": "c", "phone_number": "+15550001234"}]},
			"too_long": {"footer": "x" * 61},
			"unsupported_header_type": {"header_type": "VIDEO", "header": None},
			"sample_count": {"sample_values": "only-one"},
			"bad_placeholder": {"body": "Hi {{x}}"},
		}
		for code, override in cases.items():
			res = self._make_template(**override)
			self.assertEqual(res["error"], "validation_failed", (code, res))
			self.assertIn(code, [e["code"] for e in res["errors"]], (code, res))
		long_header = self._make_template(header="h" * 61)
		self.assertIn("too_long", [e["code"] for e in long_header["errors"]])
		long_button = self._make_template(buttons=[{"type": "QUICK_REPLY", "text": "x" * 26}])
		self.assertEqual(long_button["errors"][0]["field"], "buttons[0].text")
		long_body = self._make_template(body="x" * 1025, sample_values="")
		self.assertEqual(long_body["errors"][0]["code"], "too_long")
		two_vars = self._make_template(header="{{1}} and {{2}}")
		self.assertIn("too_many_variables", [e["code"] for e in two_vars["errors"]])
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])
		self.assertEqual(frappe.db.count("WhatsApp Templates", {"template_name": "fg_order_update"}), 0)

	def test_media_send_via_management_and_window(self):
		args = {"gateway_name": self.bridge_gateway.name, "to": SENDER, "kind": "image", "link": "https://cdn.example/a.png", "caption": "pic"}
		closed = mgmt.send_media_message(**args)
		self.assertEqual(closed["error"], "window_closed")
		self.assertEqual(self.server.requests, [])
		self._inbound(self.bridge_gateway)
		ok = mgmt.send_media_message(**args)
		self.assertTrue(ok["success"], ok)
		self.assertEqual(self.server.sent[-1]["image"], {"link": "https://cdn.example/a.png", "caption": "pic"})
		row = frappe.get_doc("WhatsApp Message", {"message_id": ok["message_id"]})
		self.assertEqual((row.content_type, row.attach, row.type), ("image", "https://cdn.example/a.png", "Outgoing"))
		doc = mgmt.send_media_message(**{**args, "kind": "document"})
		self.assertTrue(doc["success"], doc)
		self.assertEqual(self.server.sent[-1]["type"], "document")
		bad = mgmt.send_media_message(**{**args, "kind": "gif"})
		self.assertEqual(bad["error"], "validation_failed")
		private = mgmt.send_media_message(gateway_name=self.bridge_gateway.name, to=SENDER, kind="image", file_url="/private/files/x.png")
		self.assertEqual(private["error"], "invalid_file")

	def test_reply_with_attachment_via_bridge(self):
		self._inbound(self.bridge_gateway)
		adapter = gateway_webhook.get_gateway_adapter(self.bridge_gateway)
		delivery = adapter.send_reply(
			GatewayReply(
				conversation_id=SENDER, text="doc for you",
				attachments=(GatewayAttachment(url="https://cdn.example/a.pdf", kind="document", filename="a.pdf"),),
			)
		)
		self.assertEqual(self.server.sent[-1]["document"]["link"], "https://cdn.example/a.pdf")
		self.assertTrue(frappe.db.exists("WhatsApp Message", {"message_id": delivery.provider_message_id}))

	def test_tool_send_media_and_create_template_gating(self):
		args = {"to": SENDER, "kind": "image", "link": "https://cdn.example/a.png", "gateway_name": self.bridge_gateway.name}
		self.assertEqual(json.loads(wa_tool.handle_action("send_media", **args))["error"], "proactive_send_not_permitted")
		self._inbound(self.bridge_gateway)
		ok = json.loads(wa_tool.handle_action("send_media", **args))
		self.assertTrue(ok["success"], ok)
		self.assertEqual(self.server.sent[-1]["type"], "image")
		refused = json.loads(wa_tool.handle_action("create_template", template_name="t_x", category="UTILITY", language_code="en_US", body="hi"))
		self.assertEqual(refused["error"], "management_not_permitted")

	def test_inbound_media_download_via_bridge_account(self):
		self.server.add_media("MID-B1", "image/png", PNG)
		payload = fake.inbound_media_webhook(self.server.phone_id, SENDER, "wamid.MEDIA2", "image", "MID-B1", "image/png")
		self.assertTrue(self._deliver_webhook(self.bridge_gateway, payload)["success"])
		event = frappe.get_doc("Gateway Event", frappe.get_all("Gateway Event", filters={"gateway": self.bridge_gateway.name, "provider_event_id": "wamid.MEDIA2"}, pluck="name")[0])
		saved = gateway_service._save_whatsapp_media(event, self.bridge_gateway)
		self.assertEqual(len(saved), 1)
		self.assertEqual(open(frappe.get_doc("File", {"file_url": saved[0]}).get_full_path(), "rb").read(), PNG)
		media_gets = self.server.requests_to("GET", "/media/MID-B1")
		self.assertEqual(media_gets[0]["headers"]["authorization"], f"Bearer {self.server.token}")

	def test_signed_webhooks_update_message_and_template_status(self):
		event = self._inbound(self.bridge_gateway)
		self.assertEqual(frappe.db.count("WhatsApp Message", {"message_id": "wamid.IN1", "type": "Incoming"}), 1)
		delivery = gateway_webhook.send_gateway_reply(self.bridge_gateway, event, "ping")
		status = self._deliver_webhook(
			self.bridge_gateway, fake.message_status_webhook(self.server.phone_id, delivery.provider_message_id, "delivered", SENDER)
		)
		self.assertEqual(status["forwarded"], 1)
		self.assertEqual(frappe.db.get_value("WhatsApp Message", {"message_id": delivery.provider_message_id}, "status"), "delivered")
		created = self._make_template(template_name="fg_hook", header_type=None, header=None, sample=None, footer=None, buttons=None)
		self.assertTrue(created["success"], created)
		approved = self.server.approve("fg_hook")
		result = self._deliver_webhook(self.bridge_gateway, approved)
		self.assertEqual(result["template_updates"], 1)
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "status"), "APPROVED")


class TestFakeGraphServerEnforcesSchema(unittest.TestCase):
	"""The fake must itself reject what Meta rejects, otherwise the tests above prove nothing."""

	@classmethod
	def setUpClass(cls):
		cls.server = fake.FakeGraphServer().start()

	@classmethod
	def tearDownClass(cls):
		cls.server.stop()

	def setUp(self):
		self.server.violations.clear()
		self.server.templates.clear()

	def _post(self, path, body, token=None):
		return requests.post(
			f"{self.server.url}/{self.server.version}/{path}", json=body,
			headers={"Authorization": f"Bearer {token or self.server.token}"}, timeout=5,
		)

	def _msg(self, **extra):
		return self._post(f"{self.server.phone_id}/messages", {"messaging_product": "whatsapp", "to": SENDER, **extra})

	def test_message_schema(self):
		self.assertEqual(self._msg(type="text", text={"body": "ok"}).status_code, 200)
		bad = [
			self._post(f"{self.server.phone_id}/messages", {"to": SENDER, "type": "text", "text": {"body": "x"}}),  # no messaging_product
			self._msg(type="text", text={"body": ""}),
			self._msg(type="text"),
			self._msg(type="image", image={"link": "https://a.example/x.png", "id": "1"}),
			self._msg(type="image", image={}),
			self._msg(type="audio", audio={"link": "https://a.example/x.mp3", "caption": "no"}),
			self._msg(type="image", image={"link": "ftp://a.example/x.png"}),
			self._msg(type="document", document={"link": "https://a.example/x.pdf", "caption": "c" * 1025}),
			self._msg(type="text", text={"body": "x"}, extra="field"),
			self._post(f"{self.server.phone_id}/messages", {"messaging_product": "whatsapp", "to": "not-a-number", "type": "text", "text": {"body": "x"}}),
			self._post(f"{self.server.phone_id}/messages", {"messaging_product": "whatsapp", "to": SENDER, "type": "text", "text": {"body": "x"}}, token="wrong"),
		]
		for resp in bad:
			self.assertIn(resp.status_code, (400, 401), resp.text)
			self.assertIn("error", resp.json())
		self.assertEqual(len(self.server.violations), len(bad))

	def _template(self, **override):
		body = {
			"name": "chk_tpl", "language": "en_US", "category": "UTILITY",
			"components": [{"type": "BODY", "text": "Hi {{1}}", "example": {"body_text": [["Ann"]]}}],
		}
		body.update(override)
		return self._post(f"{self.server.waba_id}/message_templates", body)

	def test_template_schema(self):
		self.assertEqual(self._template().status_code, 200)
		bad = [
			self._template(name="Bad Name"),
			self._template(name="dup_free", language="english"),
			self._template(category="SALES"),
			self._template(components=[{"type": "BODY", "text": "Hi {{1}}"}]),  # variable without example
			self._template(components=[{"type": "BODY", "text": "x" * 1025}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}, {"type": "FOOTER", "text": "f" * 61}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}, {"type": "HEADER", "format": "TEXT", "text": "{{1}} {{2}}"}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}, {"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["not-issued"]}}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}, {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "t" * 26}]}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}, {"type": "BUTTONS", "buttons": [{"type": "URL", "text": "u", "url": "https://a.example/{{1}}/x", "example": ["https://a.example/1/x"]}]}]),
			self._template(components=[{"type": "BODY", "text": "Hi"}]),  # valid, but chk_tpl/en_US already exists
		]
		for resp in bad:
			self.assertEqual(resp.status_code, 400, resp.text)
		self.assertEqual(len(self.server.violations), len(bad))

	def test_template_send_checks_status_and_parameter_counts(self):
		self.assertEqual(self._template().status_code, 200)
		send = lambda comps: self._msg(type="template", template={"name": "chk_tpl", "language": {"code": "en_US"}, "components": comps})  # noqa: E731
		pending = send([{"type": "body", "parameters": [{"type": "text", "text": "Ann"}]}])
		self.assertEqual(pending.json()["error"]["code"], 132015)
		self.server.approve("chk_tpl")
		self.assertEqual(send([{"type": "body", "parameters": []}]).json()["error"]["code"], 132000)
		self.assertEqual(send([{"type": "body", "parameters": [{"type": "text", "text": "a\nb"}]}]).json()["error"]["code"], 132018)
		self.assertEqual(send([{"type": "body", "parameters": [{"type": "text", "text": "Ann"}]}]).status_code, 200)
		missing = self._msg(type="template", template={"name": "nope", "language": {"code": "en_US"}})
		self.assertEqual(missing.json()["error"]["code"], 132001)
		self.assertEqual(len(self.server.violations), 4)
