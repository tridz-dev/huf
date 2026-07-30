"""Focused fixtures for the Telegram Bot API adapter."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters import GatewayInboundRequest, GatewayReply, assert_adapter_conforms
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter


class FakeResponse:
	def __init__(self, body):
		self.body = body
		self.raised = False

	def raise_for_status(self):
		self.raised = True

	def json(self):
		return self.body


class TestTelegramGatewayAdapter(unittest.TestCase):
	def setUp(self):
		self.calls = []
		self.adapter = TelegramGatewayAdapter(
			{"token": "123:ABC", "webhook_secret": "shh"},
			http_post=self._post,
		)

	def _post(self, url, *, json_data, timeout):
		self.calls.append({"url": url, "json_data": json_data, "timeout": timeout})
		return FakeResponse({"ok": True, "result": {"message_id": 42}})

	@staticmethod
	def request(payload, secret="shh"):
		headers = {WEBHOOK_SECRET_HEADER: secret} if secret else {}
		return GatewayInboundRequest(json.dumps(payload).encode(), headers=headers)

	def message_payload(self, **overrides):
		payload = {
			"update_id": 555,
			"message": {
				"message_id": 10,
				"chat": {"id": 999, "type": "private"},
				"from": {"id": 111},
				"text": "hello bot",
			},
		}
		payload.update(overrides)
		return payload

	def test_verification_is_fail_closed_on_configured_secret(self):
		valid = self.request(self.message_payload())
		self.assertTrue(self.adapter.verify_inbound(valid))
		self.assertFalse(self.adapter.verify_inbound(self.request(self.message_payload(), secret="wrong")))
		self.assertFalse(self.adapter.verify_inbound(self.request(self.message_payload(), secret=None)))

	def test_verification_accepts_when_no_secret_configured(self):
		open_adapter = TelegramGatewayAdapter({"token": "123:ABC"}, http_post=self._post)
		self.assertTrue(open_adapter.verify_inbound(self.request(self.message_payload(), secret=None)))

	def test_missing_required_token_raises(self):
		with self.assertRaisesRegex(ValueError, "token"):
			TelegramGatewayAdapter({})

	def test_normalizes_private_message(self):
		event = self.adapter.normalize_inbound(self.request(self.message_payload()))
		self.assertEqual(event.provider_event_id, "555")
		self.assertEqual(event.sender_id, "111")
		self.assertEqual(event.conversation_id, "999")
		self.assertEqual(event.message_text, "hello bot")
		self.assertEqual(event.thread_id, "10")
		self.assertFalse(event.is_room)
		self.assertFalse(event.mentioned)

	def test_normalizes_group_message_with_bot_command_as_mentioned(self):
		payload = self.message_payload(
			message={
				"message_id": 11,
				"chat": {"id": -1001, "type": "supergroup"},
				"from": {"id": 222},
				"text": "/start",
				"entities": [{"type": "bot_command", "offset": 0, "length": 6}],
			}
		)
		event = self.adapter.normalize_inbound(self.request(payload))
		self.assertTrue(event.is_room)
		self.assertTrue(event.mentioned)

	def test_normalize_rejects_unverified_request(self):
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request(self.message_payload(), secret="wrong"))

	def test_normalize_rejects_missing_identifiers(self):
		payload = self.message_payload(message={"message_id": 1, "chat": {}, "from": {}, "text": "hi"})
		with self.assertRaises(ValueError):
			self.adapter.normalize_inbound(self.request(payload))

	def test_send_reply_calls_send_message_with_bot_token(self):
		delivery = self.adapter.send_reply(GatewayReply("999", "hi there", reply_to_provider_message_id="10"))
		self.assertEqual(delivery.provider_message_id, "42")
		self.assertEqual(self.calls, [{
			"url": "https://api.telegram.org/bot123:ABC/sendMessage",
			"json_data": {"chat_id": "999", "text": "hi there", "reply_to_message_id": 10},
			"timeout": 10,
		}])

	def test_adapter_conforms_with_verified_webhook_fixture(self):
		event = assert_adapter_conforms(
			self.adapter,
			self.request(self.message_payload()),
			GatewayReply("999", "hi there"),
		)
		self.assertEqual(event.message_text, "hello bot")

	def test_outbound_errors_are_not_silently_accepted(self):
		self.adapter._http_post = lambda *args, **kwargs: FakeResponse(
			{"ok": False, "description": "bot was blocked by the user"}
		)
		with self.assertRaisesRegex(ValueError, "blocked"):
			self.adapter.send_reply(GatewayReply("999", "hi there"))
