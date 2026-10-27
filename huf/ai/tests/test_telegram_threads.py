"""Threads, topics, group addressing, ephemeral replies; payloads carry message_thread_id."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters import telegram_threads as th
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi


class TestKeys(unittest.TestCase):
	def test_conversation_key(self):
		self.assertEqual(th.conversation_key(-100, None), "-100")
		self.assertEqual(th.conversation_key(-100, "7"), "-100:7")
		self.assertEqual(th.conversation_key(5, 0), "5")
		self.assertNotEqual(th.conversation_key(5, 1), th.conversation_key(5, 2))

	def test_thread_id_for_reply(self):
		self.assertEqual(
			th.thread_id_for_reply(
				{"message_thread_id": 9, "is_topic_message": True, "chat": {"type": "supergroup"}}
			),
			"9",
		)
		self.assertEqual(th.thread_id_for_reply({"message_thread_id": 9, "chat": {"type": "private"}}), "9")
		# reply chain in a non-forum supergroup: not a topic, must not be sent back
		self.assertIsNone(th.thread_id_for_reply({"message_thread_id": 9, "chat": {"type": "supergroup"}}))
		self.assertIsNone(th.thread_id_for_reply({"chat": {"type": "private"}}))

	def test_with_thread(self):
		self.assertEqual(th.with_thread({"a": 1}, "4"), {"a": 1, "message_thread_id": 4})
		self.assertEqual(th.with_thread({"a": 1}, None), {"a": 1})


class TestAddressing(unittest.TestCase):
	G = {"type": "supergroup"}

	def test_private_always(self):
		self.assertTrue(th.is_addressed_to_bot({"chat": {"type": "private"}, "text": "x"}, "b", 1))

	def test_mention_entity(self):
		m = {
			"chat": self.G,
			"text": "yo @Huf_Bot ok",
			"entities": [{"type": "mention", "offset": 3, "length": 8}],
		}
		self.assertTrue(th.is_addressed_to_bot(m, "huf_bot", 1))
		self.assertFalse(th.is_addressed_to_bot(m, "other_bot", 1))

	def test_text_mention_and_reply(self):
		m = {
			"chat": self.G,
			"text": "x",
			"entities": [{"type": "text_mention", "offset": 0, "length": 1, "user": {"id": 1}}],
		}
		self.assertTrue(th.is_addressed_to_bot(m, "b", 1))
		self.assertTrue(
			th.is_addressed_to_bot(
				{"chat": self.G, "text": "k", "reply_to_message": {"from": {"id": 1}}}, "b", 1
			)
		)
		self.assertFalse(
			th.is_addressed_to_bot(
				{"chat": self.G, "text": "k", "reply_to_message": {"from": {"id": 2}}}, "b", 1
			)
		)

	def test_command_at_bot(self):
		ent = [{"type": "bot_command", "offset": 0, "length": 10}]
		self.assertTrue(
			th.is_addressed_to_bot(
				{
					"chat": self.G,
					"text": "/help@huf_bot",
					"entities": [{"type": "bot_command", "offset": 0, "length": 13}],
				},
				"huf_bot",
				1,
			)
		)
		self.assertFalse(
			th.is_addressed_to_bot({"chat": self.G, "text": "/help@x_bot a", "entities": ent}, "huf_bot", 1)
		)

	def test_utf16_offsets(self):
		m = {
			"chat": self.G,
			"text": "\U0001f600 @b_bot",
			"entities": [{"type": "mention", "offset": 3, "length": 6}],
		}
		self.assertTrue(th.is_addressed_to_bot(m, "b_bot", 1))


class TestEphemeral(unittest.TestCase):
	def test_params(self):
		self.assertEqual(th.ephemeral_reply_params({"from": {"id": 3}}), {})
		m = {"from": {"id": 3}, "ephemeral_message_id": 11, "receiver_user": {"id": 3}}
		self.assertEqual(
			th.ephemeral_reply_params(m),
			{
				"ephemeral_message_parameters": {"receiver_user_id": 3},
				"reply_parameters": {"ephemeral_message_id": 11},
			},
		)


class TestPayloads(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			http_get=self.api.http_get,
			download_attachments=False,
		)
		self.s = self.adapter.sender

	def test_senders_carry_thread(self):
		self.s.send_text(5, "hi", thread_id="9")
		self.s.send_chat_action(5, "typing", thread_id="9")
		self.s.send_message_draft(5, 1, "d", thread_id="9")
		self.s.send_location(5, 1.0, 2.0, thread_id="9")
		self.s.send_contact(5, "+1", "A", thread_id="9")
		for method in ("sendMessage", "sendChatAction", "sendMessageDraft", "sendLocation", "sendContact"):
			self.assertEqual(self.api.last(method)["payload"]["message_thread_id"], 9, method)

	def test_no_thread_omitted(self):
		self.s.send_text(5, "hi")
		self.assertNotIn("message_thread_id", self.api.last("sendMessage")["payload"])

	def test_adapter_typing_threaded(self):
		self.adapter.send_typing(5, "typing", "9")
		self.assertEqual(self.api.last("sendChatAction")["payload"]["message_thread_id"], 9)

	def test_create_topic(self):
		th.create_topic(self.adapter.client, 5, "Order 1")
		self.assertEqual(self.api.last("createForumTopic")["payload"], {"chat_id": 5, "name": "Order 1"})
		with self.assertRaises(ValueError):
			th.create_topic_payload(5, "")


if __name__ == "__main__":
	unittest.main()
