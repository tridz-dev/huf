# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp integration tests against a real local fake of the Meta Graph API.

Nothing in the code under test is patched at the HTTP layer: the WhatsApp Account
``url`` and the Integration Settings ``graph_api_url`` point at
:class:`~huf.testing.fake_graph_server.FakeGraphServer`, so genuine ``requests``
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

from huf.ai import gateway_service, gateway_webhook
from huf.ai.whatsapp import management as mgmt
from huf.ai.gateway_adapters import GatewayInboundRequest, whatsapp_bridge as bridge
from huf.ai.gateway_adapters.types import GatewayAttachment, GatewayReply
from huf.ai.gateway_adapters.whatsapp import WhatsAppWindowClosed
from huf.testing import fake_graph_server as fake
from huf.ai.tools import whatsapp as wa_tool

SENDER = "15551234567"
EXEC_USER = "wa-fakegraph-exec@example.com"
PNG = (
	b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
	b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)

WEBP_STATIC = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
WEBP_ANIMATED = b"RIFF\x00\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00\x02" + b"\x00" * 64
OGG = b"OggS" + b"\x00" * 64



def _tool(action, **kwargs):
	"""Call the agent tool the way a run does: the gateway is bound server-side, never taken from the args."""
	# The chat contact is the recipient under test, so recipient scope passes and the 24h window rules decide.
	with wa_tool.trusted_gateway(kwargs.get("gateway_name") or "", contact=str(kwargs.get("to") or "")):
		return wa_tool.handle_action(action, **kwargs)


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
			"body": "Hi {{1}}, order ships {{2}} soon",
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

	def test_reply_with_sticker_sends_no_caption_then_text(self):
		self._inbound(self.direct_gateway)
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		adapter.send_reply(
			GatewayReply(
				conversation_id=SENDER, text="enjoy",
				attachments=(GatewayAttachment(url="https://cdn.example/a.webp", kind="sticker", mime_type="image/webp"),),
			)
		)
		sent = self.server.sent
		self.assertEqual(sent[-2]["type"], "sticker")
		self.assertEqual(sent[-2]["sticker"], {"link": "https://cdn.example/a.webp"})
		self.assertEqual(sent[-1]["type"], "text")

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
		refused = json.loads(_tool("send_media", **args))
		self.assertEqual(refused["error"], "proactive_send_not_permitted")
		self.assertEqual(self.server.requests, [])
		self._inbound(self.direct_gateway)
		with patch.object(wa_tool, "_get_whatsapp_credentials", return_value=(self.server.phone_id, self.server.token)):
			ok = json.loads(_tool("send_media", **args))
			self.assertTrue(ok["success"], ok)
			bad = json.loads(_tool("send_media", **{**args, "kind": "gif"}))
		self.assertEqual(bad["error"], "validation_failed")
		self.assertEqual(self.server.sent[-1]["image"]["link"], "https://cdn.example/a.png")

	# ---------------------------------------------------- non-text types (T5)
	def _each_typed_send(self, adapter):
		"""One send of every non-text type through the adapter; returns the sent bodies in order."""
		before = len(self.server.sent)
		adapter.send_media(SENDER, "audio", media_id="MEDIA9", voice=True)
		adapter.send_sticker(SENDER, link="https://cdn.example/s.webp")
		adapter.send_location(SENDER, 12.97, 77.59, name="Office", address="MG Road")
		adapter.send_contacts(SENDER, [{"name": {"formatted_name": "Ann Lee"}, "phones": [{"phone": "+15551230000", "wa_id": "15551230000"}]}])
		adapter.send_reaction(SENDER, "wamid.IN1", "\U0001F44D")
		adapter.send_reaction(SENDER, "wamid.IN1", "")
		adapter.send_interactive(SENDER, "buttons", {"body": "Pick", "buttons": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}], "header": "Hi", "footer": "Foot"})
		adapter.send_interactive(
			SENDER, "list",
			{"body": "Menu", "button_text": "Open", "sections": [{"title": "S1", "rows": [{"id": "1", "title": "One", "description": "first"}]}, {"title": "S2", "rows": [{"id": "2", "title": "Two"}]}]},
		)
		adapter.send_interactive(SENDER, "cta_url", {"body": "See", "display_text": "Open", "url": "https://shop.example/x", "header": {"type": "image", "link": "https://cdn.example/h.png"}})
		adapter.send_interactive(SENDER, "location_request", {"body": "Where are you?"})
		return self.server.sent[before:]

	def test_every_non_text_type_is_accepted_by_the_strict_fake(self):
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		self._inbound(self.direct_gateway)
		sent = self._each_typed_send(adapter)
		self.assertEqual(
			[(m["type"], (m.get("interactive") or {}).get("type")) for m in sent],
			[("audio", None), ("sticker", None), ("location", None), ("contacts", None), ("reaction", None), ("reaction", None),
				("interactive", "button"), ("interactive", "list"), ("interactive", "cta_url"), ("interactive", "location_request_message")],
		)
		self.assertEqual(sent[0]["audio"], {"id": "MEDIA9", "voice": True})
		self.assertEqual(sent[2]["location"]["name"], "Office")
		self.assertEqual(sent[5]["reaction"], {"message_id": "wamid.IN1", "emoji": ""})
		self.assertEqual(sent[6]["interactive"]["action"]["buttons"][0], {"type": "reply", "reply": {"id": "a", "title": "A"}})

	def test_non_text_types_need_an_open_window_and_validate_before_sending(self):
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		calls = [
			lambda: adapter.send_sticker(SENDER, media_id="1"),
			lambda: adapter.send_location(SENDER, 1, 2),
			lambda: adapter.send_contacts(SENDER, [{"name": "A"}]),
			lambda: adapter.send_reaction(SENDER, "wamid.X", "\U0001F44D"),
			lambda: adapter.send_interactive(SENDER, "buttons", {"body": "b", "buttons": ["A"]}),
		]
		for call in calls:
			with self.assertRaises(WhatsAppWindowClosed):
				call()
		self.assertEqual(self.server.requests, [])
		self._inbound(self.direct_gateway)
		before = len(self.server.requests)
		invalid = [
			lambda: adapter.send_sticker(SENDER),
			lambda: adapter.send_location(SENDER, 91, 2),
			lambda: adapter.send_contacts(SENDER, []),
			lambda: adapter.send_reaction(SENDER, "wamid.X", "not an emoji"),
			lambda: adapter.send_interactive(SENDER, "buttons", {"body": "b", "buttons": ["1", "2", "3", "4"]}),
			lambda: adapter.send_interactive(SENDER, "flow", {"body": "b", "flow_cta": "Go"}),
		]
		for call in invalid:
			with self.assertRaises(bridge.BridgeError) as cm:
				call()
			self.assertEqual(cm.exception.payload["error"], "validation_failed")
		self.assertEqual(len(self.server.requests), before)

	def test_media_upload_then_send_by_id(self):
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		self._inbound(self.direct_gateway)
		image_id = adapter.upload_media(PNG, "image/png", "p.png")
		sticker_id = adapter.upload_media(WEBP_STATIC, "image/webp", "s.webp")
		voice_id = adapter.upload_media(OGG, "audio/ogg; codecs=opus", "v.ogg", voice=True)
		uploads = self.server.requests_to("POST", "/media")
		self.assertEqual(len(uploads), 3)
		self.assertEqual([self.server.uploaded_media[i]["kind"] for i in (image_id, sticker_id, voice_id)], ["image", "sticker", "audio"])
		adapter.send_media(SENDER, "image", media_id=image_id, caption="by id")
		adapter.send_sticker(SENDER, media_id=sticker_id)
		adapter.send_media(SENDER, "audio", media_id=voice_id, voice=True)
		self.assertEqual([m["type"] for m in self.server.sent[-3:]], ["image", "sticker", "audio"])

	def test_upload_caps_are_enforced_before_meta_is_called(self):
		adapter = gateway_webhook.get_gateway_adapter(self.direct_gateway)
		for content, mime, kind, code in (
			(WEBP_STATIC + b"\x00" * (100 * 1024), "image/webp", None, "too_large"),
			(b"x" * (5 * 1024 * 1024 + 1), "image/png", None, "too_large"),
			(b"GIF89a", "image/gif", None, "unsupported_mime"),
		):
			with self.assertRaises(bridge.BridgeError) as cm:
				adapter.upload_media(content, mime, "f", kind=kind)
			self.assertEqual(cm.exception.payload["errors"][0]["code"], code)
		with self.assertRaises(bridge.BridgeError) as cm:
			adapter.upload_media(OGG, "audio/mpeg", "v.mp3", voice=True)
		self.assertEqual(cm.exception.payload["errors"][0]["code"], "voice_needs_ogg_opus")
		self.assertEqual(self.server.requests_to("POST", "/media"), [])
		# the largest animated sticker is accepted, the static cap does not apply to it
		big_animated = WEBP_ANIMATED + b"\x00" * (500 * 1024 - len(WEBP_ANIMATED))
		self.assertTrue(adapter.upload_media(big_animated, "image/webp", "a.webp"))

	def test_typed_agent_tool_actions_direct(self):
		args = {"to": SENDER, "gateway_name": self.direct_gateway.name}
		closed = json.loads(_tool("send_location", latitude=1, longitude=2, **args))
		self.assertEqual(closed["error"], "proactive_send_not_permitted")
		self.assertEqual(self.server.requests, [])
		self._inbound(self.direct_gateway)
		with patch.object(wa_tool, "_get_whatsapp_credentials", return_value=(self.server.phone_id, self.server.token)):
			for action, extra, mtype in (
				("send_location", {"latitude": 1, "longitude": 2}, "location"),
				("send_contact", {"contact_name": "Ann", "contact_phone": "+15551230000"}, "contacts"),
				("send_reaction", {"message_id": "wamid.IN1", "emoji": "\U0001F525"}, "reaction"),
				("send_buttons", {"body": "b", "buttons": [{"id": "a", "title": "A"}]}, "interactive"),
				("send_list", {"body": "b", "button_text": "Go", "sections": [{"id": "1", "title": "One"}]}, "interactive"),
				("send_cta_url", {"body": "b", "display_text": "Go", "url": "https://shop.example"}, "interactive"),
				("send_sticker", {"media_id": "42"}, "sticker"),
				("send_image", {"link": "https://cdn.example/a.png"}, "image"),
			):
				res = json.loads(_tool(action, **extra, **args))
				self.assertTrue(res["success"], (action, res))
				self.assertEqual(self.server.sent[-1]["type"], mtype)


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
		# the outbound policy refuses a template that is not APPROVED locally, so nothing reaches Meta
		self.assertEqual(early["error"], "template_not_approved")
		self.assertIn("not approved", early["message"])
		self.assertEqual(self.server.sent, [])

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
			body="Sale for {{1}} today", sample_values="Ann", buttons=[
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
		synced = mgmt.sync_templates(account=self.account.name)  # the local status gates sends: sync the approval first
		self.assertTrue(synced["success"], synced)
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
			body="Hello {{1}}, welcome", sample_values="Ann",
		)
		self.assertTrue(created["success"], created)
		self.server.approve("fg_plain")
		mgmt.sync_templates(account=self.account.name)
		result = mgmt.send_template_message(to=SENDER, template_name="fg_plain", body_params=json.dumps(["Zed"]), gateway_name=self.bridge_gateway.name)
		self.assertTrue(result["success"], result)
		self.assertEqual(self.server.sent[-1]["template"]["components"], [{"type": "body", "parameters": [{"type": "text", "text": "Zed"}]}])

	def test_invalid_templates_return_structured_errors_without_calling_meta(self):
		cases = {
			"too_many_buttons": {"buttons": [{"type": "QUICK_REPLY", "text": f"b{i}"} for i in range(11)]},
			"too_many_url_buttons": {"buttons": [
				{"type": "URL", "text": "a", "url": "https://a.example"}, {"type": "URL", "text": "b", "url": "https://b.example"},
				{"type": "URL", "text": "c", "url": "https://c.example"}]},
			"too_long": {"footer": "x" * 61},
			"unsupported_header_type": {"header_type": "AUDIO", "header": None},
			"sample_count": {"sample_values": "only-one"},
			"bad_placeholder": {"body": "Hi {{x y}} there"},
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
		self.assertEqual(json.loads(_tool("send_media", **args))["error"], "proactive_send_not_permitted")
		self._inbound(self.bridge_gateway)
		ok = json.loads(_tool("send_media", **args))
		self.assertTrue(ok["success"], ok)
		self.assertEqual(self.server.sent[-1]["type"], "image")
		refused = json.loads(_tool("create_template", gateway_name=self.bridge_gateway.name, template_name="t_x", category="UTILITY", language_code="en_US", body="hi"))
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

	# ---------------------------------------------------- non-text types (T5)
	def _opt_out(self, gateway):
		frappe.db.set_value("Gateway Access Entry", {"gateway": gateway.name, "external_id": SENDER}, "state", "Opted out")

	def _typed_calls(self):
		gw = self.bridge_gateway.name
		contact = [{"name": {"formatted_name": "Ann Lee"}, "emails": [{"email": "ann@example.com", "type": "WORK"}]}]
		return {
			"send_location_message": (dict(latitude=12.97, longitude=77.59, name="Office"), "location", "location"),
			"send_contacts_message": (dict(contacts=json.dumps(contact)), "contacts", "contact"),
			"send_reaction_message": (dict(message_id="wamid.IN1", emoji="\U0001F44D"), "reaction", "reaction"),
			"send_sticker_message": (dict(link="https://cdn.example/s.webp"), "sticker", "image"),
			"send_interactive_message": (
				dict(kind="buttons", body="Pick", buttons=json.dumps([{"id": "a", "title": "A"}]), footer="Foot"), "interactive", "interactive",
			),
			"send_media_message": (dict(kind="audio", media_id="MEDIA7", voice=True), "audio", "audio"),
		}, gw

	def test_management_type_endpoints_send_once_and_mirror_one_row(self):
		self._inbound(self.bridge_gateway)
		calls, gw = self._typed_calls()
		for endpoint, (kwargs, mtype, content_type) in calls.items():
			posts_before = len(self.server.requests_to("POST", "/messages"))
			result = getattr(mgmt, endpoint)(gateway_name=gw, to=SENDER, **kwargs)
			self.assertTrue(result["success"], (endpoint, result))
			# exactly one Graph send, and frappe_whatsapp did not send the mirror row again
			self.assertEqual(len(self.server.requests_to("POST", "/messages")) - posts_before, 1, endpoint)
			self.assertEqual(self.server.sent[-1]["type"], mtype)
			self.assertEqual(self.server.sent[-1]["_wamid"], result["message_id"])
			rows = frappe.get_all("WhatsApp Message", filters={"message_id": result["message_id"]}, fields=["content_type", "type", "to", "status"])
			self.assertEqual(len(rows), 1, endpoint)
			self.assertEqual((rows[0].content_type, rows[0].type), (content_type, "Outgoing"))

	def test_management_type_endpoints_window_and_opt_out(self):
		calls, gw = self._typed_calls()
		for endpoint, (kwargs, _m, _c) in calls.items():
			self.assertEqual(getattr(mgmt, endpoint)(gateway_name=gw, to=SENDER, **kwargs)["error"], "window_closed", endpoint)
		self.assertEqual(self.server.requests, [])
		self._inbound(self.bridge_gateway)
		self._opt_out(self.bridge_gateway)
		for endpoint, (kwargs, _m, _c) in calls.items():
			self.assertEqual(getattr(mgmt, endpoint)(gateway_name=gw, to=SENDER, **kwargs)["error"], "opted_out", endpoint)
		self.assertEqual(self.server.requests_to("POST", "/messages"), [])

	def test_management_type_endpoints_validate_without_calling_meta(self):
		self._inbound(self.bridge_gateway)
		gw = self.bridge_gateway.name
		bad = [
			mgmt.send_location_message(gateway_name=gw, to=SENDER, latitude=0, longitude=181),
			mgmt.send_contacts_message(gateway_name=gw, to=SENDER, contacts=json.dumps([{"phones": []}])),
			mgmt.send_reaction_message(gateway_name=gw, to=SENDER, message_id="", emoji="x"),
			mgmt.send_interactive_message(gateway_name=gw, to=SENDER, kind="list", body="b", button_text="o" * 21, sections=json.dumps([{"id": "1", "title": "t"}])),
			mgmt.send_interactive_message(gateway_name=gw, to=SENDER, kind="cta_url", body="b", display_text="go", url="http://insecure.example"),
			mgmt.send_interactive_message(gateway_name=gw, to=SENDER, kind="flow", body="b", flow_cta="Start"),
			mgmt.send_sticker_message(gateway_name=gw, to=SENDER),
		]
		for res in bad:
			self.assertEqual(res["error"], "validation_failed", res)
		self.assertIn("flow_id_required", [e["code"] for e in bad[5]["errors"]])
		self.assertEqual(self.server.requests_to("POST", "/messages"), [])

	def test_private_file_is_uploaded_then_sent_by_media_id(self):
		self._inbound(self.bridge_gateway)
		gw = self.bridge_gateway.name
		suffix = frappe.generate_hash(length=6)
		png = frappe.get_doc({"doctype": "File", "file_name": f"fg-{suffix}.png", "is_private": 1, "content": PNG}).insert(ignore_permissions=True)
		res = mgmt.send_media_message(gateway_name=gw, to=SENDER, kind="image", file_url=png.file_url, caption="uploaded")
		self.assertTrue(res["success"], res)
		uploads = self.server.requests_to("POST", "/media")
		self.assertEqual(len(uploads), 1)
		media_id = next(iter(self.server.uploaded_media))
		self.assertEqual(self.server.sent[-1]["image"], {"id": media_id, "caption": "uploaded"})
		only = mgmt.upload_media_file(gateway_name=gw, file_url=png.file_url)
		self.assertEqual((only["success"], only["kind"], only["mime_type"]), (True, "image", "image/png"))
		self.assertIn(only["media_id"], self.server.uploaded_media)
		# a sticker file over the static cap never reaches Meta
		big = frappe.get_doc({"doctype": "File", "file_name": f"big-{suffix}.webp", "is_private": 1, "content": WEBP_STATIC + b"\x00" * (100 * 1024)}).insert(ignore_permissions=True)
		uploads_before = len(self.server.requests_to("POST", "/media"))
		refused = mgmt.send_sticker_message(gateway_name=gw, to=SENDER, file_url=big.file_url)
		self.assertEqual(refused["error"], "validation_failed")
		self.assertEqual(refused["errors"][0]["code"], "too_large")
		self.assertEqual(len(self.server.requests_to("POST", "/media")), uploads_before)

	def test_meta_rejection_is_structured_and_not_mirrored(self):
		self._inbound(self.bridge_gateway)
		before = frappe.db.count("WhatsApp Message")
		with patch.object(self.server, "token", "revoked-token"):
			res = mgmt.send_location_message(gateway_name=self.bridge_gateway.name, to=SENDER, latitude=1, longitude=2)
		self.assertFalse(res["success"])
		self.assertEqual(res["error"], "send_failed")
		self.assertTrue(res.get("kind"))
		self.assertEqual(frappe.db.count("WhatsApp Message"), before)
		self.server.violations.clear()  # the rejected call is the point of this test

	def test_typed_agent_tool_actions_via_bridge(self):
		gw = self.bridge_gateway.name
		args = {"to": SENDER, "gateway_name": gw, "latitude": 1, "longitude": 2}
		self.assertEqual(json.loads(_tool("send_location", **args))["error"], "proactive_send_not_permitted")
		self._inbound(self.bridge_gateway)
		for action, extra, mtype in (
			("send_location", {"latitude": 1, "longitude": 2}, "location"),
			("send_reaction", {"message_id": "wamid.IN1", "emoji": "\U0001F44D"}, "reaction"),
			("send_buttons", {"body": "b", "buttons": [{"id": "a", "title": "A"}]}, "interactive"),
			("send_sticker", {"media_id": "42"}, "sticker"),
		):
			posts = len(self.server.requests_to("POST", "/messages"))
			res = json.loads(_tool(action, to=SENDER, gateway_name=gw, **extra))
			self.assertTrue(res["success"], (action, res))
			self.assertEqual(len(self.server.requests_to("POST", "/messages")) - posts, 1)
			self.assertTrue(frappe.db.exists("WhatsApp Message", {"message_id": res["data"]["message_id"]}))
		self._opt_out(self.bridge_gateway)
		self.assertEqual(json.loads(_tool("send_location", **args))["error"], "opted_out")


class TestTemplateWizard(FakeGraphCase):
	"""Direct-to-Meta create / edit / send of the wizard's template shapes (bridge mode, fake Graph)."""

	MODE = "bridge"

	def setUp(self):
		super().setUp()
		self._need_bridge()

	def _create(self, **override):
		payload = {
			"template_name": "fg_wiz",
			"category": "UTILITY",
			"language_code": "en_US",
			"body": "Hi {{1}}, your order shipped",
			"sample_values": "Ann",
		}
		payload.update({k: v for k, v in override.items() if v is not None})
		for key in [k for k, v in override.items() if v is None]:
			payload.pop(key, None)
		return mgmt.create_template(account=self.account.name, payload=json.dumps(payload))

	def _meta_post(self, index=-1):
		return self.server.requests_to("POST", "/message_templates")[index]["body"]

	def _extra(self, docname):
		from huf.ai.gateway_adapters import whatsapp_template_guard as guard

		return guard.get_extra(self.account.name, docname)

	def _approve(self, name):
		self.assertEqual(self._deliver_webhook(self.bridge_gateway, self.server.approve(name))["template_updates"], 1)

	def _set_status(self, name, status):
		self.assertEqual(self._deliver_webhook(self.bridge_gateway, self.server.set_template_status(name, status))["template_updates"], 1)

	def _send(self, template, **kw):
		for key in ("body_params", "header_params", "button_params"):
			if key in kw:
				kw[key] = json.dumps(kw[key])
		return mgmt.send_template_message(to=SENDER, template_name=template, gateway_name=self.bridge_gateway.name, **kw)

	def test_positional_create_pushes_directly_and_mirrors_under_the_guard_flag(self):
		seen = {}
		original = bridge._insert_mirror_row

		def spy(doc):
			seen["write_flag"] = frappe.flags.get("huf_template_write")
			seen["mirror_flag"] = doc.flags.get("huf_mirror")
			return original(doc)

		with patch.object(bridge, "_insert_mirror_row", side_effect=spy):
			created = self._create()
		self.assertTrue(created["success"], created)
		self.assertEqual(seen, {"write_flag": True, "mirror_flag": True})
		self.assertFalse(frappe.flags.get("huf_template_write"))  # restored after the block
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)  # frappe_whatsapp never pushes
		body = self._meta_post()
		self.assertEqual(body["parameter_format"], "POSITIONAL")
		self.assertNotIn("message_send_ttl_seconds", body)
		self.assertEqual(body["components"], [{"type": "BODY", "text": "Hi {{1}}, your order shipped", "example": {"body_text": [["Ann"]]}}])
		row = frappe.db.get_value("WhatsApp Templates", created["name"], ["status", "id", "actual_name", "category", "language_code", "template", "whatsapp_account"], as_dict=True)
		self.assertEqual((row.status, row.actual_name, row.category, row.language_code), ("PENDING", "fg_wiz", "UTILITY", "en_US"))
		self.assertEqual((row.id, row.whatsapp_account), (created["id"], self.account.name))
		extra = self._extra(created["name"])
		self.assertEqual((extra["created_via"], extra["parameter_format"], extra["template_id"]), ("Huf", "POSITIONAL", created["id"]))
		self.assertEqual(extra["components_json"], body["components"])

	def test_named_create_edit_prefill_and_send_use_parameter_name(self):
		created = self._create(
			template_name="fg_named", body="Hi {{first_name}}, your order {{order_id}} shipped",
			named_samples={"first_name": "Ann", "order_id": "A100"}, sample_values=None,
		)
		self.assertTrue(created["success"], created)
		body = self._meta_post()
		self.assertEqual(body["parameter_format"], "NAMED")
		self.assertEqual(
			body["components"][0]["example"],
			{"body_text_named_params": [{"param_name": "first_name", "example": "Ann"}, {"param_name": "order_id", "example": "A100"}]},
		)
		extra = self._extra(created["name"])
		self.assertEqual(extra["parameter_format"], "NAMED")
		self.assertEqual(extra["named_samples"], [{"name": "first_name", "example": "Ann"}, {"name": "order_id", "example": "A100"}])
		self._approve("fg_named")

		# send: dict, list-of-pairs and ordered list all produce parameter_name entries
		for params in ({"order_id": "B7", "first_name": "Zed"}, [{"name": "first_name", "value": "Zed"}, {"name": "order_id", "value": "B7"}], ["Zed", "B7"]):
			sent = self._send("fg_named", body_params=params)
			self.assertTrue(sent["success"], sent)
			self.assertEqual(
				self.server.sent[-1]["template"]["components"],
				[{"type": "body", "parameters": [
					{"type": "text", "parameter_name": "first_name", "text": "Zed"},
					{"type": "text", "parameter_name": "order_id", "text": "B7"},
				]}],
			)
		missing = self._send("fg_named", body_params={"first_name": "Zed"})
		self.assertEqual(missing["error"], "param_missing")
		self.assertEqual(missing["errors"][0]["field"], "body_params.order_id")
		unknown = self._send("fg_named", body_params={"first_name": "Zed", "order_id": "1", "extra": "x"})
		self.assertEqual(unknown["error"], "param_unknown")
		self.assertEqual(len(self.server.sent), 3)

		# prefill for the wizard
		detail = mgmt.get_template(name=created["name"])
		self.assertEqual(detail["parameter_format"], "NAMED")
		self.assertEqual(detail["named_samples"], extra["named_samples"])
		self.assertEqual((detail["header_format"], detail["ttl_seconds"]), ("", None))

		bad = mgmt.edit_template(name=created["name"], payload=json.dumps({"parameter_format": "POSITIONAL"}))
		self.assertEqual((bad["error"], bad["field"]), ("immutable_field", "parameter_format"))

		# edit: full components, no parameter_format on the edit call, row + extras updated
		edited = mgmt.edit_template(name=created["name"], payload=json.dumps({
			"body": "Hi {{first_name}}, order {{order_id}} left the warehouse",
			"named_samples": {"first_name": "Ann", "order_id": "A100"},
		}))
		self.assertTrue(edited["success"], edited)
		edit_body = self.server.requests_to("POST", f"/{created['id']}")[-1]["body"]
		self.assertEqual(set(edit_body), {"components"})
		self.assertEqual(edit_body["components"][0]["text"], "Hi {{first_name}}, order {{order_id}} left the warehouse")
		self.assertIn("body_text_named_params", edit_body["components"][0]["example"])
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "status"), "PENDING")
		self.assertEqual(self._extra(created["name"])["components_json"], edit_body["components"])

	def test_video_header_uploads_a_handle_and_edits_reuse_it(self):
		sample = self.server.add_file("samples/clip.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom")
		created = self._create(template_name="fg_video", header_type="VIDEO", sample=sample)
		self.assertTrue(created["success"], created)
		self.assertEqual(len(self.server.requests_to("POST", "/uploads")), 1)
		header = self._meta_post()["components"][0]
		self.assertEqual(header["format"], "VIDEO")
		handle = header["example"]["header_handle"][0]
		self.assertTrue(handle.startswith("4:"))
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "header_type"), "")  # doctype has no VIDEO
		self.assertEqual(self._extra(created["name"])["header_format"], "VIDEO")
		self.assertEqual(mgmt.get_template(name=created["name"])["header_format"], "VIDEO")
		self._approve("fg_video")
		# send needs a video link of the right kind
		self.assertEqual(self._send("fg_video", body_params=["Ann"])["errors"][0]["code"], "required")
		wrong = self._send("fg_video", body_params=["Ann"], header_params=[{"type": "image", "link": sample}])
		self.assertEqual(wrong["errors"][0]["code"], "invalid_type")
		ok = self._send("fg_video", body_params=["Ann"], header_params=[{"type": "video", "link": sample}])
		self.assertTrue(ok["success"], ok)
		self.assertEqual(self.server.sent[-1]["template"]["components"][0], {"type": "header", "parameters": [{"type": "video", "video": {"link": sample}}]})
		# body-only edit re-sends the stored handle without a new upload (REJECTED templates edit freely)
		self._set_status("fg_video", "REJECTED")
		edited = mgmt.edit_template(name=created["name"], payload=json.dumps({"body": "Hi {{1}}, your video order shipped", "sample_values": "Ann"}))
		self.assertTrue(edited["success"], edited)
		self.assertEqual(len(self.server.requests_to("POST", "/uploads")), 1)
		self.assertEqual(self.server.requests_to("POST", f"/{created['id']}")[-1]["body"]["components"][0]["example"]["header_handle"], [handle])
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "header_type"), "")
		# a replacement sample is uploaded again; a header switch without a sample is refused
		self._set_status("fg_video", "REJECTED")
		newer = self.server.add_file("samples/clip2.mp4", "video/mp4", b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom2")
		swapped = mgmt.edit_template(name=created["name"], payload=json.dumps({"sample": newer}))
		self.assertTrue(swapped["success"], swapped)
		self.assertEqual(len(self.server.requests_to("POST", "/uploads")), 2)
		self._set_status("fg_video", "REJECTED")
		no_sample = mgmt.edit_template(name=created["name"], payload=json.dumps({"header_type": "IMAGE"}))
		self.assertEqual(no_sample["error"], "media_header_edit_unsupported")

	def test_location_header_create_and_send(self):
		created = self._create(template_name="fg_loc", header_type="LOCATION")
		self.assertTrue(created["success"], created)
		self.assertEqual(self._meta_post()["components"][0], {"type": "HEADER", "format": "LOCATION"})
		self.assertEqual(frappe.db.get_value("WhatsApp Templates", created["name"], "header_type"), "")
		self.assertEqual(self._extra(created["name"])["header_format"], "LOCATION")
		self._approve("fg_loc")
		self.assertEqual(self._send("fg_loc", body_params=["Ann"])["errors"][0]["code"], "required")
		loc = {"type": "location", "latitude": 12.97, "longitude": 77.59, "name": "HQ", "address": "1 Main St"}
		ok = self._send("fg_loc", body_params=["Ann"], header_params=[loc])
		self.assertTrue(ok["success"], ok)
		self.assertEqual(
			self.server.sent[-1]["template"]["components"][0],
			{"type": "header", "parameters": [{"type": "location", "location": {"latitude": 12.97, "longitude": 77.59, "name": "HQ", "address": "1 Main St"}}]},
		)

	def test_copy_code_button_create_and_send(self):
		created = self._create(
			template_name="fg_copy", category="MARKETING", body="Use your code at checkout today", sample_values=None,
			buttons=[{"type": "COPY_CODE", "example": "SAVE20"}],
		)
		self.assertTrue(created["success"], created)
		self.assertEqual(self._meta_post()["components"][-1], {"type": "BUTTONS", "buttons": [{"type": "COPY_CODE", "example": "SAVE20"}]})
		button = frappe.db.get_value("WhatsApp Button", {"parent": created["name"]}, ["button_type", "button_label", "example_url"], as_dict=True)
		self.assertEqual((button.button_type, button.example_url), ("Copy Code", "SAVE20"))
		self._approve("fg_copy")
		self.assertEqual(self._send("fg_copy")["errors"][0]["code"], "required")
		ok = self._send("fg_copy", button_params=[{"index": 0, "sub_type": "copy_code", "code": "SAVE30"}])
		self.assertTrue(ok["success"], ok)
		self.assertEqual(
			self.server.sent[-1]["template"]["components"],
			[{"type": "button", "sub_type": "copy_code", "index": "0", "parameters": [{"type": "coupon_code", "coupon_code": "SAVE30"}]}],
		)

	def test_utility_ttl_is_sent_stored_and_rejected_for_marketing(self):
		created = self._create(template_name="fg_ttl", ttl_seconds=3600)
		self.assertTrue(created["success"], created)
		self.assertEqual(self._meta_post()["message_send_ttl_seconds"], 3600)
		self.assertEqual(self._extra(created["name"])["ttl_seconds"], 3600)
		self.assertEqual(mgmt.get_template(name=created["name"])["ttl_seconds"], 3600)
		before = len(self.server.requests_to("POST", "/message_templates"))
		marketing = self._create(template_name="fg_ttl_mkt", category="MARKETING", ttl_seconds=3600)
		self.assertIn("ttl_not_allowed", [e["code"] for e in marketing["errors"]])
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), before)
		self._approve("fg_ttl")
		edited = mgmt.edit_template(name=created["name"], payload=json.dumps({"ttl_seconds": 7200}))
		self.assertTrue(edited["success"], edited)
		self.assertEqual(self.server.requests_to("POST", f"/{created['id']}")[-1]["body"]["message_send_ttl_seconds"], 7200)
		self.assertEqual(self._extra(created["name"])["ttl_seconds"], 7200)

	def test_meta_refusal_leaves_no_local_row_and_a_redacted_error(self):
		self.server.add_template("fg_taken", components=[{"type": "BODY", "text": "Already there"}])  # exists on Meta, not locally
		res = self._create(template_name="fg_taken", body="Hello there friend", sample_values=None)
		self.assertEqual(res["error"], "create_failed")
		self.assertIn("already exists", res["message"])
		self.assertNotIn(self.server.token, json.dumps(res))
		self.assertEqual(frappe.db.count("WhatsApp Templates", {"template_name": "fg_taken"}), 0)
		self.assertIsNone(self._extra("fg_taken-en_US"))
		self.assertEqual(len(self.server.violations), 1)  # Meta's own duplicate refusal; expected here
		self.server.violations.clear()

	def test_draft_approval_carries_the_wizard_payload_and_submits_once(self):
		payload = {
			"template_name": "fg_draft", "category": "UTILITY", "language_code": "en_US",
			"parameter_format": "NAMED", "body": "Hi {{first_name}}, your slot is booked",
			"named_samples": {"first_name": "Ann"}, "ttl_seconds": 900,
			"buttons": [{"type": "QUICK_REPLY", "text": "OK"}],
		}
		draft = mgmt.create_template_draft(account=self.account.name, payload=json.dumps(payload))
		self.assertTrue(draft["success"], draft)
		self.assertEqual(self.server.requests_to("POST", "/message_templates"), [])  # nothing sent before approval
		stored = json.loads(frappe.db.get_value("WhatsApp Template Draft", draft["name"], "payload"))
		for key in ("parameter_format", "named_samples", "ttl_seconds", "buttons", "category"):
			self.assertEqual(stored[key], payload[key])
		approved = mgmt.approve_template_draft(name=draft["name"])
		self.assertTrue(approved["success"], approved)
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)
		body = self._meta_post()
		self.assertEqual((body["parameter_format"], body["message_send_ttl_seconds"]), ("NAMED", 900))
		again = mgmt.approve_template_draft(name=draft["name"])
		self.assertEqual(again["error"], "already_processed")
		self.assertEqual(len(self.server.requests_to("POST", "/message_templates")), 1)
		extra = self._extra(approved["submitted_template"])
		self.assertEqual((extra["parameter_format"], extra["ttl_seconds"], extra["created_via"]), ("NAMED", 900, "Huf"))


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

	def test_wizard_template_schema(self):
		named = {"type": "BODY", "text": "Hi {{first_name}}, welcome", "example": {"body_text_named_params": [{"param_name": "first_name", "example": "Ann"}]}}
		ok = [
			self._template(name="n_ok", parameter_format="NAMED", components=[named]),
			self._template(name="loc_ok", components=[{"type": "HEADER", "format": "LOCATION"}, {"type": "BODY", "text": "Hi"}]),
			self._template(name="ttl_ok", message_send_ttl_seconds=3600, components=[{"type": "BODY", "text": "Hi"}]),
			self._template(name="cc_ok", category="MARKETING", components=[{"type": "BODY", "text": "Hi"}, {"type": "BUTTONS", "buttons": [{"type": "COPY_CODE", "example": "SAVE20"}]}]),
		]
		for resp in ok:
			self.assertEqual(resp.status_code, 200, resp.text)
		bad = [
			self._template(name="n_bad1", parameter_format="WEIRD", components=[{"type": "BODY", "text": "Hi"}]),
			self._template(name="n_bad2", components=[named]),  # named variables need parameter_format NAMED
			self._template(name="n_bad3", parameter_format="NAMED", components=[{"type": "BODY", "text": "Hi {{first_name}}, x", "example": {"body_text": [["Ann"]]}}]),
			self._template(name="n_bad4", parameter_format="NAMED", components=[{**named, "example": {"body_text_named_params": [{"param_name": "other", "example": "Ann"}]}}]),
			self._template(name="loc_bad", components=[{"type": "HEADER", "format": "LOCATION", "text": "x"}, {"type": "BODY", "text": "Hi"}]),
			self._template(name="ttl_bad1", message_send_ttl_seconds=10, components=[{"type": "BODY", "text": "Hi"}]),
			self._template(name="ttl_bad2", category="MARKETING", message_send_ttl_seconds=3600, components=[{"type": "BODY", "text": "Hi"}]),
			self._template(name="cc_bad", components=[{"type": "BODY", "text": "Hi"}, {"type": "BUTTONS", "buttons": [{"type": "COPY_CODE", "example": "x" * 21}]}]),
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

	def test_non_text_message_schema(self):
		contact = {"name": {"formatted_name": "Ann"}, "phones": [{"phone": "+1555", "wa_id": "1555"}]}
		button = lambda **kw: {"type": "button", "body": {"text": "b"}, "action": {"buttons": [{"type": "reply", "reply": {"id": "a", "title": "A"}}]}, **kw}  # noqa: E731
		lst = lambda **kw: {"type": "list", "body": {"text": "b"}, "action": {"button": "Open", "sections": [{"title": "S", "rows": [{"id": "1", "title": "One"}]}]}, **kw}  # noqa: E731
		cta = lambda **kw: {"type": "cta_url", "body": {"text": "b"}, "action": {"name": "cta_url", "parameters": {"display_text": "Go", "url": "https://a.example"}}, **kw}  # noqa: E731
		ok = [
			self._msg(type="sticker", sticker={"id": "1"}),
			self._msg(type="audio", audio={"id": "1", "voice": True}),
			self._msg(type="location", location={"latitude": 12.5, "longitude": -77.5, "name": "n", "address": "a"}),
			self._msg(type="contacts", contacts=[contact]),
			self._msg(type="reaction", reaction={"message_id": "wamid.X", "emoji": "\U0001F44D"}),
			self._msg(type="reaction", reaction={"message_id": "wamid.X", "emoji": ""}),
			self._msg(type="interactive", interactive=button(footer={"text": "f"}, header={"type": "text", "text": "h"})),
			self._msg(type="interactive", interactive=lst()),
			self._msg(type="interactive", interactive=cta(header={"type": "image", "image": {"link": "https://a.example/h.png"}})),
			self._msg(type="interactive", interactive={"type": "location_request_message", "body": {"text": "where"}, "action": {"name": "send_location"}}),
			self._msg(type="interactive", interactive={"type": "flow", "body": {"text": "b"}, "action": {"name": "flow", "parameters": {"flow_message_version": "3", "flow_id": "1", "flow_cta": "Go"}}}),
		]
		for resp in ok:
			self.assertEqual(resp.status_code, 200, resp.text)
		many_buttons = [{"type": "reply", "reply": {"id": str(i), "title": f"B{i}"}} for i in range(4)]
		rows = lambda n: [{"title": "S", "rows": [{"id": str(i), "title": f"R{i}"} for i in range(n)]}]  # noqa: E731
		bad = [
			self._msg(type="sticker", sticker={"id": "1", "caption": "no"}),
			self._msg(type="audio", audio={"id": "1", "voice": "yes"}),
			self._msg(type="location", location={"latitude": 91, "longitude": 0}),
			self._msg(type="location", location={"latitude": 1}),
			self._msg(type="contacts", contacts=[]),
			self._msg(type="contacts", contacts=[{"phones": []}]),
			self._msg(type="contacts", contacts=[{**contact, "birthday": "1/1/90"}]),
			self._msg(type="contacts", contacts=[{**contact, "nick": "x"}]),
			self._msg(type="contacts", contacts={"name": {"formatted_name": "x"}}),
			self._msg(type="reaction", reaction={"message_id": "", "emoji": "\U0001F44D"}),
			self._msg(type="reaction", reaction={"message_id": "wamid.X"}),
			self._msg(type="reaction", reaction={"message_id": "wamid.X", "emoji": "\U0001F44D"}, context={"message_id": "wamid.Y"}),
			self._msg(type="interactive", interactive=button(action={"buttons": many_buttons})),
			self._msg(type="interactive", interactive=button(action={"buttons": [{"type": "reply", "reply": {"id": "a", "title": "t" * 21}}]})),
			self._msg(type="interactive", interactive=button(action={"buttons": [{"type": "reply", "reply": {"id": "a" * 257, "title": "t"}}]})),
			self._msg(type="interactive", interactive=button(action={"buttons": [{"type": "reply", "reply": {"id": "a", "title": "t"}}, {"type": "reply", "reply": {"id": "b", "title": "t"}}]})),
			self._msg(type="interactive", interactive=button(body={"text": "b" * 1025})),
			self._msg(type="interactive", interactive=button(footer={"text": "f" * 61})),
			self._msg(type="interactive", interactive=lst(action={"button": "Open", "sections": rows(11)})),
			self._msg(type="interactive", interactive=lst(action={"button": "o" * 21, "sections": rows(1)})),
			self._msg(type="interactive", interactive=lst(header={"type": "image", "image": {"link": "https://a.example/h.png"}})),
			self._msg(type="interactive", interactive=lst(action={"button": "Open", "sections": [{"title": "t" * 25, "rows": rows(1)[0]["rows"]}]})),
			self._msg(type="interactive", interactive=lst(action={"button": "Open", "sections": [{"title": "S", "rows": [{"id": "1", "title": "t" * 25}]}]})),
			self._msg(type="interactive", interactive=lst(action={"button": "Open", "sections": [{"title": "S", "rows": [{"id": "1", "title": "t", "description": "d" * 73}]}]})),
			self._msg(type="interactive", interactive=cta(action={"name": "cta_url", "parameters": {"display_text": "Go", "url": "http://a.example"}})),
			self._msg(type="interactive", interactive=cta(action={"name": "cta_url", "parameters": {"display_text": "g" * 21, "url": "https://a.example"}})),
			self._msg(type="interactive", interactive={"type": "location_request_message", "body": {"text": "w"}, "action": {"name": "send_location"}, "footer": {"text": "f"}}),
			self._msg(type="interactive", interactive={"type": "flow", "body": {"text": "b"}, "action": {"name": "flow", "parameters": {"flow_cta": "Go"}}}),
			self._msg(type="interactive", interactive={"type": "carousel", "body": {"text": "b"}, "action": {}}),
		]
		for resp in bad:
			self.assertEqual(resp.status_code, 400, resp.text)
		self.assertEqual(len(self.server.violations), len(bad))

	def _upload(self, content, mime, field_type=None, token=None, **fields):
		data = {"messaging_product": "whatsapp", "type": field_type if field_type is not None else mime, **fields}
		data = {k: v for k, v in data.items() if v is not None}
		return requests.post(
			f"{self.server.url}/{self.server.version}/{self.server.phone_id}/media", data=data, files={"file": ("f", content, mime)},
			headers={"Authorization": f"Bearer {token or self.server.token}"}, timeout=5,
		)

	def test_media_upload_schema(self):
		kb = 1024
		static = WEBP_STATIC
		ok = [
			self._upload(PNG, "image/png"),
			self._upload(b"x" * (5 * 1024 * 1024), "image/jpeg"),
			self._upload(OGG, "audio/ogg"),
			self._upload(b"%PDF", "application/pdf"),
			self._upload(static + b"\x00" * (100 * kb - len(static)), "image/webp"),
			self._upload(WEBP_ANIMATED + b"\x00" * (500 * kb - len(WEBP_ANIMATED)), "image/webp"),
		]
		for resp in ok:
			self.assertEqual(resp.status_code, 200, resp.text)
			self.assertIn(resp.json()["id"], self.server.uploaded_media)
		bad = [
			self._upload(b"x" * (5 * 1024 * 1024 + 1), "image/png"),
			self._upload(static + b"\x00" * (100 * kb), "image/webp"),
			self._upload(WEBP_ANIMATED + b"\x00" * (500 * kb), "image/webp"),
			self._upload(b"GIF89a", "image/gif"),
			self._upload(PNG, "image/png", field_type="image/jpeg"),
			self._upload(PNG, "image/png", field_type=""),
			self._upload(b"", "image/png"),
			self._upload(PNG, "image/png", messaging_product=None),
			self._upload(PNG, "image/png", token="wrong"),
		]
		for resp in bad:
			self.assertIn(resp.status_code, (400, 401), resp.text)
		self.assertEqual(bad[0].json()["error"]["code"], 131053)
		self.assertEqual(len(self.server.violations), len(bad))

	def test_media_id_must_be_used_for_its_upload_kind(self):
		image_id = self._upload(PNG, "image/png").json()["id"]
		sticker_id = self._upload(WEBP_STATIC, "image/webp").json()["id"]
		mp3_id = self._upload(b"ID3", "audio/mpeg").json()["id"]
		self.assertEqual(self._msg(type="image", image={"id": image_id}).status_code, 200)
		self.assertEqual(self._msg(type="sticker", sticker={"id": sticker_id}).status_code, 200)
		bad = [
			self._msg(type="sticker", sticker={"id": image_id}),
			self._msg(type="image", image={"id": sticker_id}),
			self._msg(type="audio", audio={"id": mp3_id, "voice": True}),
		]
		for resp in bad:
			self.assertEqual(resp.status_code, 400, resp.text)
			self.assertEqual(resp.json()["error"]["code"], 131053)
		self.assertEqual(self._msg(type="audio", audio={"id": mp3_id}).status_code, 200)
		self.assertEqual(len(self.server.violations), len(bad))
