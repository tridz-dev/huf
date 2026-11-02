# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram agent tool and webhook reply path over the in-memory fake Bot API (no network).

Every test patches ``_make_client`` so no request can reach api.telegram.org; webhook setup is
exercised only through the fake, never against the live bot.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramBotClient
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi
from huf.ai.tools import telegram as tool
from huf.ai.tools.telegram_webhook import _send_telegram_message


class TestTelegramTools(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()

		def fake_make_client(token, *, timeout=30):
			return TelegramBotClient(
				token,
				http_post=self.api.http_post,
				http_get=self.api.http_get,
				timeout=timeout,
				sleep=lambda s: None,
			)

		self.update_last_error = patch.object(tool, "update_last_error").start()
		self.addCleanup(patch.stopall)
		patch.object(tool, "_make_client", side_effect=fake_make_client).start()
		patch.object(tool, "_get_token", return_value=TOKEN).start()
		patch.object(tool.scope, "run_gateway", return_value="").start()  # legacy (non-gateway) path
		patch("huf.ai.http_handler.validate_url", return_value=(True, None)).start()  # no DNS in unit tests

	def run_action(self, **kwargs):
		return json.loads(tool.handle_action(**kwargs))

	def test_send_message_uses_reply_parameters(self):
		result = self.run_action(action="send_message", chat_id="999", text="hi", reply_to_message_id="7")
		self.assertTrue(result["success"])
		self.assertEqual(result["results"]["message_id"], 101)
		payload = self.api.last("sendMessage")["payload"]
		self.assertEqual(payload["chat_id"], "999")
		self.assertEqual(payload["text"], "hi")
		self.assertEqual(payload["reply_parameters"], {"message_id": 7, "allow_sending_without_reply": True})
		self.assertNotIn("reply_to_message_id", payload)

	def test_reply_to_message_requires_reply_id(self):
		result = self.run_action(action="reply_to_message", chat_id="999", text="hi")
		self.assertFalse(result["success"])
		self.assertEqual(result["error"], "invalid_argument")
		self.assertEqual(result["missing_arguments"], ["reply_to_message_id"])
		self.assertEqual(self.api.calls, [])

	def test_send_photo_by_url_uses_reply_parameters(self):
		result = self.run_action(
			action="send_photo", chat_id="999", photo="https://cdn.test/a.jpg", reply_to_message_id=3
		)
		self.assertTrue(result["success"])
		payload = self.api.last("sendPhoto")["payload"]
		self.assertEqual(payload["photo"], "https://cdn.test/a.jpg")
		self.assertEqual(payload["reply_parameters"]["message_id"], 3)

	def test_api_rejection_is_returned_and_recorded_without_token(self):
		self.api.queue("sendMessage", FakeBotApi.error(f"Bad Request: chat not found {TOKEN}", 400))
		result = self.run_action(action="send_message", chat_id="999", text="hi")
		self.assertFalse(result["success"])
		self.assertIn("sendMessage", result["error"])
		self.assertIn("chat not found", result["error"])
		rendered = json.dumps(result)
		self.assertNotIn(TOKEN, rendered)
		self.assertNotIn(TOKEN.split(":", 1)[1], rendered)
		self.update_last_error.assert_called_once()

	def test_missing_token_makes_no_http_call(self):
		with patch.object(tool, "_get_token", return_value=None):
			result = self.run_action(action="get_me")
		self.assertFalse(result["success"])
		self.assertIn("token not configured", result["error"])
		self.assertEqual(self.api.calls, [])

	def test_get_me_calls_getme(self):
		result = self.run_action(action="get_me")
		self.assertTrue(result["success"])
		self.assertEqual([c["method"] for c in self.api.calls], ["getMe"])

	def test_set_webhook_sends_allowed_updates_and_secret_through_fake_only(self):
		result = self.run_action(action="set_webhook", url="https://example.test/hook", secret_token="s3cret")
		self.assertTrue(result["success"])
		payload = self.api.last("setWebhook")["payload"]
		self.assertEqual(payload["url"], "https://example.test/hook")
		self.assertEqual(payload["secret_token"], "s3cret")
		self.assertEqual(payload["allowed_updates"], list(ALLOWED_UPDATES))

	def test_delete_webhook_calls_fake_only(self):
		result = self.run_action(action="delete_webhook")
		self.assertTrue(result["success"])
		self.assertEqual([c["method"] for c in self.api.calls], ["deleteWebhook"])

	def test_setup_webhook_and_get_webhook_info_return_dicts(self):
		parsed = tool.setup_webhook(TOKEN, "https://example.test/hook", secret_token="s3cret")
		self.assertTrue(parsed["success"])
		info = tool.get_webhook_info(TOKEN)
		self.assertTrue(info["success"])
		self.assertEqual(info["results"]["url"], "https://x/h")
		self.assertEqual([c["method"] for c in self.api.calls], ["setWebhook", "getWebhookInfo"])

	def test_unknown_action_lists_valid_actions(self):
		result = self.run_action(action="nope")
		self.assertFalse(result["success"])
		self.assertIn("Valid actions", result["error"])
		self.assertEqual(self.api.calls, [])

	def test_webhook_reply_goes_through_reply_parameters(self):
		settings = SimpleNamespace(name="Telegram Bot A")
		_send_telegram_message(settings, "999", "hello back", reply_to_message_id=12)
		payload = self.api.last("sendMessage")["payload"]
		self.assertEqual(payload["chat_id"], "999")
		self.assertEqual(payload["reply_parameters"]["message_id"], 12)
		self.assertNotIn("reply_to_message_id", payload)
