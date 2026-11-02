"""The fake Bot API must reject what the real one rejects (otherwise "ok" assertions prove nothing)."""

import unittest

from huf.ai.tests.telegram_fakes import BotApiContractError, FakeBotApi, validate_call


class TestFakeBotApiStrict(unittest.TestCase):
	def test_rejects_invalid_calls(self):
		bad = [
			("noSuchMethod", {}),
			("sendMessage", {"chat_id": 1}),
			("sendMessage", {"chat_id": 1, "text": 5}),
			("sendMessage", {"chat_id": 1, "text": "x", "bogus": 1}),
			("sendMessage", {"chat_id": 1, "text": "x", "reply_markup": '{"inline_keyboard": []}'}),
			("sendMessage", {"chat_id": 1, "text": "x", "reply_parameters": "{}"}),
			("sendMessage", {"chat_id": 1, "text": "x", "link_preview_options": "{}"}),
			("setMyCommands", {"commands": "[]"}),
			("restrictChatMember", {"chat_id": 1, "user_id": 2, "permissions": "{}"}),
			("setMessageReaction", {"chat_id": 1, "message_id": 2, "reaction": "[]"}),
			("sendMediaGroup", {"chat_id": 1, "media": "[]"}),
			("answerCallbackQuery", {"callback_query_id": "1", "show_alert": "yes"}),
		]
		for method, payload in bad:
			with self.subTest(method=method, payload=payload), self.assertRaises(BotApiContractError):
				validate_call(method, payload)

	def test_accepts_valid_calls_and_multipart_json_strings(self):
		validate_call("sendMessage", {"chat_id": "@c", "text": "hi", "reply_markup": {"inline_keyboard": []}})
		validate_call(
			"sendPhoto",
			{"chat_id": 1, "reply_markup": '{"inline_keyboard": []}'},
			multipart=True,
			files={"photo": b"x"},
		)

	def test_fake_raises_through_http_post(self):
		with self.assertRaises(BotApiContractError):
			FakeBotApi().http_post("https://api.telegram.org/botT/sendMessage", json_data={"chat_id": 1})
