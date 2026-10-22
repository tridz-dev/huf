# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram bot health checks against the in-memory fake Bot API (no network, no Frappe)."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramBotClient
from huf.ai.gateway_adapters.telegram_health import check_bot, check_webhook, readiness
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi

EXPECTED_URL = "https://example.test/api/method/huf.ai.gateway_webhook.telegram"


def _me(**overrides):
	body = {"id": 42, "is_bot": True, "username": "HufTestBot", "first_name": "Huf"}
	body.update(overrides)
	return {"ok": True, "result": body}


def _hook(**overrides):
	body = {
		"url": EXPECTED_URL,
		"has_custom_certificate": False,
		"pending_update_count": 0,
		"allowed_updates": list(ALLOWED_UPDATES),
	}
	body.update(overrides)
	return {"ok": True, "result": body}


class TestTelegramHealth(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.client = TelegramBotClient(TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None)

	def test_check_bot_reports_identity_and_capability_flags(self):
		self.api.queue("getMe", _me(can_join_groups=True, can_connect_to_business=True, has_topics_enabled=False))
		info = check_bot(self.client)
		self.assertEqual(info["id"], 42)
		self.assertEqual(info["username"], "HufTestBot")
		self.assertTrue(info["can_join_groups"])
		self.assertTrue(info["can_connect_to_business"])
		self.assertFalse(info["has_topics_enabled"])
		self.assertFalse(info["supports_guest_queries"])
		self.assertFalse(info["supports_join_request_queries"])
		self.assertEqual(self.api.of("getMe")[0]["method"], "getMe")

	def test_check_bot_tolerates_unexpected_result_shape(self):
		# The default fake answers getMe with result=True (not a bot object).
		info = check_bot(self.client)
		self.assertIsNone(info["id"])
		self.assertIsNone(info["username"])

	def test_check_webhook_matching_url_and_allowed_updates(self):
		self.api.queue("getWebhookInfo", _hook(pending_update_count=3))
		info = check_webhook(self.client, EXPECTED_URL)
		self.assertTrue(info["url_matches"])
		self.assertEqual(info["pending_update_count"], 3)
		self.assertTrue(info["allowed_updates_present"])
		self.assertTrue(info["allowed_updates_ok"])
		self.assertIsNone(info["last_error_date"])
		self.assertEqual(info["last_error_message"], "")

	def test_check_webhook_mismatched_url_and_missing_allowed_updates(self):
		self.api.queue("getWebhookInfo", _hook(url="https://other.test/hook", allowed_updates=None))
		info = check_webhook(self.client, EXPECTED_URL)
		self.assertFalse(info["url_matches"])
		self.assertFalse(info["allowed_updates_present"])
		self.assertFalse(info["allowed_updates_ok"])
		self.assertIsNone(info["allowed_updates"])

	def test_check_webhook_partial_allowed_updates_is_not_ok(self):
		self.api.queue("getWebhookInfo", _hook(allowed_updates=["message"]))
		info = check_webhook(self.client, EXPECTED_URL)
		self.assertTrue(info["allowed_updates_present"])
		self.assertFalse(info["allowed_updates_ok"])

	def test_check_webhook_reports_last_error(self):
		self.api.queue(
			"getWebhookInfo",
			_hook(last_error_date=1767225600, last_error_message="Wrong response from the webhook: 500 Internal"),
		)
		info = check_webhook(self.client, EXPECTED_URL)
		self.assertEqual(info["last_error_date"], 1767225600)
		self.assertIn("500", info["last_error_message"])

	def test_readiness_all_green(self):
		self.api.queue("getMe", _me())
		self.api.queue("getWebhookInfo", _hook())
		checks = readiness(self.client, EXPECTED_URL)
		self.assertTrue(all(c["ok"] for c in checks), checks)
		self.assertEqual(
			[c["id"] for c in checks],
			["bot_reachable", "webhook_url", "webhook_error", "webhook_pending", "webhook_allowed_updates", "bot_identity"],
		)
		for check in checks:
			self.assertEqual(set(check), {"id", "label", "ok", "hint"})
			self.assertEqual(check["hint"], "")

	def test_readiness_flags_url_error_backlog_and_allowed_updates(self):
		self.api.queue("getMe", _me())
		self.api.queue(
			"getWebhookInfo",
			_hook(
				url="https://stale.test/hook",
				pending_update_count=500,
				last_error_date=1767225600,
				last_error_message="Connection timed out",
				allowed_updates=["message"],
			),
		)
		by_id = {c["id"]: c for c in readiness(self.client, EXPECTED_URL)}
		self.assertFalse(by_id["webhook_url"]["ok"])
		self.assertIn("webhook setup", by_id["webhook_url"]["hint"])
		self.assertFalse(by_id["webhook_error"]["ok"])
		self.assertIn("Connection timed out", by_id["webhook_error"]["hint"])
		self.assertFalse(by_id["webhook_pending"]["ok"])
		self.assertIn("500", by_id["webhook_pending"]["hint"])
		self.assertFalse(by_id["webhook_allowed_updates"]["ok"])
		self.assertTrue(by_id["bot_reachable"]["ok"])

	def test_readiness_reports_getme_failure_without_raising(self):
		self.api.queue("getMe", FakeBotApi.error("Unauthorized", 401))
		self.api.queue("getWebhookInfo", _hook())
		checks = readiness(self.client, EXPECTED_URL)
		by_id = {c["id"]: c for c in checks}
		self.assertFalse(by_id["bot_reachable"]["ok"])
		self.assertIn("Unauthorized", by_id["bot_reachable"]["hint"])
		self.assertTrue(by_id["webhook_url"]["ok"])
		self.assertNotIn("bot_identity", by_id)

	def test_readiness_reports_webhook_info_failure_and_stops(self):
		self.api.queue("getMe", _me())
		self.api.queue("getWebhookInfo", FakeBotApi.error("Too Many Requests: retry later", 429, retry_after=30))
		checks = readiness(self.client, EXPECTED_URL)
		self.assertEqual([c["id"] for c in checks], ["bot_reachable", "webhook_info"])
		self.assertFalse(checks[1]["ok"])
		self.assertIn("Too Many Requests", checks[1]["hint"])

	def test_health_checks_never_call_mutating_webhook_methods(self):
		self.api.queue("getMe", _me())
		self.api.queue("getWebhookInfo", _hook())
		readiness(self.client, EXPECTED_URL)
		methods = {c["method"] for c in self.api.calls}
		self.assertEqual(methods, {"getMe", "getWebhookInfo"})
		self.assertNotIn("setWebhook", methods)
		self.assertNotIn("deleteWebhook", methods)

	def test_readiness_output_never_contains_the_token(self):
		self.api.queue("getMe", FakeBotApi.error(f"bad token {TOKEN}", 401))
		self.api.queue("getWebhookInfo", _hook())
		rendered = repr(readiness(self.client, EXPECTED_URL))
		self.assertNotIn(TOKEN, rendered)
		self.assertNotIn(TOKEN.split(":", 1)[1], rendered)
