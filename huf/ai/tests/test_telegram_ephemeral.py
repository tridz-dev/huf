"""Ephemeral command replies: detection, payloads, private chats ignored, unchanged defaults."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from huf.ai.gateway_adapters import telegram_ephemeral as te
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender


class Client:
	def __init__(self):
		self.calls = []

	def call(self, method, payload, files=None):
		self.calls.append((method, payload))
		return {"message_id": 9}


def group(**extra):
	msg = {"chat": {"id": -100, "type": "supergroup"}, "from": {"id": 42}, "text": "/help",
		"ephemeral_message_id": 5, "receiver_user": {"id": 42}}
	msg.update(extra)
	return {"message": msg}


class TestEphemeral(unittest.TestCase):
	def test_detection(self):
		self.assertTrue(te.is_ephemeral_command(group()))
		self.assertFalse(te.is_ephemeral_command(group(ephemeral_message_id=None, receiver_user=None)))
		self.assertFalse(te.is_ephemeral_command(None))
		self.assertFalse(te.is_ephemeral_command({"message": {"chat": {"type": "private"},
			"ephemeral_message_id": 1, "receiver_user": {"id": 1}}}))

	def test_params(self):
		self.assertEqual(te.ephemeral_params(group()), {
			"ephemeral_message_parameters": {"receiver_user_id": 42},
			"reply_parameters": {"ephemeral_message_id": 5}})
		self.assertEqual(te.ephemeral_params({"message": {"chat": {"type": "private"}, "receiver_user": {"id": 1}}}), {})

	def test_send_text_payload(self):
		c = Client()
		TelegramSender(c).send_text(-100, "hi", reply_to="7", ephemeral=te.ephemeral_params(group()))
		p = c.calls[0][1]
		self.assertEqual(p["ephemeral_message_parameters"], {"receiver_user_id": 42})
		self.assertEqual(p["reply_parameters"], {"ephemeral_message_id": 5})

	def test_no_quote_without_reply_to(self):
		c = Client()
		TelegramSender(c).send_text(-100, "hi", ephemeral=te.ephemeral_params(group()))
		self.assertNotIn("reply_parameters", c.calls[0][1])

	def test_defaults_unchanged(self):
		c = Client()
		TelegramSender(c).send_text(-100, "hi", reply_to="7")
		p = c.calls[0][1]
		self.assertNotIn("ephemeral_message_parameters", p)
		self.assertEqual(p["reply_parameters"]["message_id"], 7)

	def test_pipeline(self):
		c = Client()
		s = TelegramSender(c)
		tp.send_parts_with(s, -100, ["a", "b"], reply_to="7", ephemeral=tp.ephemeral_for(
			SimpleNamespace(raw_payload=group())))
		self.assertTrue(all("ephemeral_message_parameters" in p for _m, p in c.calls))
		self.assertIsNone(tp.ephemeral_for(SimpleNamespace(raw_payload={})))
		c.calls.clear()
		tp.send_parts_with(s, 1, ["a"])
		self.assertNotIn("ephemeral_message_parameters", c.calls[0][1])


if __name__ == "__main__":
	unittest.main()
