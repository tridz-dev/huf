"""Telegram reply pipeline: split, formatting fallback, retry_after, blocked, partial resume, reply_parameters."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import provider_hooks, telegram_messages
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.gateway_adapters.telegram_client import TelegramApiError
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

CHAT = 555


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)


class FakeEvent:
	def __init__(self, **kw):
		self.name = "EVT-1"
		self.sender_id = "42"
		self.conversation_id = str(CHAT)
		self.thread_id = "77"
		self.reply_message_id = ""
		self.agent_run = "RUN-1"
		self.raw_payload = {}
		self.values = {}
		self.__dict__.update(kw)

	def db_set(self, a, b=None):
		self.values.update(a if isinstance(a, dict) else {a: b})
		for k, v in self.values.items():
			setattr(self, k, v)


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET}, http_post=self.api.http_post,
			http_get=self.api.http_get, download_attachments=False,
		)
		self.sender = tp.build_sender(self.adapter)

	def send(self, parts, **kw):
		return tp.send_parts_with(self.sender, CHAT, parts, **kw)


class TestSend(Base):
	def test_split_4096(self):
		parts = tp.make_parts("a" * 5000)
		self.assertEqual([len(p) for p in parts], [4096, 904])
		self.send(parts)
		self.assertEqual(len(self.api.of("sendMessage")), 2)

	def test_html_format_and_reply_parameters_first_part_only(self):
		self.send(["**bold**", "second"], reply_to="77", thread_id="9")
		first, second = [c["payload"] for c in self.api.of("sendMessage")]
		self.assertEqual(first["parse_mode"], "HTML")
		self.assertIn("<b>bold</b>", first["text"])
		self.assertEqual(first["reply_parameters"]["message_id"], 77)
		self.assertNotIn("reply_parameters", second)
		self.assertEqual(first["message_thread_id"], 9)

	def test_parse_error_falls_back_to_plain_once(self):
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: can't parse entities", 400))
		self.send(["**hi**"])
		calls = self.api.of("sendMessage")
		self.assertEqual(len(calls), 2)
		self.assertNotIn("parse_mode", calls[1]["payload"])
		self.assertEqual(calls[1]["payload"]["text"], "hi")

	def test_markup_on_last_part_only(self):
		self.send(["a", "b"], markup={"inline_keyboard": []})
		c = self.api.of("sendMessage")
		self.assertNotIn("reply_markup", c[0]["payload"])
		self.assertIn("reply_markup", c[1]["payload"])

	def test_partial_send_resume(self):
		self.api.queue("sendMessage", None)  # placeholder consumed below
		self.api._queues["sendMessage"] = [
			{"ok": True, "result": {"message_id": 1}},
			FakeBotApi.error("Too Many Requests: retry after 7", 429, retry_after=7),
		]
		with self.assertRaises(tp.TelegramPartsError) as cm:
			self.send(["p1", "p2", "p3"], reply_to="77")
		err = cm.exception
		self.assertEqual(err.sent_ids, [1])
		self.assertEqual(err.remaining, ["p2", "p3"])
		cls = tp.classify(err)
		self.assertTrue(cls["retryable"])
		self.assertEqual(cls["delay"], 8.0)
		self.assertEqual(tp.backoff_seconds(cls, 1), 8.0)
		before = len(self.api.of("sendMessage"))
		self.send(err.remaining)  # resume sends only the rest, no quote
		sent = [c["payload"]["text"] for c in self.api.of("sendMessage")[before:]]
		self.assertEqual(sent, ["p2", "p3"])
		self.assertNotIn("reply_parameters", self.api.of("sendMessage")[before]["payload"])

	def test_on_sent_records_ids(self):
		cache = FakeCache()
		self.send(["a", "b"], on_sent=lambda ids: telegram_messages.record_sent("GW", CHAT, "E", ids, cache=cache))
		self.assertEqual(telegram_messages.sent_for_event("GW", "E", cache=cache), [101, 102])
		self.assertEqual(telegram_messages.last_in_chat("GW", CHAT, cache=cache), 102)


class TestClassify(unittest.TestCase):
	def test_blocked_not_retryable(self):
		c = tp.classify(TelegramApiError("sendMessage", "Forbidden: bot was blocked by the user", error_code=403))
		self.assertTrue(c["blocked"])
		self.assertFalse(c["retryable"])

	def test_chat_not_found_not_retryable(self):
		c = tp.classify(TelegramApiError("sendMessage", "Bad Request: chat not found", error_code=400))
		self.assertFalse(c["retryable"])
		self.assertEqual(c["code"], "chat_not_found")

	def test_5xx_retryable_backoff(self):
		c = tp.classify(TelegramApiError("sendMessage", "Internal", error_code=502))
		self.assertTrue(c["retryable"])
		self.assertEqual(tp.backoff_seconds(c, 2), 10.0)

	def test_parse_error_not_retryable(self):
		c = tp.classify(TelegramApiError("sendMessage", "can't parse entities", error_code=400))
		self.assertFalse(c["retryable"])


class TestFailureHandling(Base):
	def setUp(self):
		super().setUp()
		self.svc = mock.MagicMock()
		self.svc._reply_max_attempts.return_value = 4
		self.svc._redact_error_text.side_effect = lambda s: s
		self.event = FakeEvent()
		self.gw = SimpleNamespace(name="GW", provider="Telegram")
		p = mock.patch.object(tp, "_svc", return_value=self.svc)
		p.start()
		self.addCleanup(p.stop)
		fr = mock.patch("frappe.enqueue")
		self.enqueue = fr.start()
		self.addCleanup(fr.stop)
		for target in ("frappe.log_error", "frappe.logger"):
			m = mock.patch(target)
			m.start()
			self.addCleanup(m.stop)
		m = mock.patch("huf.ai.gateway_webhook._set_gateway_error")
		m.start()
		self.addCleanup(m.stop)

	def test_flood_schedules_retry_with_remaining_and_delay(self):
		exc = tp.TelegramPartsError(
			TelegramApiError("sendMessage", "Too Many Requests", error_code=429, retry_after=3), [9], ["p2"])
		out = tp.handle_failure(self.event, self.gw, exc, ["p1", "p2"], 1)
		self.assertEqual(out["reply_status"], "retrying")
		self.assertEqual(out["retry_in_seconds"], 4.0)
		kw = self.enqueue.call_args.kwargs
		self.assertEqual(kw["parts_remaining"], ["p2"])
		self.assertEqual(kw["attempt"], 2)
		self.svc._record_reply_sent.assert_called_once_with(self.event, 9)

	def test_blocked_dead_letters_and_marks_unsendable(self):
		exc = tp.TelegramPartsError(
			TelegramApiError("sendMessage", "Forbidden: bot was blocked by the user", error_code=403), [], ["p1"])
		out = tp.handle_failure(self.event, self.gw, exc, ["p1"], 1)
		self.assertEqual(out["status"], "Failed")
		self.assertEqual(out["error_code"], "blocked")
		self.enqueue.assert_not_called()
		self.svc._record_opt_out.assert_called_once_with(self.gw, "42")

	def test_gives_up_after_max_attempts(self):
		exc = TelegramApiError("sendMessage", "Bad Gateway", error_code=502)
		out = tp.handle_failure(self.event, self.gw, exc, ["p1"], 4)
		self.assertEqual(out["status"], "Failed")
		self.enqueue.assert_not_called()
		self.assertIn("gave up", self.event.values["delivery_error"])

	def test_chat_not_found_fails_without_retry(self):
		exc = TelegramApiError("sendMessage", "Bad Request: chat not found", error_code=400)
		out = tp.handle_failure(self.event, self.gw, exc, ["p1"], 1)
		self.assertEqual(out["status"], "Failed")
		self.enqueue.assert_not_called()
		self.svc._record_opt_out.assert_not_called()


class TestMisc(Base):
	def test_reply_target(self):
		ev = FakeEvent(raw_payload={"message": {"message_thread_id": 12, "is_topic_message": True}})
		self.assertEqual(tp.reply_target(ev), ("12", "77"))
		self.assertEqual(tp.reply_target(FakeEvent()), (None, "77"))

	def test_typing_best_effort(self):
		with mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=self.adapter), \
				mock.patch("huf.ai.gateway_webhook.event_contact_name", return_value=""):
			self.assertTrue(tp.send_typing(SimpleNamespace(provider="Telegram", name="G"), FakeEvent()))
			self.assertEqual(self.api.last("sendChatAction")["payload"]["action"], "typing")
			self.api.queue("sendChatAction", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
			self.assertFalse(tp.send_typing(SimpleNamespace(provider="Telegram", name="G"), FakeEvent()))
		with mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", side_effect=RuntimeError("x")):
			self.assertFalse(tp.send_typing(SimpleNamespace(provider="Telegram", name="G"), FakeEvent()))

	def test_hooks_registered(self):
		for name in ("send_reply", "send_parts", "attempt_reply_parts", "send_errors", "error_text",
				"reply_target", "recover_reply_parts"):
			self.assertIsNotNone(provider_hooks.get("Telegram", name), name)
		self.assertEqual(provider_hooks.call("Telegram", "recover_reply_parts", "hi"), ["hi"])
		self.assertEqual(provider_hooks.call("Telegram", "recover_reply_parts", "   "), [])
		exc = tp.TelegramPartsError(TelegramApiError("m", "Forbidden: bot was blocked by the user", error_code=403), [], [])
		self.assertIn("blocked", provider_hooks.call("Telegram", "error_text", exc))


if __name__ == "__main__":
	unittest.main()


class TestSpokenText(unittest.TestCase):
	def test_media_and_button_fences_are_not_spoken(self):
		from huf.ai.gateway_adapters import telegram_pipeline as tp

		text = (
			"Here is your report.\n```telegram-media\n"
			'{"items":[{"type":"photo","source":"url","value":"https://example.com/a.png"}]}\n```\n'
			'```telegram-buttons\n{"rows":[[{"text":"Ok","url":"https://example.com"}]]}\n```\nBye.'
		)
		spoken = tp.spoken_text(text)
		self.assertIn("Here is your report.", spoken)
		self.assertIn("Bye.", spoken)
		self.assertNotIn("telegram-media", spoken)
		self.assertNotIn("telegram-buttons", spoken)
		self.assertNotIn("example.com", spoken)
