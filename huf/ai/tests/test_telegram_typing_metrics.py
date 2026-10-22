# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Telegram typing counters in the frappe cache: success, failure, keepalive, 24h window, health shape."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import telegram_ingest as ing, telegram_typing_metrics as tm
from huf.ai.gateway_adapters.telegram_client import TelegramApiError
from huf.ai.tests.test_telegram_typing import FakeCache, event, gateway


class MetricsCase(unittest.TestCase):
	def setUp(self):
		self.cache = FakeCache()
		self.sender = mock.Mock()
		patchers = [
			mock.patch("frappe.cache", return_value=self.cache),
			mock.patch(
				"huf.ai.gateway_webhook.get_gateway_adapter", return_value=SimpleNamespace(sender=self.sender)
			),
			mock.patch.object(ing, "frappe"),
		]
		for p in patchers:
			p.start()
			self.addCleanup(p.stop)

	def read(self):
		return tm.read("TG-1")


class TestSuccessAndFailure(MetricsCase):
	def test_success_counts_and_records_last_sent(self):
		self.assertTrue(ing.send_typing_for_event(event(), gateway(name="TG-1")))
		data = self.read()
		self.assertEqual(data["sent_count_24h"], 1)
		self.assertTrue(data["last_sent_at"])
		self.assertIsNone(data["last_error"])
		self.assertEqual(self.cache.store["huf_tg_typing:TG-1"]["last_chat"], "111")

	def test_failure_stores_type_name_only_never_message_text(self):
		secret_text = "bot 123:ABC-secret rejected"
		self.sender.send_chat_action.side_effect = TelegramApiError("sendChatAction", secret_text, error_code=500)
		self.assertFalse(ing.send_typing_for_event(event(), gateway(name="TG-1")))
		data = self.read()
		self.assertEqual(data["sent_count_24h"], 0)
		self.assertEqual(data["last_error"], "api_500")
		self.assertNotIn("secret", repr(self.cache.store))

	def test_unexpected_exception_records_its_type_name(self):
		self.sender.send_chat_action.side_effect = RuntimeError("boom")
		ing.send_typing_for_event(event(), gateway(name="TG-1"))
		self.assertEqual(self.read()["last_error"], "RuntimeError")


class TestKeepaliveTick(MetricsCase):
	def test_tick_counts_success_and_failure(self):
		captured = {}

		def fake_start(key, send, skip=None, **kw):
			captured["send"] = send
			return True

		with mock.patch("huf.ai.gateway_adapters.telegram_typing_keepalive.start", side_effect=fake_start):
			ing.send_typing_for_event(event(), gateway(name="TG-1"))
		captured["send"]()
		self.assertEqual(self.read()["keepalive_ticks"], 1)
		self.sender.send_chat_action.side_effect = TelegramApiError("sendChatAction", "x", error_code=429)
		with self.assertRaises(TelegramApiError):
			captured["send"]()
		self.assertEqual(self.read()["keepalive_ticks"], 1)
		self.assertEqual(self.read()["last_error"], "flood_control")


class TestWindowAndSafety(MetricsCase):
	def test_24h_window_resets_after_a_day(self):
		tm.record_sent("TG-1", "111")
		tm.record_sent("TG-1", "111")
		self.assertEqual(self.read()["sent_count_24h"], 2)
		self.cache.store["huf_tg_typing:TG-1"]["window_start"] -= tm.WINDOW_SECONDS + 1
		self.assertEqual(self.read()["sent_count_24h"], 0)
		tm.record_sent("TG-1", "111")
		self.assertEqual(self.read()["sent_count_24h"], 1)

	def test_cache_outage_never_raises(self):
		broken = mock.Mock()
		broken.get_value.side_effect = RuntimeError("redis down")
		broken.set_value.side_effect = RuntimeError("redis down")
		with mock.patch("frappe.cache", return_value=broken):
			tm.record_sent("TG-1", "111")
			tm.record_error("TG-1", "blocked")
			tm.record_keepalive_tick("TG-1")
			self.assertEqual(tm.read("TG-1")["sent_count_24h"], 0)

	def test_read_exposes_no_chat_ids(self):
		tm.record_sent("TG-1", "555")
		self.assertNotIn("last_chat", self.read())


class TestHealthBlock(MetricsCase):
	def test_block_is_none_when_typing_off(self):
		from huf.ai.telegram_management import build_typing

		self.assertIsNone(build_typing({"name": "TG-1", "typing_indicator": 0}))

	def test_block_shape_when_on(self):
		from huf.ai.telegram_management import build_typing

		tm.record_sent("TG-1", "111")
		block = build_typing({"name": "TG-1", "typing_indicator": 1})
		self.assertEqual(
			set(block),
			{"last_sent_at", "sent_count_24h", "last_error", "last_error_at", "keepalive_ticks"},
		)
		self.assertEqual(block["sent_count_24h"], 1)
		self.assertNotIn("token", repr(block).lower())
