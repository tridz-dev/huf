"""Focused fixtures for the WhatsApp Cloud API adapter."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply, assert_adapter_conforms
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

class FakeResponse:
	def __init__(self, body):
		self.body = body
		self.raised = False

	def raise_for_status(self):
		self.raised = True

	def json(self):
		return self.body

@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
class TestWhatsAppGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.adapter = WhatsAppGatewayAdapter(
			{
				"phone_number_id": "phone-123",
				"access_token": "access-token",
				"verify_token": "verify-value",
			},
			http_post=self._post,
		)

	def _post(self, url, *, headers, json_data, timeout):
		self.calls.append({"url": url, "headers": headers, "json": json_data, "timeout": timeout})
		return FakeResponse({"messages": [{"id": "wamid.123"}]})

	@staticmethod
	def request(payload):
		return GatewayInboundRequest(json.dumps(payload).encode())

	def message_payload(self, **overrides):
		payload = {
			"object": "whatsapp_business_account",
			"entry": [
				{
					"changes": [
						{
							"value": {
								"messages": [
									{
										"from": "1234567890",
										"id": "wamid.inbound123",
										"type": "text",
										"text": {"body": "hello"},
										"context": {"id": "wamid.prev123"}
									}
								]
							}
						}
					]
				}
			]
		}
		if overrides:
			payload.update(overrides)
		return payload

	def test_verification_is_fail_closed_and_confirmation_is_separate(self):
		valid = self.request(self.message_payload())
		self.assertTrue(self.adapter.verify_inbound(valid))
		self.assertFalse(self.adapter.verify_inbound(self.request(self.message_payload(object="wrong"))))
		confirmation = GatewayInboundRequest(b"", query={"hub.mode": "subscribe", "hub.verify_token": "verify-value", "hub.challenge": "challenge-string"})
		self.assertEqual(self.adapter.verify_url(confirmation), "challenge-string")

	def test_normalizes_only_verified_message_events(self):
		event = self.adapter.normalize_inbound(self.request(self.message_payload()))
		self.assertEqual(event.provider_event_id, "wamid.inbound123")
		self.assertEqual(event.sender_id, "1234567890")
		self.assertEqual(event.conversation_id, "1234567890")
		self.assertEqual(event.thread_id, "wamid.prev123")
		self.assertFalse(event.is_room)
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request({"object": "whatsapp_business_account"}))

	def test_send_reply_uses_access_token_and_whatsapp_required_parameters(self):
		delivery = self.adapter.send_reply(GatewayReply("1234567890", "hello back", reply_to_provider_message_id="wamid.prev123"))
		self.assertEqual(delivery.provider_message_id, "wamid.123")
		self.assertEqual(self.calls, [{
			"url": "https://graph.facebook.com/v17.0/phone-123/messages",
			"headers": {"Authorization": "Bearer access-token", "Content-Type": "application/json"},
			"json": {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "1234567890",
                "type": "text",
                "text": {"preview_url": False, "body": "hello back"},
                "context": {"message_id": "wamid.prev123"}
            },
			"timeout": 10,
		}])

	def test_adapter_conforms_with_verified_callback_fixture(self):
		event = assert_adapter_conforms(
			self.adapter,
			self.request(self.message_payload()),
			GatewayReply("1234567890", "hello back"),
		)
		self.assertEqual(event.message_text, "hello")

	def test_outbound_errors_are_not_silently_accepted(self):
		self.adapter._http_post = lambda *args, **kwargs: FakeResponse({"error": {"message": "denied"}})
		with self.assertRaisesRegex(ValueError, "denied"):
			self.adapter.send_reply(GatewayReply("1234567890", "hello"))
