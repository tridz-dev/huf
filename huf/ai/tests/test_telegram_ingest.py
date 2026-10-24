"""Telegram inbound hooks: classification, block/unblock, callbacks, reactions, /start, media."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import GatewayInboundRequest, provider_hooks
from huf.ai.gateway_adapters import telegram_ingest as ing
from huf.ai.gateway_adapters.telegram import WEBHOOK_SECRET_HEADER, TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES
from huf.ai.gateway_adapters.telegram_inbound import parse_update
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, load_fixture

GW = SimpleNamespace(name="gw1", provider="Telegram", mention_required=0)


def adapter():
	return TelegramGatewayAdapter({"token": TOKEN, "webhook_secret": SECRET}, download_attachments=False)


def req(payload):
	return GatewayInboundRequest(json.dumps(payload).encode(), headers={WEBHOOK_SECRET_HEADER: SECRET})


def run(payload, ad=None):
	"""Run handle_update with ingest/touch patched; returns (result, ingest mock)."""
	with (
		mock.patch("huf.ai.gateway_service.ingest_gateway_event", return_value={"event_name": "E1"}) as ing_m,
		mock.patch("huf.ai.gateway_webhook.touch_last_event"),
	):
		return ing.handle_update(GW, ad or adapter(), req(payload)), ing_m


class TestParsing(unittest.TestCase):
	def test_new_fields(self):
		p = parse_update(load_fixture("message_from_bot_thread"))
		self.assertTrue(p.is_bot)
		self.assertEqual(p.message_thread_id, "5")
		b = parse_update(load_fixture("business_message"))
		self.assertEqual((b.kind, b.business_connection_id), ("business_message", "bc-1"))
		self.assertFalse(b.is_bot)

	def test_allowed_updates(self):
		for name in (
			"message",
			"edited_message",
			"callback_query",
			"inline_query",
			"chosen_inline_result",
			"chat_join_request",
			"chat_member",
			"my_chat_member",
			"message_reaction",
			"channel_post",
			"business_connection",
			"business_message",
			"edited_business_message",
			"deleted_business_messages",
		):
			self.assertIn(name, ALLOWED_UPDATES)

	def test_classify(self):
		cases = {
			"message_text": "message",
			"callback_query": "callback",
			"message_reaction_added": "reaction",
			"my_chat_member_blocked": "membership",
			"business_message": "business",
			"unsupported_update": "other",
		}
		for name, want in cases.items():
			with self.subTest(name):
				self.assertEqual(ing.classify(parse_update(load_fixture(name))), want)


class TestHandleUpdate(unittest.TestCase):
	def test_text_ingested_with_meta(self):
		result, m = run(load_fixture("message_text"))
		self.assertEqual(result["event_name"], "E1")
		self.assertEqual(m.call_args.kwargs["raw_payload"]["telegram_meta"]["chat_type"], "private")

	def test_thread_and_bot_in_meta(self):
		_, m = run(load_fixture("message_from_bot_thread"))
		meta = m.call_args.kwargs["raw_payload"]["telegram_meta"]
		self.assertEqual((meta["message_thread_id"], meta["is_bot"]), ("5", True))

	def test_business_and_membership_acked_no_ingest(self):
		for name in ("business_message", "unsupported_update", "message_reaction_count"):
			with self.subTest(name):
				result, m = run(load_fixture(name))
				self.assertTrue(result["success"])
				m.assert_not_called()

	def test_reaction_ingested_as_reaction_kind(self):
		_, m = run(load_fixture("message_reaction_added"))
		self.assertEqual(m.call_args.args[2]["kind"], "reaction")  # context -> record-only, no agent run

	def test_tampered_callback_dropped(self):
		result, m = run(load_fixture("callback_query"))  # unsigned data
		self.assertEqual(result["ignored"], "callback_query")
		m.assert_not_called()

	def test_signed_callback_ingested_with_query_id(self):
		ad = adapter()
		payload = load_fixture("callback_query")
		payload["callback_query"]["data"] = ad.sign_callback_data("approve:42", "111")
		with mock.patch("huf.ai.gateway_adapters.telegram_buttons.time.time", return_value=1760000100.0):
			_, m = run(payload, ad)
		self.assertEqual(m.call_args.args[2]["message_text"], "approve:42")
		meta = m.call_args.kwargs["raw_payload"]["telegram_meta"]
		self.assertEqual((meta["callback_query_id"], meta["callback_data"]), ("cbq-1", "approve:42"))

	def test_blocked_marks_known_sender_unsendable(self):
		with (
			mock.patch("huf.ai.gateway_service._sender_is_known", return_value=True),
			mock.patch("huf.ai.gateway_service._record_opt_out") as out,
		):
			result, m = run(load_fixture("my_chat_member_blocked"))
		out.assert_called_once()
		self.assertEqual(result["ignored"], "bot_blocked")
		m.assert_not_called()

	def test_blocked_unknown_sender_stores_nothing(self):
		with (
			mock.patch("huf.ai.gateway_service._sender_is_known", return_value=False),
			mock.patch("huf.ai.gateway_service._record_opt_out") as out,
		):
			run(load_fixture("my_chat_member_blocked"))
		out.assert_not_called()

	def test_unblocked_restores(self):
		payload = load_fixture("my_chat_member_unblocked")
		with mock.patch("huf.ai.gateway_service._record_opt_in") as inn:
			result, _ = run(payload)
		inn.assert_called_once()
		self.assertEqual(result["ignored"], "bot_unblocked")

	def test_start_payload_reaches_event(self):
		_, m = run(load_fixture("message_start_deep_link"))
		self.assertEqual(m.call_args.kwargs["raw_payload"]["telegram_meta"]["start_payload"], "pair_ABC123")
		self.assertEqual(m.call_args.args[2]["message_text"], "/start pair_ABC123")

	def test_bad_body_falls_through(self):
		bad = GatewayInboundRequest(b"not json", headers={WEBHOOK_SECRET_HEADER: SECRET})
		self.assertIsNone(ing.handle_update(GW, adapter(), bad))


class TestHooks(unittest.TestCase):
	def test_registered(self):
		for name in (
			"ingest_update",
			"inbound_kind",
			"media_save",
			"typing",
			"mark_read_typing",
			"extra_event_fields",
		):
			self.assertIsNotNone(provider_hooks.get("Telegram", name), name)
		self.assertFalse(provider_hooks.get("Telegram", "consent_required")())

	def test_inbound_kind(self):
		ev = lambda n: SimpleNamespace(get=lambda k, d=None: load_fixture(n), raw_payload=load_fixture(n))
		self.assertEqual(ing.inbound_media_type(ev("photo")), "image")
		self.assertEqual(ing.inbound_media_type(ev("voice")), "audio")
		self.assertIsNone(ing.inbound_media_type(ev("message_text")))

	def test_extra_fields(self):
		raw = load_fixture("message_text")
		raw["telegram_meta"] = {"chat_type": "private", "message_thread_id": "5"}
		ev = SimpleNamespace(raw_payload=raw, conversation_id="111", get=lambda k, d=None: raw)
		out = ing.extra_fields(ev, GW, "111")
		self.assertEqual((out["telegram_chat_id"], out["message_thread_id"]), ("111", "5"))

	def test_typing_private_calls_send_typing(self):
		raw = {"telegram_meta": {"chat_type": "private"}}
		ev = SimpleNamespace(raw_payload=raw, conversation_id="111", get=lambda k, d=None: raw)
		fake = mock.Mock()
		with mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=fake):
			self.assertTrue(ing.send_typing_for_event(ev, GW))
		fake.sender.send_chat_action.assert_called_once_with("111", "typing", thread_id=None)

	def test_typing_group_unaddressed_skipped(self):
		raw = {"telegram_meta": {"chat_type": "supergroup"}, "message": {"text": "hi"}}
		ev = SimpleNamespace(raw_payload=raw, conversation_id="-1", get=lambda k, d=None: raw)
		gw = SimpleNamespace(get=lambda k: 1)
		self.assertFalse(ing.send_typing_for_event(ev, gw))

	def test_oversize_media_skipped_without_failing(self):
		raw = load_fixture("photo")
		raw["message"]["photo"][-1]["file_size"] = 25 * 1024 * 1024
		ev = SimpleNamespace(raw_payload=raw, name="EV", get=lambda k, d=None: raw)
		with mock.patch("huf.ai.gateway_webhook.get_gateway_adapter") as g:
			self.assertEqual(ing.save_media(ev, GW), [])
		g.assert_not_called()


if __name__ == "__main__":
	unittest.main()


class TestFirstDeliveryFailOpenWarns(unittest.TestCase):
	def test_warns_once(self):
		from unittest.mock import patch

		ing._DEDUP_WARNED = False
		with (
			patch.object(ing.frappe, "cache", side_effect=RuntimeError("redis down")),
			patch.object(ing.frappe, "logger") as lg,
		):
			self.assertTrue(ing._first_delivery("GW", 1))
			self.assertTrue(ing._first_delivery("GW", 2))
		self.assertEqual(lg.return_value.warning.call_count, 1)


class TestPoisonUpdate(unittest.TestCase):
	"""A handler that always raises is retried a bounded number of times, then acked and logged."""

	def setUp(self):
		self.cache = {}
		self.patches = [
			mock.patch.object(ing, "_count_failure", side_effect=self._count),
			mock.patch.object(ing, "_clear_failures", side_effect=lambda g, u: self.cache.pop(u, None)),
			mock.patch.object(ing, "frappe"),
		]
		self.mocks = [p.start() for p in self.patches]
		self.log_error = self.mocks[2].log_error
		self.addCleanup(lambda: [p.stop() for p in self.patches])

	def _count(self, gateway_name, update_id):
		self.cache[update_id] = self.cache.get(update_id, 0) + 1
		return self.cache[update_id]

	def _run(self):
		with mock.patch.object(ing, "_dispatch", side_effect=RuntimeError("boom")):
			return ing.handle_update(GW, adapter(), req(load_fixture("message_text")))

	def test_raises_until_limit_then_acks_and_logs(self):
		for _ in range(ing.MAX_UPDATE_FAILURES - 1):
			with self.assertRaises(RuntimeError):
				self._run()
		self.log_error.assert_not_called()
		result = self._run()
		self.assertTrue(result["success"])
		self.assertIn("dropped", result["note"])
		self.log_error.assert_called_once()
		self.assertEqual(self.cache, {})  # counter cleared once dropped
