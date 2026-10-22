"""WP-6: the single outbound policy choke point (opt-out, template state, marketing, BSUID, fallback)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai import gateway_service as gsvc
from huf.ai.whatsapp import account_events as events
from huf.ai.whatsapp import outbound_policy as policy
from huf.ai.gateway_adapters import GatewayReply
from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters.whatsapp import (
	WhatsAppFallbackUnavailable,
	WhatsAppGatewayAdapter,
)
from huf.ai.gateway_webhook import get_gateway_adapter as real_get_gateway_adapter  # fixture patches the module attr
from huf.ai.tests.test_gateway_pairing_hardening import _GatewayFixture

PHONE = "15551230001"
CREDS = {
	"phone_number_id": "phone-123",
	"access_token": "access-token",
	"webhook_verify_token": "verify-value",
	"app_secret": "s3cret",
}
CLOSED = {"open": False, "last_inbound_at": None, "expires_at": None}


class _Fixture(_GatewayFixture):
	def tearDown(self):
		for name in self.gateways:
			frappe.db.delete("Gateway Consent", {"gateway": name})
		super().tearDown()

	def stopped_gateway(self, **kw):
		gateway = self.make_gateway("P", policy="Allow list", **kw)
		self.make_entry(gateway, PHONE, state="Approved")
		self.ingest(gateway, PHONE, "STOP")
		self.assertTrue(gsvc.is_opted_out(gateway, PHONE))
		return gateway

	def adapter_for(self, gateway, **ctx):
		self.posts = []

		def post(url, *, headers, json, timeout):
			self.posts.append(json)
			resp = MagicMock()
			resp.json.return_value = {"messages": [{"id": "wamid.out"}]}
			return resp

		context = {"gateway_name": gateway, **ctx}
		return WhatsAppGatewayAdapter(CREDS, http_post=post, gateway_context=context)


class TestRecipientPolicy(_Fixture, IntegrationTestCase):
	def test_opted_out_recipient_refused(self):
		gateway = self.stopped_gateway()
		with self.assertRaises(policy.OutboundRefused) as ctx:
			policy.check_recipient(gateway, PHONE)
		self.assertEqual(ctx.exception.code, "opted_out")

	def test_normal_recipient_allowed(self):
		gateway = self.make_gateway("P", policy="Allow list")
		policy.check_recipient(gateway, PHONE)

	def test_bsuid_recipient_refused_explicitly(self):
		gateway = self.make_gateway("P", policy="Allow list")
		with self.assertRaises(policy.OutboundRefused) as ctx:
			policy.check_recipient(gateway, "IN.4608123456789")
		self.assertEqual(ctx.exception.code, "bsuid_recipient")

	def test_consent_confirmation_scope_not_blocked(self):
		gateway = self.stopped_gateway()
		with gsvc._consent_send_scope(self.gw(gateway), PHONE):
			policy.check_recipient(gateway, PHONE)


class TestTemplatePolicy(_Fixture, IntegrationTestCase):
	def test_non_approved_template_refused(self):
		gateway = self.make_gateway("P", policy="Allow list")
		for status in ("PAUSED", "paused", "REJECTED", "PENDING"):
			with self.assertRaises(policy.OutboundRefused) as ctx:
				policy.check_template(gateway, PHONE, {"status": status, "category": "UTILITY"})
			self.assertEqual(ctx.exception.code, "template_not_approved")

	def test_approved_utility_allowed_and_unknown_row_allowed(self):
		gateway = self.make_gateway("P", policy="Allow list")
		policy.check_template(gateway, PHONE, {"status": "APPROVED", "category": "UTILITY"})
		policy.check_template(gateway, PHONE, None)

	def test_marketing_refused_after_user_preference_stop(self):
		gateway = self.make_gateway("P", policy="Allow list")
		events.record_user_preferences(
			gateway, [{"wa_id": PHONE, "category": "marketing_messages", "value": "stop"}]
		)
		row = {"status": "APPROVED", "category": "MARKETING"}
		with self.assertRaises(policy.OutboundRefused) as ctx:
			policy.check_template(gateway, PHONE, row)
		self.assertEqual(ctx.exception.code, "marketing_opted_out")
		# utility is still fine
		policy.check_template(gateway, PHONE, {"status": "APPROVED", "category": "UTILITY"})
		events.record_user_preferences(
			gateway, [{"wa_id": PHONE, "category": "marketing_messages", "value": "resume"}]
		)
		policy.check_template(gateway, PHONE, row)


class TestBridgeSendTemplate(_Fixture, IntegrationTestCase):
	def _send(self, gateway, row):
		with patch.object(bridge, "_account_or_error", return_value={"name": "acct"}), patch.object(
			bridge, "_template_docname", return_value="doc"
		), patch.object(bridge, "_template_row", return_value={**row, "whatsapp_account": "acct"}), patch.object(
			bridge, "_graph_post_message"
		) as graph, patch.object(bridge.frappe, "get_doc") as get_doc:
			try:
				bridge.send_template("acct", PHONE, "tpl", [], trusted=True, gateway_name=gateway)
			except bridge.BridgeError as exc:
				return exc, graph, get_doc
			return None, graph, get_doc

	def test_stopped_contact_refused_before_any_write(self):
		gateway = self.stopped_gateway()
		err, graph, get_doc = self._send(gateway, {"status": "APPROVED", "template": "hi", "buttons": []})
		self.assertEqual(err.payload["error"], "opted_out")
		graph.assert_not_called()
		get_doc.assert_not_called()

	def test_paused_template_refused(self):
		gateway = self.make_gateway("P", policy="Allow list")
		err, graph, get_doc = self._send(gateway, {"status": "PAUSED", "template": "hi", "buttons": []})
		self.assertEqual(err.payload["error"], "template_not_approved")
		get_doc.assert_not_called()

	def test_account_resolves_gateway_when_not_passed(self):
		gateway = self.stopped_gateway()
		frappe.db.set_value("Gateway", gateway, "whatsapp_account", "acct-wp6", update_modified=False)
		with patch.object(bridge, "_account_or_error", return_value={"name": "acct-wp6"}), patch.object(
			bridge, "_template_docname", return_value="doc"
		), patch.object(bridge, "_template_row", return_value={"status": "APPROVED", "template": "hi", "buttons": [], "whatsapp_account": "acct-wp6"}):
			with self.assertRaises(bridge.BridgeError) as ctx:
				bridge.send_template("acct-wp6", PHONE, "tpl", [], trusted=True)
		self.assertEqual(ctx.exception.payload["error"], "opted_out")


class TestAdapterPaths(_Fixture, IntegrationTestCase):
	def test_fallback_template_refused_for_stopped_contact(self):
		gateway = self.stopped_gateway()
		adapter = self.adapter_for(gateway, fallback_template="reopen")
		with patch("huf.ai.gateway_adapters.whatsapp.bridge") as b:
			b.window_state.return_value = CLOSED
			b.is_available.return_value = False
			with self.assertRaises(WhatsAppFallbackUnavailable) as ctx:
				adapter.send_reply(GatewayReply(PHONE, "hi"))
		self.assertEqual(ctx.exception.code, "recipient_opted_out")
		self.assertEqual(self.posts, [])

	def test_every_adapter_send_refuses_stopped_contact(self):
		gateway = self.stopped_gateway()
		adapter = self.adapter_for(gateway)
		calls = [
			lambda: adapter.send_template(PHONE, "tpl", "en_US", []),
			lambda: adapter.send_media(PHONE, "image", link="https://x/y.png"),
			lambda: adapter.send_location(PHONE, 1.0, 2.0),
			lambda: adapter.send_reaction(PHONE, "wamid.1", "x"),
			lambda: adapter.send_text_parts(PHONE, ["hi"]),
		]
		for call in calls:
			with self.assertRaises(policy.OutboundRefused):
				call()
		self.assertEqual(self.posts, [])

	def test_bsuid_recipient_refused_by_adapter(self):
		gateway = self.make_gateway("P", policy="Allow list")
		adapter = self.adapter_for(gateway)
		with self.assertRaises(policy.OutboundRefused) as ctx:
			adapter.send_template("IN.4608123456789", "tpl", "en_US", [])
		self.assertEqual(ctx.exception.code, "bsuid_recipient")
		self.assertEqual(self.posts, [])

	def test_normal_contact_still_sends(self):
		gateway = self.make_gateway("P", policy="Allow list")
		adapter = self.adapter_for(gateway)
		adapter.send_template(PHONE, "tpl", "en_US", [])
		self.assertEqual(len(self.posts), 1)


class TestToolTemplate(_Fixture, IntegrationTestCase):
	def test_tool_send_template_refused_when_stopped(self):
		from huf.ai.tools import whatsapp as tool

		gateway = self.stopped_gateway()
		with patch.object(tool, "_resolve_bridge_account", return_value=None), patch.object(
			bridge, "send_template"
		) as send:
			out = tool._send_template({"to": PHONE, "template_name": "tpl", "gateway_name": gateway})
		self.assertIn("opted_out", out)
		send.assert_not_called()


class TestStrangerStopAfterTemplate(_Fixture, IntegrationTestCase):
	def _event(self, gateway):
		return frappe.get_doc(
			{"doctype": "Gateway Event", "gateway": gateway, "idempotency_key": "k" + self.suffix,
			 "provider_event_id": "p", "status": "Received", "received_at": now_datetime()}
		).insert(ignore_permissions=True)

	def test_stop_from_contact_who_got_a_template_is_recorded(self):
		gateway = self.make_gateway("P")  # Pairing, no access entry
		policy.record_template_outreach(gateway, PHONE)
		ctx = {"sender_id": PHONE, "conversation_id": PHONE, "message_text": "STOP"}
		result = gsvc.record_consent_event(self._event(gateway), self.gw(gateway), ctx)
		self.assertEqual(result["status"], "Rejected")
		self.assertTrue(gsvc.is_opted_out(gateway, PHONE))

	def test_stop_from_total_stranger_still_ignored(self):
		gateway = self.make_gateway("P")
		ctx = {"sender_id": PHONE, "conversation_id": PHONE, "message_text": "STOP"}
		gsvc.record_consent_event(self._event(gateway), self.gw(gateway), ctx)
		self.assertFalse(gsvc.is_opted_out(gateway, PHONE))
		self.assertEqual(frappe.db.count("Gateway Access Entry", {"gateway": gateway}), 0)

	def test_successful_template_send_records_outreach(self):
		gateway = self.make_gateway("P", policy="Allow list")
		adapter = self.adapter_for(gateway)
		adapter.send_template(PHONE, "tpl", "en_US", [])
		self.assertTrue(policy.has_received_template(gateway, PHONE))


class TestFallbackContext(_Fixture, IntegrationTestCase):
	def test_adapter_context_carries_params_and_contact_name(self):
		from huf.ai import gateway_webhook as webhook

		gateway = self.make_gateway("P", policy="Allow list")
		frappe.db.set_value("Gateway", gateway, "fallback_template", "reopen")
		frappe.db.set_value("Gateway", gateway, "fallback_template_params", '["{{contact_name}}", "Acme"]')
		doc = self.gw(gateway)
		captured = {}

		class Fake:
			def __init__(self, creds, gateway_context=None):
				captured.update(gateway_context or {})

		with patch.object(webhook, "_adapter_class_for_provider", return_value=Fake), patch.object(
			webhook, "_gateway_credentials", return_value={}
		):
			real_get_gateway_adapter(doc, contact_name="Ann")
		self.assertEqual(captured["contact_name"], "Ann")
		self.assertEqual(captured["fallback_template_params"], ["Ann", "Acme"])


class TestFallbackValidator(_Fixture, IntegrationTestCase):
	def _validate(self, row, params=""):
		self.n = getattr(self, "n", 0) + 1
		gateway = self.make_gateway(f"V{self.n}", policy="Allow list")
		doc = self.gw(gateway)
		doc.whatsapp_account = "acct"
		doc.fallback_template = "reopen"
		doc.fallback_template_params = params
		with patch.object(bridge, "is_available", return_value=True), patch.object(
			bridge, "_template_docname", return_value="doc"
		), patch.object(bridge, "_template_row", return_value={**row, "whatsapp_account": "acct", "buttons": []}):
			doc._validate_fallback_template()

	def test_body_variables_allowed(self):
		self._validate({"template": "Hi {{1}}, we miss you", "header": "", "header_type": ""})

	def test_media_header_still_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate({"template": "Hi", "header": "", "header_type": "IMAGE"})

	def test_params_count_must_match_variables(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate({"template": "Hi {{1}} {{2}}", "header": "", "header_type": ""}, '["only one"]')
		self._validate({"template": "Hi {{1}} {{2}}", "header": "", "header_type": ""}, '["a", "b"]')
