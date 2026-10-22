"""Telegram guest chat mode: parse, policy, rate limit, answerGuestQuery payload."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.gateway_adapters import telegram_guest as tg
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_inbound import parse_update
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi, load_fixture


class Env:
	def __init__(self):
		self.api = FakeBotApi()
		self.client = TelegramBotClient(TOKEN, http_post=self.api.http_post, http_get=self.api.http_get)
		self.adapter = SimpleNamespace(client=self.client)
		self.counts: dict = {}
		self.claims: set = set()

	def bump(self, key, ttl):
		self.counts[key] = self.counts.get(key, 0) + 1
		return self.counts[key]

	def claim(self, key, ttl):
		if key in self.claims:
			return False
		self.claims.add(key)
		return True


class TestGuest(unittest.TestCase):
	def setUp(self):
		self.env = Env()
		self.ingest_calls = []

		def fake_ingest(name, pid, context, **kw):
			self.ingest_calls.append((name, pid, context, kw))
			return {"duplicate": False, "event_name": "E1"}

		patches = [
			patch.object(tg, "_bump", self.env.bump),
			patch.object(tg, "_claim_once", self.env.claim),
			patch("huf.ai.gateway_service.ingest_gateway_event", fake_ingest),
			patch("huf.ai.gateway_webhook.touch_last_event", lambda g: None),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def _run(self, fixture="guest_message", policy="Open"):
		update = load_fixture(fixture)
		gw = SimpleNamespace(name="GW1", direct_policy=policy)
		parsed = parse_update(update)
		return tg.handle_guest(gw, self.env.adapter, parsed, None)

	def test_parse_ok_and_tampered(self):
		g = tg.parse_guest_update(load_fixture("guest_message"))
		self.assertEqual((g["guest_query_id"], g["guest_id"], g["chat_id"]), ("gq-abc123", "777", "-1009988"))
		self.assertIsNone(tg.parse_guest_update(load_fixture("guest_message_tampered")))

	def test_tampered_dropped_without_reply_or_ingest(self):
		res = self._run("guest_message_tampered")
		self.assertEqual(res["ignored"], "guest_message")
		self.assertEqual(self.env.api.calls, [])
		self.assertEqual(self.ingest_calls, [])

	def test_non_guest_update_falls_through(self):
		self.assertIsNone(self._run("callback_query"))

	def test_open_policy_ingests_with_guest_flag(self):
		res = self._run()
		self.assertTrue(res["success"])
		name, pid, ctx, kw = self.ingest_calls[0]
		self.assertEqual((name, pid), ("GW1", "2001"))
		self.assertEqual(ctx["conversation_id"], "guest:-1009988")
		self.assertFalse(ctx["is_room"])
		meta = kw["raw_payload"]["telegram_meta"]
		self.assertTrue(meta["guest"])
		self.assertEqual(meta["guest_query_id"], "gq-abc123")
		self.assertTrue(tg.is_guest_event(kw["raw_payload"]))
		self.assertEqual(tg.guest_query_id_of(kw["raw_payload"]), "gq-abc123")
		self.assertEqual(self.env.api.calls, [])

	def test_non_open_policy_denies_once_no_ingest(self):
		for policy in ("Allow list", "Pairing", "Disabled"):
			self.env.claims.clear()
			self.env.api.calls.clear()
			self._run(policy=policy)
			self.assertEqual(len(self.env.api.of("answerGuestQuery")), 1)
			self.assertIn("owner", self.env.api.last()["payload"]["result"]["input_message_content"]["message_text"])
		self.assertEqual(self.ingest_calls, [])
		# second message from same guest: no further reply
		self.env.api.calls.clear()
		self._run(policy="Pairing")
		self.assertEqual(self.env.api.calls, [])

	def test_rate_limit_per_guest(self):
		for _ in range(tg.PER_GUEST_LIMIT):
			self._run()
		self.assertEqual(len(self.ingest_calls), tg.PER_GUEST_LIMIT)
		res = self._run()
		self.assertEqual(res["note"], "rate limited")
		self.assertEqual(len(self.ingest_calls), tg.PER_GUEST_LIMIT)
		self.assertEqual(len(self.env.api.of("answerGuestQuery")), 1)
		self._run()  # still limited, no second notice
		self.assertEqual(len(self.env.api.of("answerGuestQuery")), 1)

	def test_rate_limit_per_chat(self):
		self.assertFalse(tg.rate_limited("GW1", "1", "C"))
		hit = False
		for i in range(2, tg.PER_CHAT_LIMIT + 3):
			hit = tg.rate_limited("GW1", str(i), "C")
		self.assertTrue(hit)

	def test_answer_payload_matches_fixture(self):
		self.assertEqual(tg.answer_payload("gq-abc123", "4"), load_fixture("answer_guest_query"))
		reply = tg.reply_for_guest(self.env.client, "gq-abc123", "4")
		self.assertTrue(reply)
		self.assertEqual(self.env.api.last("answerGuestQuery")["payload"]["guest_query_id"], "gq-abc123")

	def test_reply_error_is_swallowed_and_token_free(self):
		self.env.api.queue("answerGuestQuery", FakeBotApi.error("Bad Request: query expired", 400))
		self.assertIsNone(tg.reply_for_guest(self.env.client, "gq-1", "x"))
		self.assertIsNone(tg.reply_for_guest(self.env.client, "", "x"))

	def test_hooks_registered(self):
		import huf.ai.gateway_adapters.telegram_guest_hooks  # noqa: F401

		self.assertIn("guest_message", ing._UPDATE_HANDLERS)
		self.assertIn("unsupported", ing._UPDATE_HANDLERS)
