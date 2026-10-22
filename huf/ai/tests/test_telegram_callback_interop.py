# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import unittest
from types import SimpleNamespace as NS

from huf.ai.gateway_adapters import telegram_buttons as tb
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_keyboards import derive_callback_key, sign_callback


class _Sender:
	def __init__(self):
		self.answered = []

	def answer_callback_query(self, cqid, text=""):
		self.answered.append((cqid, text))

	def edit_message_reply_markup(self, *args, **kwargs):
		pass


class TestToolSignedCallbackInterop(unittest.TestCase):
	"""A button signed by the agent tool (raw payload) must verify with the adapter and be ingested."""

	def test_tool_signed_button_is_verified_and_ingested_as_text(self):
		adapter = TelegramGatewayAdapter({"token": "1:x", "webhook_secret": "s3cret"})
		data = sign_callback(derive_callback_key("s3cret"), "approve_42", context="42")
		payload = adapter.verify_callback_data(data, "42")
		self.assertEqual(payload, "approve_42")
		parsed = NS(
			callback_query_id="cq1", chat_id="42", message_id=5, callback_data=data,
			raw={"callback_query": {"message": {"date": 100}}},
		)
		sender = _Sender()
		cache = NS(get_value=lambda key: None, set_value=lambda *args, **kwargs: None)
		decision = tb.handle_callback(parsed, payload, sender, "gw", cache=cache, now=110)
		self.assertEqual(decision["action"], "ingest")
		self.assertEqual(decision["reason"], "foreign")
		self.assertEqual(decision["text"], "approve_42")
		self.assertEqual(sender.answered, [("cq1", "")])

	def test_tool_signed_button_for_another_chat_is_rejected(self):
		adapter = TelegramGatewayAdapter({"token": "1:x", "webhook_secret": "s3cret"})
		data = sign_callback(derive_callback_key("s3cret"), "approve_42", context="42")
		self.assertIsNone(adapter.verify_callback_data(data, "999"))
