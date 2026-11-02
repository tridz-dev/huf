# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram bot health checks against the in-memory fake Bot API (no network, no Frappe)."""

from __future__ import annotations

import unittest

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramBotClient
from huf.ai.gateway_adapters.telegram_health import (
	capability_checks,
	check_bot,
	check_menu_button,
	check_webhook,
	readiness,
)
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
		self.client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None
		)

	def test_check_bot_reports_identity_and_capability_flags(self):
		self.api.queue(
			"getMe", _me(can_join_groups=True, can_connect_to_business=True, has_topics_enabled=False)
		)
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
			_hook(
				last_error_date=1767225600, last_error_message="Wrong response from the webhook: 500 Internal"
			),
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
			[
				"bot_reachable",
				"webhook_url",
				"webhook_error",
				"webhook_pending",
				"webhook_allowed_updates",
				"bot_identity",
			],
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
		self.assertIn("Connect to Telegram", by_id["webhook_url"]["hint"])
		self.assertFalse(by_id["webhook_error"]["ok"])
		self.assertIn("Connection timed out", by_id["webhook_error"]["hint"])
		self.assertFalse(by_id["webhook_pending"]["ok"])
		self.assertIn("500", by_id["webhook_pending"]["hint"])
		self.assertFalse(by_id["webhook_allowed_updates"]["ok"])
		self.assertIn("chat_join_request", by_id["webhook_allowed_updates"]["hint"])
		self.assertNotIn("types: message,", by_id["webhook_allowed_updates"]["hint"])
		self.assertIn("Last error", by_id["webhook_pending"]["hint"])
		self.assertIn("Connection timed out", by_id["webhook_pending"]["hint"])
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
		self.api.queue(
			"getWebhookInfo", FakeBotApi.error("Too Many Requests: retry later", 429, retry_after=30)
		)
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


ALL_FEATURES = {k: True for k in ("inline", "groups", "group_open", "business", "guest", "join_requests")}
NO_FEATURES = {k: False for k in ALL_FEATURES}
# row id -> (bot flag, feature key)
ROWS = {
	"inline_mode": ("supports_inline_queries", "inline"),
	"group_privacy": ("can_read_all_group_messages", "group_open"),
	"join_groups": ("can_join_groups", "groups"),
	"business_mode": ("can_connect_to_business", "business"),
	"guest_mode": ("supports_guest_queries", "guest"),
	"join_requests": ("supports_join_request_queries", "join_requests"),
}


class TestCapabilityChecks(unittest.TestCase):
	def test_flag_by_feature_matrix(self):
		for row_id, (flag, feature) in ROWS.items():
			for flag_on in (True, False):
				for used in (True, False):
					with self.subTest(row=row_id, flag=flag_on, used=used):
						bot = {flag: flag_on}
						features = {**NO_FEATURES, feature: used}
						row = {r["id"]: r for r in capability_checks(bot, features)}[row_id]
						want = "off" if not used else ("pass" if flag_on else "warn")
						self.assertEqual(row["state"], want)
						self.assertEqual(row["level"], "warn")
						self.assertEqual(row["ok"], want != "warn")
						self.assertEqual(bool(row["hint"]), want == "warn")

	def test_hints_name_the_exact_fix(self):
		rows = {r["id"]: r for r in capability_checks({}, ALL_FEATURES)}
		self.assertIn("/setinline", rows["inline_mode"]["hint"])
		self.assertIn("/setprivacy", rows["group_privacy"]["hint"])
		self.assertIn("Disable", rows["group_privacy"]["hint"])
		self.assertIn("/setjoingroups", rows["join_groups"]["hint"])
		self.assertIn("Business Mode", rows["business_mode"]["hint"])
		self.assertIn("Premium", rows["business_mode"]["hint"])

	def test_no_rows_without_readable_bot(self):
		self.assertEqual(capability_checks(None, ALL_FEATURES), [])

	def test_mini_app_states(self):
		def state(bot, menu, host="huf.example.com"):
			return {r["id"]: r for r in capability_checks(bot, NO_FEATURES, menu, host)}["mini_app"]

		self.assertEqual(state({}, {"type": "commands", "url": ""})["state"], "off")
		self.assertEqual(state({}, None)["state"], "off")
		self.assertEqual(
			state({}, {"type": "web_app", "url": "https://huf.example.com/huf"})["state"], "pass"
		)
		bad = state({}, {"type": "web_app", "url": "https://other.example.com/x"})
		self.assertEqual(bad["state"], "warn")
		self.assertIn("other.example.com", bad["hint"])
		self.assertEqual(state({"has_main_web_app": True}, None)["state"], "pass")

	def test_check_bot_collects_new_flags(self):
		api = FakeBotApi()
		client = TelegramBotClient(
			TOKEN, http_post=api.http_post, http_get=api.http_get, sleep=lambda s: None
		)
		api.queue(
			"getMe",
			_me(supports_inline_queries=True, can_read_all_group_messages=True, has_main_web_app=True),
		)
		info = check_bot(client)
		self.assertTrue(info["supports_inline_queries"])
		self.assertTrue(info["can_read_all_group_messages"])
		self.assertTrue(info["has_main_web_app"])

	def test_check_menu_button(self):
		api = FakeBotApi()
		client = TelegramBotClient(
			TOKEN, http_post=api.http_post, http_get=api.http_get, sleep=lambda s: None
		)
		api.queue(
			"getChatMenuButton",
			{
				"ok": True,
				"result": {"type": "web_app", "text": "Open", "web_app": {"url": "https://a.test/x"}},
			},
		)
		self.assertEqual(check_menu_button(client), {"type": "web_app", "url": "https://a.test/x"})
