"""Focused fixtures for the VK Community Callback API adapter."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply, assert_adapter_conforms
from huf.ai.gateway_adapters.vk import VK_MESSAGES_SEND_URL, VKGatewayAdapter


class FakeResponse:
	def __init__(self, body):
		self.body = body
		self.raised = False

	def raise_for_status(self):
		self.raised = True

	def json(self):
		return self.body


class TestVKGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.adapter = VKGatewayAdapter(
			{
				"community_token": "community-token",
				"callback_secret": "callback-secret",
				"confirmation_string": "confirmation-value",
			},
			http_post=self._post,
			random_id_factory=lambda: 123,
		)

	def _post(self, url, *, data, timeout):
		self.calls.append({"url": url, "data": data, "timeout": timeout})
		return FakeResponse({"response": 42})

	@staticmethod
	def request(payload):
		return GatewayInboundRequest(json.dumps(payload).encode())

	def message_payload(self, **overrides):
		payload = {
			"type": "message_new",
			"event_id": "event-1",
			"secret": "callback-secret",
			"object": {"message": {"from_id": 10, "peer_id": 2_000_000_001, "text": "hello", "conversation_message_id": 7}},
		}
		payload.update(overrides)
		return payload

	def test_verification_is_fail_closed_and_confirmation_is_separate(self):
		valid = self.request(self.message_payload())
		self.assertTrue(self.adapter.verify_inbound(valid))
		self.assertFalse(self.adapter.verify_inbound(self.request(self.message_payload(secret="wrong"))))
		confirmation = self.request({"type": "confirmation", "group_id": 1})
		self.assertEqual(self.adapter.confirmation_response(confirmation), "confirmation-value")
		self.assertFalse(self.adapter.verify_inbound(confirmation))

	def test_normalizes_only_verified_message_events(self):
		event = self.adapter.normalize_inbound(self.request(self.message_payload()))
		self.assertEqual(event.provider_event_id, "event-1")
		self.assertEqual(event.sender_id, "10")
		self.assertEqual(event.conversation_id, "2000000001")
		self.assertEqual(event.thread_id, "7")
		self.assertTrue(event.is_room)
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request(self.message_payload(type="wall_reply_new")))

	def test_send_reply_uses_community_token_and_vk_required_parameters(self):
		delivery = self.adapter.send_reply(GatewayReply("2000000001", "hello back", reply_to_provider_message_id="99"))
		self.assertEqual(delivery.provider_message_id, "42")
		self.assertEqual(self.calls, [{
			"url": VK_MESSAGES_SEND_URL,
			"data": {"access_token": "community-token", "v": "5.199", "peer_id": "2000000001", "message": "hello back", "random_id": "123", "reply_to": "99"},
			"timeout": 10,
		}])

	def test_adapter_conforms_with_verified_callback_fixture(self):
		event = assert_adapter_conforms(
			self.adapter,
			self.request(self.message_payload()),
			GatewayReply("2000000001", "hello back"),
		)
		self.assertEqual(event.message_text, "hello")

	def test_outbound_errors_are_not_silently_accepted(self):
		self.adapter._http_post = lambda *args, **kwargs: FakeResponse({"error": {"error_msg": "denied"}})
		with self.assertRaisesRegex(ValueError, "denied"):
			self.adapter.send_reply(GatewayReply("2000000001", "hello"))
