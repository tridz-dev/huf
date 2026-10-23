# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram test environment: /test/ URL segment, redaction, gateway field, allow-list."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_client import (
	TelegramBotClient,
	bot_api_url,
	bot_file_url,
	truthy_flag,
)
from huf.ai.telegram_management_settings import FIELD_SPECS

TOKEN = "123456789:AAFakeTokenValue-1234567890"
GATEWAY_JSON = Path(__file__).resolve().parents[2] / "huf" / "doctype" / "gateway" / "gateway.json"


class _Resp:
	def __init__(self, body=None, content=b"x", status_code=200):
		self._body, self.content, self.status_code = body, content, status_code

	def json(self):
		return self._body


class TestUrls(unittest.TestCase):
	def test_builders(self):
		self.assertEqual(bot_api_url(TOKEN, "getMe"), f"https://api.telegram.org/bot{TOKEN}/getMe")
		self.assertEqual(
			bot_api_url(TOKEN, "getMe", test_environment=True), f"https://api.telegram.org/bot{TOKEN}/test/getMe"
		)
		self.assertEqual(bot_file_url(TOKEN, "p/a.jpg"), f"https://api.telegram.org/file/bot{TOKEN}/p/a.jpg")
		self.assertEqual(
			bot_file_url(TOKEN, "p/a.jpg", test_environment=True),
			f"https://api.telegram.org/file/bot{TOKEN}/test/p/a.jpg",
		)

	def test_truthy_flag(self):
		self.assertTrue(truthy_flag("1") and truthy_flag(1) and truthy_flag("true"))
		self.assertFalse(truthy_flag("0") or truthy_flag("") or truthy_flag(None) or truthy_flag(0))

	def _client(self, flag):
		calls = []

		def post(url, **kw):
			calls.append(url)
			return _Resp({"ok": True, "result": {"file_path": "p/a.jpg"}})

		def get(url, timeout=None):
			calls.append(url)
			return _Resp(content=b"data")

		return TelegramBotClient(TOKEN, http_post=post, http_get=get, test_environment=flag), calls

	def test_client_api_and_file_paths(self):
		for flag, seg in ((False, ""), (True, "/test")):
			client, calls = self._client(flag)
			client.call("getWebhookInfo")
			client.download_file("fid")
			self.assertEqual(calls[0], f"https://api.telegram.org/bot{TOKEN}{seg}/getWebhookInfo")
			self.assertEqual(calls[2], f"https://api.telegram.org/file/bot{TOKEN}{seg}/p/a.jpg")
			self.assertEqual(client.test_environment, flag)

	def test_set_and_delete_webhook_use_test_path(self):
		client, calls = self._client(True)
		client.set_webhook("https://x.example/h", secret_token="s" * 20)
		client.call("deleteWebhook")
		self.assertTrue(all(f"/bot{TOKEN}/test/" in u for u in calls))

	def test_redaction_in_test_env_errors(self):
		def boom(url, **kw):
			raise RuntimeError(f"connection failed for {url}")

		client = TelegramBotClient(TOKEN, http_post=boom, test_environment=True)
		with self.assertRaises(Exception) as cm:
			client.call("getMe")
		text = str(cm.exception)
		self.assertNotIn(TOKEN, text)
		self.assertNotIn(TOKEN.split(":")[1], text)
		self.assertIn("/test/getMe", text)

	def test_adapter_reads_credential_flag(self):
		base = {"token": TOKEN, "webhook_secret": "w" * 24}
		self.assertFalse(TelegramGatewayAdapter(base).client.test_environment)
		self.assertTrue(TelegramGatewayAdapter({**base, "test_environment": "1"}).client.test_environment)


class TestFieldContract(unittest.TestCase):
	def test_gateway_json(self):
		doc = json.loads(GATEWAY_JSON.read_text())
		field = next(f for f in doc["fields"] if f["fieldname"] == "telegram_test_environment")
		self.assertEqual(field["fieldtype"], "Check")
		self.assertEqual(str(field.get("default")), "0")
		self.assertIn("Telegram", field["depends_on"])
		self.assertIn("test", field["description"].lower())
		self.assertIn("telegram_test_environment", doc["field_order"])

	def test_field_specs(self):
		self.assertEqual(FIELD_SPECS["telegram_test_environment"]["type"], "check")
