# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import provider_hooks
from huf.ai.gateway_adapters import telegram_integration_hooks as hooks
from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES


def _event(raw, conversation_id="42"):
	return NS(
		raw_payload=raw,
		conversation_id=conversation_id,
		thread_id="9",
		sender_id="7",
		name="E1",
		agent_run="AR",
	)


class TestConversationKey(unittest.TestCase):
	def test_registered_for_telegram(self):
		self.assertIs(provider_hooks.get("Telegram", "conversation_key"), hooks.conversation_key)

	def test_plain_chat_uses_chat_id_not_message_id(self):
		event = _event({"message": {"message_id": 9, "chat": {"id": 42, "type": "private"}}})
		self.assertEqual(hooks.conversation_key(event), "42")

	def test_topic_gets_its_own_conversation(self):
		event = _event(
			{
				"message": {
					"message_id": 9,
					"message_thread_id": 77,
					"is_topic_message": True,
					"chat": {"id": -100, "type": "supergroup"},
				}
			},
			conversation_id="-100",
		)
		self.assertEqual(hooks.conversation_key(event), "-100:77")

	def test_missing_chat_returns_none(self):
		self.assertIsNone(hooks.conversation_key(_event({}, conversation_id="")))


class TestGuestReply(unittest.TestCase):
	def test_non_guest_event_is_not_handled(self):
		self.assertIsNone(hooks.guest_reply(_event({"message": {}}), MagicMock(), "hi"))

	def test_guest_event_answers_via_answer_guest_query(self):
		event = _event({"telegram_meta": {"guest": True}, "guest_message": {"guest_query_id": "GQ1"}})
		event.db_set = MagicMock()
		adapter = NS(client=MagicMock())
		with (
			patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter),
			patch(
				"huf.ai.gateway_adapters.telegram_guest.reply_for_guest",
				return_value={"inline_message_id": "x"},
			) as reply,
		):
			result = hooks.guest_reply(event, MagicMock(), "hello")
		reply.assert_called_once_with(adapter.client, "GQ1", "hello")
		self.assertEqual(result["status"], "Succeeded")
		self.assertTrue(result["guest"])

	def test_guest_reply_failure_marks_event_failed(self):
		event = _event({"telegram_meta": {"guest": True}, "guest_message": {"guest_query_id": "GQ1"}})
		event.db_set = MagicMock()
		with (
			patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=NS(client=MagicMock())),
			patch("huf.ai.gateway_adapters.telegram_guest.reply_for_guest", return_value=None),
		):
			result = hooks.guest_reply(event, MagicMock(), "hello")
		self.assertEqual(result["status"], "Failed")


class TestAllowedUpdates(unittest.TestCase):
	def test_guest_and_core_updates_are_requested(self):
		for name in (
			"message",
			"callback_query",
			"message_reaction",
			"guest_message",
			"chat_join_request",
			"business_message",
		):
			self.assertIn(name, ALLOWED_UPDATES)
