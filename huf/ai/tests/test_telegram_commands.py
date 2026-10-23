"""setMyCommands builders: validation, scopes, languages, ephemeral flag."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters import telegram_commands as tc
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi


class TestBuild(unittest.TestCase):
	def test_valid_tuple_and_mapping(self):
		out = tc.build_commands(
			[("help", "Show help"), {"command": "me", "description": "Whisper", "is_ephemeral": True}]
		)
		self.assertEqual(
			out,
			[
				{"command": "help", "description": "Show help"},
				{"command": "me", "description": "Whisper", "is_ephemeral": True},
			],
		)

	def test_name_validation(self):
		for bad in ("", "Help", "he-lp", "a" * 33, "/start"):
			with self.assertRaises(ValueError, msg=bad):
				tc.build_commands([(bad, "d")])
		self.assertEqual(tc.build_commands([("a_1" + "b" * 29, "d")])[0]["command"][:3], "a_1")

	def test_description_validation(self):
		for bad in ("", "  ", "x" * 257):
			with self.assertRaises(ValueError):
				tc.build_commands([("ok", bad)])
		tc.build_commands([("ok", "x" * 256)])

	def test_limits_and_dupes(self):
		tc.build_commands([(f"c{i}", "d") for i in range(100)])
		with self.assertRaises(ValueError):
			tc.build_commands([(f"c{i}", "d") for i in range(101)])
		with self.assertRaises(ValueError):
			tc.build_commands([("a", "d"), ("a", "e")])
		with self.assertRaises(ValueError):
			tc.build_commands([])

	def test_scopes(self):
		self.assertEqual(tc.build_scope("all_group_chats"), {"type": "all_group_chats"})
		self.assertEqual(tc.build_scope("chat", chat_id=-5), {"type": "chat", "chat_id": -5})
		self.assertEqual(
			tc.build_scope("chat_member", chat_id=-5, user_id="7"),
			{"type": "chat_member", "chat_id": -5, "user_id": 7},
		)
		for s in ("all_private_chats", "all_chat_administrators", "default"):
			self.assertEqual(tc.build_scope(s)["type"], s)
		with self.assertRaises(ValueError):
			tc.build_scope("chat")
		with self.assertRaises(ValueError):
			tc.build_scope("chat_member", chat_id=1)
		with self.assertRaises(ValueError):
			tc.build_scope("nope")

	def test_payload_language(self):
		p = tc.build_payload([("a", "d")], scope="all_private_chats", language_code="de")
		self.assertEqual(p["scope"], {"type": "all_private_chats"})
		self.assertEqual(p["language_code"], "de")
		self.assertNotIn("scope", tc.build_payload([("a", "d")]))
		with self.assertRaises(ValueError):
			tc.build_payload([("a", "d")], language_code="deu")


class TestSend(unittest.TestCase):
	def test_calls(self):
		api = FakeBotApi()
		client = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=api.http_post,
			http_get=api.http_get,
			download_attachments=False,
		).client
		tc.set_commands(client, [("a", "d")], scope="chat", chat_id=-5, language_code="en")
		self.assertEqual(
			api.last("setMyCommands")["payload"],
			{
				"commands": [{"command": "a", "description": "d"}],
				"scope": {"type": "chat", "chat_id": -5},
				"language_code": "en",
			},
		)
		tc.delete_commands(client, scope="all_group_chats")
		self.assertEqual(api.last("deleteMyCommands")["payload"], {"scope": {"type": "all_group_chats"}})
		tc.get_commands(client)
		self.assertEqual(api.last("getMyCommands")["payload"], {})


if __name__ == "__main__":
	unittest.main()
