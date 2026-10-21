"""Focused fixtures for the WhatsApp Cloud API adapter, sender and webhook gates."""

from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai import gateway_webhook
from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply
from huf.ai.gateway_adapters.whatsapp import (
	GRAPH_API_VERSION,
	META_GRAPH_URL,
	WhatsAppGatewayAdapter,
	WhatsAppSender,
)


class FakeResponse:
	def __init__(self, body):
		self.body = body

	def raise_for_status(self):
		pass

	def json(self):
		return self.body


CREDS = {
	"phone_number_id": "phone-123",
	"access_token": "access-token",
	"webhook_verify_token": "verify-value",
	"app_secret": "app-secret",
}


def _signed(payload):
	body = json.dumps(payload).encode()
	sig = "sha256=" + hmac.new(b"app-secret", body, hashlib.sha256).hexdigest()
	return GatewayInboundRequest(body, headers={"X-Hub-Signature-256": sig}, method="POST")


def _message_payload():
	return {
		"object": "whatsapp_business_account",
		"entry": [{"changes": [{"value": {"messages": [{
			"from": "1234567890", "id": "wamid.in", "type": "text",
			"text": {"body": "hello"}, "context": {"id": "wamid.prev"},
		}]}}]}],
	}


def _status_payload():
	return {
		"object": "whatsapp_business_account",
		"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.out", "status": "delivered"}]}}]}],
	}


class TestWhatsAppAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []

		def post(url, *, json, headers, timeout):
			self.calls.append({"url": url, "json": json, "headers": headers})
			return FakeResponse({"messages": [{"id": "wamid.123"}]})

		self.adapter = WhatsAppGatewayAdapter(CREDS, http_post=post)

	def test_graph_version_single_constant(self):
		self.assertEqual(GRAPH_API_VERSION, "v25.0")
		self.assertTrue(META_GRAPH_URL.endswith("/v25.0"))

	def test_verify_url_handshake(self):
		req = GatewayInboundRequest(b"", query={"hub.verify_token": "verify-value", "hub.challenge": "abc"}, method="GET")
		self.assertEqual(self.adapter.verify_url(req), "abc")

	def test_verify_url_rejects_empty_and_wrong_token(self):
		for token in ("", None, "wrong"):
			query = {"hub.challenge": "abc"}
			if token is not None:
				query["hub.verify_token"] = token
			with self.assertRaises(ValueError):
				self.adapter.verify_url(GatewayInboundRequest(b"", query=query, method="GET"))

	def test_verify_url_rejects_when_no_token_configured(self):
		adapter = WhatsAppGatewayAdapter(CREDS)
		adapter._verify_token = ""
		req = GatewayInboundRequest(b"", query={"hub.verify_token": "", "hub.challenge": "abc"}, method="GET")
		with self.assertRaises(ValueError):
			adapter.verify_url(req)
		self.assertFalse(adapter.verify_inbound(req))

	def test_post_requires_valid_signature(self):
		self.assertTrue(self.adapter.verify_inbound(_signed(_message_payload())))
		self.assertFalse(self.adapter.verify_inbound(GatewayInboundRequest(b"{}", method="POST")))

	def test_normalizes_message(self):
		event = self.adapter.normalize_inbound(_signed(_message_payload()))
		self.assertEqual(event.provider_event_id, "wamid.in")
		self.assertEqual(event.thread_id, "wamid.prev")

	def test_status_only_payload_is_ignored(self):
		self.assertIsNone(self.adapter.normalize_inbound(_signed(_status_payload())))

	def test_empty_payload_still_raises(self):
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(_signed({"object": "whatsapp_business_account"}))

	@patch("huf.ai.gateway_adapters.whatsapp.frappe")
	def test_send_reply_text(self, _frappe):
		d = self.adapter.send_reply(GatewayReply("1234567890", "hi", reply_to_provider_message_id="wamid.prev"))
		self.assertEqual(d.provider_message_id, "wamid.123")
		call = self.calls[0]
		self.assertEqual(call["url"], f"{META_GRAPH_URL}/phone-123/messages")
		self.assertEqual(call["json"]["context"], {"message_id": "wamid.prev"})
		self.assertEqual(call["headers"]["Authorization"], "Bearer access-token")

	@patch("huf.ai.gateway_adapters.whatsapp.frappe")
	def test_sender_template(self, _frappe):
		sent = []

		def post(url, *, json, headers, timeout):
			sent.append(json)
			return FakeResponse({"messages": [{"id": "wamid.t"}]})

		WhatsAppSender("p1", "tok", http_post=post).send_template("1555", "order", "en_US", ["Jane"])
		self.assertEqual(sent[0]["type"], "template")
		self.assertEqual(sent[0]["template"]["components"][0]["parameters"], [{"type": "text", "text": "Jane"}])

	def test_outbound_error_raises(self):
		self.adapter._http_post = lambda *a, **k: FakeResponse({"error": {"message": "denied"}})
		with self.assertRaisesRegex(ValueError, "denied"):
			self.adapter.send_reply(GatewayReply("1234567890", "hello"))


class _Resp:
	http_status_code = 200


class TestWhatsAppWebhookGates(unittest.TestCase):
	def _run(self, mock_frappe, method, enabled, adapter):
		mock_frappe.request = SimpleNamespace(args={"gateway_name": "WA"}, method=method)
		mock_frappe.local = SimpleNamespace(response=_Resp())
		mock_frappe.local.response.update = lambda d: None
		mock_frappe.get_doc.return_value = SimpleNamespace(name="WA", provider="WhatsApp", is_enabled=enabled)
		req = GatewayInboundRequest(b"{}", method=method)
		with patch.object(gateway_webhook, "get_gateway_adapter", return_value=adapter), \
			patch.object(gateway_webhook, "_inbound_request", return_value=req), \
			patch.object(gateway_webhook, "_text_response") as txt:
			return gateway_webhook.handle_gateway_webhook(), txt, mock_frappe.local.response

	@patch("huf.ai.gateway_webhook.frappe")
	def test_get_verification_succeeds_when_disabled(self, mock_frappe):
		adapter = MagicMock()
		adapter.verify_url.return_value = "challenge"
		result, txt, resp = self._run(mock_frappe, "GET", 0, adapter)
		self.assertIsNone(result)
		txt.assert_called_once_with("challenge")
		self.assertEqual(resp.http_status_code, 200)

	@patch("huf.ai.gateway_webhook.frappe")
	def test_post_blocked_when_disabled(self, mock_frappe):
		result, _txt, resp = self._run(mock_frappe, "POST", 0, MagicMock())
		self.assertEqual(resp.http_status_code, 403)
		self.assertFalse(result["success"])

	@patch("huf.ai.gateway_service.ingest_gateway_event")
	@patch("huf.ai.gateway_webhook.frappe")
	def test_status_event_acked_without_ingest(self, mock_frappe, ingest):
		adapter = MagicMock()
		adapter.verify_inbound.return_value = True
		adapter.normalize_inbound.return_value = None
		result, _txt, resp = self._run(mock_frappe, "POST", 1, adapter)
		self.assertEqual(result, {"success": True, "ignored": True})
		self.assertEqual(resp.http_status_code, 200)
		ingest.assert_not_called()


if __name__ == "__main__":
	unittest.main()
