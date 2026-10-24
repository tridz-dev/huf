# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""End-to-end agent reply: ``_send_telegram_reply`` -> provider hooks -> pipeline -> fake Bot API.

Only the Frappe service layer (rate limit, opt-out, DB writes, enqueue) is replaced by mocks; every Bot API call
the reply makes is recorded by ``FakeBotApi`` and asserted in order. No network, no ffmpeg, no TTS provider.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import gateway_service
from huf.ai.whatsapp import send_file
from huf.ai.gateway_adapters import provider_hooks, telegram_hooks
from huf.ai.gateway_adapters import telegram_buttons as tb
from huf.ai.gateway_adapters import telegram_media_reply as mr
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters import telegram_voice as tv
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

CHAT = 555
VOICE_RAW = {
	"update_id": 1,
	"message": {
		"message_id": 77,
		"voice": {"file_id": "F1", "duration": 3},
		"chat": {"id": CHAT, "type": "private"},
	},
}
TEXT_RAW = {
	"update_id": 1,
	"message": {"message_id": 77, "text": "hi", "chat": {"id": CHAT, "type": "private"}},
}


class FakeCache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


class FakeEvent:
	def __init__(self, raw=None, **kw):
		self.name = "EVT-1"
		self.sender_id = "42"
		self.conversation_id = str(CHAT)
		self.thread_id = "77"
		self.reply_message_id = ""
		self.reply_status = ""
		self.status = "Running"
		self.delivery_error = ""
		self.agent_run = "RUN-1"
		self.target_agent = "Agent A"
		self.raw_payload = TEXT_RAW if raw is None else raw
		self.values = {}
		self.__dict__.update(kw)

	def db_set(self, key, value=None, **_kw):
		values = key if isinstance(key, dict) else {key: value}
		self.values.update(values)
		self.__dict__.update(values)


def make_gateway(voice_mode=""):
	return SimpleNamespace(
		name="G1",
		provider="Telegram",
		voice_reply_mode=voice_mode,
		direct_policy="Open",
		retry_max_attempts=4,
	)


def block(kind, obj) -> str:
	return f"```{kind}\n" + json.dumps(obj) + "\n```"


def media(*items) -> str:
	return block("telegram-media", {"items": list(items)})


def buttons(obj) -> str:
	return block("telegram-buttons", obj)


def photo(value="P1", **kw):
	return {"type": "photo", "source": "file_id", "value": value, **kw}


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter(
			{"token": TOKEN, "webhook_secret": SECRET},
			http_post=self.api.http_post,
			http_get=self.api.http_get,
			download_attachments=False,
		)
		self.cache = FakeCache()
		self.svc = mock.MagicMock()
		self.svc._reply_max_attempts.return_value = 4
		self.svc._redact_error_text.side_effect = lambda text: text
		self.enqueue = self._patch_path("frappe.enqueue")
		self._patch_path("frappe.log_error")
		self._patch_path("frappe.logger")
		self._patch_path("huf.ai.gateway_webhook.touch_last_event")
		self._patch_path("huf.ai.gateway_webhook._set_gateway_error")
		self._patch_path("huf.ai.gateway_webhook.event_contact_name", return_value="")
		self._patch_path("huf.ai.gateway_webhook.get_gateway_adapter", return_value=self.adapter)
		self._patch_path("huf.ai.gateway_adapters.telegram_messages.record_sent")
		self._patch(frappe, "db", SimpleNamespace(get_value=lambda *a, **k: "retrying"))
		self._patch(tp, "_svc", return_value=self.svc)
		self._patch(mr, "_cache", return_value=self.cache)
		self._patch(tb, "_cache", return_value=self.cache)
		self._patch(gateway_service, "is_opted_out", return_value=False)
		self._patch(gateway_service, "_commit_unless_testing")
		self._patch(gateway_service, "_throttle_outbound_send")
		self._patch(gateway_service, "_outbound_rate_cap", return_value=0)
		self._patch(gateway_service, "_record_reply_sent", side_effect=self._record_reply_sent)
		self.svc._record_reply_sent.side_effect = self._record_reply_sent
		self.synth = self._patch(tv, "_synthesize", return_value=b"mp3-bytes")
		self.convert = self._patch(tv, "_convert", return_value=b"OggSOpus")
		self._patch(tv, "_adapter", return_value=self.adapter)
		self._patch(tv, "_claim", return_value=True)
		self._patch(tv, "_conversation", return_value="CONV-1")

	def _patch(self, target, attr, *args, **kw):
		p = mock.patch.object(target, attr, *args, **kw)
		m = p.start()
		self.addCleanup(p.stop)
		return m

	def _patch_path(self, path, **kw):
		p = mock.patch(path, **kw)
		m = p.start()
		self.addCleanup(p.stop)
		return m

	@staticmethod
	def _record_reply_sent(event, message_id):
		if message_id:
			event.db_set("reply_message_id", str(message_id))

	def reply(self, event, text, gateway=None):
		return gateway_service._send_telegram_reply(event, gateway or make_gateway(), "RUN-1", text)

	def methods(self):
		return [c["method"] for c in self.api.calls]

	def payloads(self, method):
		return [c["payload"] for c in self.api.of(method)]


class TestPlainReply(Base):
	def test_a_long_reply_split_at_4096_quotes_only_first_part(self):
		result = self.reply(FakeEvent(), "a" * 5000)
		self.assertEqual(self.methods(), ["sendMessage", "sendMessage"])
		first, second = self.payloads("sendMessage")
		self.assertEqual([len(first["text"]), len(second["text"])], [4096, 904])
		self.assertEqual(first["reply_parameters"]["message_id"], 77)
		self.assertNotIn("reply_parameters", second)
		self.assertNotIn("reply_markup", first)
		self.assertEqual(result["status"], "Succeeded")

	def test_h_html_parse_error_retries_once_as_plain_text(self):
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: can't parse entities: bad", 400))
		result = self.reply(FakeEvent(), "**hi**")
		first, fallback = self.payloads("sendMessage")
		self.assertEqual(first["parse_mode"], "HTML")
		self.assertIn("<b>hi</b>", first["text"])
		self.assertNotIn("parse_mode", fallback)
		self.assertEqual(fallback["text"], "hi")
		self.assertEqual(result["status"], "Succeeded")

	def test_i_forum_topic_reply_carries_message_thread_id(self):
		raw = {
			"update_id": 1,
			"message": {
				"message_id": 77,
				"message_thread_id": 12,
				"is_topic_message": True,
				"text": "hi",
				"chat": {"id": CHAT, "type": "supergroup"},
			},
		}
		self.reply(FakeEvent(raw=raw), "hello topic")
		(sent,) = self.payloads("sendMessage")
		self.assertEqual(sent["message_thread_id"], 12)
		self.assertEqual(sent["reply_parameters"]["message_id"], 77)

	def test_i_non_topic_supergroup_reply_has_no_thread(self):
		raw = {
			"update_id": 1,
			"message": {
				"message_id": 77,
				"message_thread_id": 12,
				"text": "hi",
				"chat": {"id": CHAT, "type": "supergroup"},
			},
		}
		self.reply(FakeEvent(raw=raw), "hello group")
		(sent,) = self.payloads("sendMessage")
		self.assertNotIn("message_thread_id", sent)


class TestMediaBlock(Base):
	def test_b_all_media_kinds_sent_before_text(self):
		text = "Report ready.\n" + media(
			photo("P1", caption="chart"),
			{"type": "document", "source": "file_id", "value": "D1"},
			photo("P2"),
			photo("P3"),
			photo("P4"),
			{"type": "voice", "source": "file_id", "value": "V1"},
			{"type": "location", "latitude": 1.5, "longitude": 2.5},
			{"type": "poll", "question": "Pick?", "options": ["a", "b"]},
			{"type": "dice", "emoji": "🎲"},
		)
		self.reply(FakeEvent(), text)
		self.assertEqual(
			self.methods(),
			[
				"sendPhoto",
				"sendDocument",
				"sendMediaGroup",
				"sendVoice",
				"sendLocation",
				"sendPoll",
				"sendDice",
				"sendMessage",
			],
		)
		first_photo = self.payloads("sendPhoto")[0]
		self.assertEqual(first_photo["caption"], "chart")
		self.assertEqual(first_photo["reply_parameters"]["message_id"], 77)
		self.assertEqual(len(self.payloads("sendMediaGroup")[0]["media"]), 3)
		text_msg = self.payloads("sendMessage")[0]
		self.assertEqual(text_msg["text"], "Report ready.")
		self.assertNotIn("reply_parameters", text_msg)

	def test_b_failed_attachment_appends_could_not_send_note(self):
		self.api.queue("sendPhoto", FakeBotApi.error("Bad Request: wrong file identifier", 400))
		result = self.reply(FakeEvent(), "The answer.\n" + media(photo("bad")))
		self.assertEqual(self.methods(), ["sendPhoto", "sendMessage", "sendMessage"])
		texts = [p["text"] for p in self.payloads("sendMessage")]
		self.assertEqual(texts[0], "The answer.")
		self.assertIn("Could not send 1 attachment", texts[-1])
		self.assertEqual(result["status"], "Succeeded")

	def test_b_media_only_reply_sends_no_empty_text(self):
		self.reply(FakeEvent(), media(photo("P1")))
		self.assertEqual(self.methods(), ["sendPhoto"])


class TestButtonsBlock(Base):
	SPEC = {"rows": [[{"text": "Yes", "callback": "yes"}], [{"text": "Docs", "url": "https://example.com"}]]}

	def test_c_markup_on_last_part_only_and_callback_is_signed(self):
		self.reply(FakeEvent(), "a" * 5000 + "\n" + buttons(self.SPEC))
		self.assertEqual(self.methods(), ["sendMessage", "sendMessage"])
		first, last = self.payloads("sendMessage")
		self.assertNotIn("reply_markup", first)
		rows = last["reply_markup"]["inline_keyboard"]
		self.assertEqual(rows[1][0], {"text": "Docs", "url": "https://example.com"})
		signed = rows[0][0]["callback_data"]
		self.assertNotEqual(signed, "b:--:yes")
		payload = self.adapter.verify_callback_data(signed, CHAT)
		self.assertEqual(tb.decode_payload(payload)["id"], "yes")

	def test_d_media_and_buttons_together_media_first_markup_on_text(self):
		text = "Hi there.\n" + media(photo("P1")) + "\n" + buttons(self.SPEC)
		self.reply(FakeEvent(), text)
		self.assertEqual(self.methods(), ["sendPhoto", "sendMessage"])
		text_msg = self.payloads("sendMessage")[0]
		self.assertEqual(text_msg["text"], "Hi there.")
		self.assertIn("reply_markup", text_msg)


class TestVoice(Base):
	def test_e_voice_only_sends_one_voice_note_and_no_text(self):
		event = FakeEvent(raw=VOICE_RAW)
		text = "Here is **the** answer.\n" + media(photo("P1")) + "\n" + buttons(TestButtonsBlock.SPEC)
		result = self.reply(event, text, make_gateway("Voice only"))
		self.assertEqual(self.methods(), ["sendChatAction", "sendVoice"])
		self.assertEqual(self.payloads("sendChatAction")[0]["action"], "upload_voice")
		spoken = self.synth.call_args.args[1]
		self.assertNotIn("```", spoken)
		self.assertNotIn("telegram", spoken)
		self.assertNotIn("example.com", spoken)
		self.assertIn("answer", spoken)
		self.assertTrue(result["voice"])
		self.assertEqual(event.values["status"], "Succeeded")

	def test_e_text_and_voice_sends_text_then_companion_voice_unquoted(self):
		event = FakeEvent(raw=VOICE_RAW)
		text = "Here is the answer.\n" + buttons(TestButtonsBlock.SPEC)
		result = self.reply(event, text, make_gateway("Text and voice"))
		self.assertEqual(self.methods(), ["sendMessage", "sendChatAction", "sendVoice"])
		self.assertIn("reply_markup", self.payloads("sendMessage")[0])
		self.assertNotIn("reply_parameters", self.payloads("sendVoice")[0])
		self.assertNotIn("```", self.synth.call_args.args[1])
		self.assertEqual(result["status"], "Succeeded")

	def test_e_text_and_voice_tts_failure_keeps_text(self):
		self.synth.side_effect = ValueError("no tts model")
		result = self.reply(FakeEvent(raw=VOICE_RAW), "Just text.", make_gateway("Text and voice"))
		self.assertEqual(self.methods(), ["sendMessage", "sendChatAction"])
		self.assertEqual(result["status"], "Succeeded")

	def test_e_ffmpeg_failure_in_voice_only_falls_back_to_text(self):
		self.convert.side_effect = send_file.FileSendError("ffmpeg_unavailable", "no ffmpeg")
		with mock.patch("frappe.logger"):
			self.reply(FakeEvent(raw=VOICE_RAW), "Fallback text.", make_gateway("Voice only"))
		self.assertEqual(self.methods(), ["sendChatAction", "sendMessage"])
		self.assertEqual(self.payloads("sendMessage")[0]["text"], "Fallback text.")


class TestOptOutAndBlocked(Base):
	def test_f_opted_out_sender_is_suppressed_without_any_api_call(self):
		self._patch(gateway_service, "is_opted_out", return_value=True)
		event = FakeEvent()
		result = self.reply(event, "Hello")
		self.assertEqual(self.api.calls, [])
		self.assertEqual(result["reply_status"], "suppressed")
		self.assertEqual(event.values["error_message"], tp.OPT_OUT_NOTE)
		self.enqueue.assert_not_called()

	def test_f_blocked_by_user_dead_letters_without_retry(self):
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		event = FakeEvent()
		gateway = make_gateway()
		result = self.reply(event, "Hello", gateway)
		self.assertEqual(self.methods(), ["sendMessage"])
		self.enqueue.assert_not_called()
		self.svc._record_opt_out.assert_called_once_with(gateway, "42")
		self.assertEqual(result["status"], "Failed")
		self.assertEqual(result["error_code"], "blocked")
		self.assertEqual(event.values["status"], "Failed")
		self.assertEqual(event.values["reply_status"], "failed")


class TestRetry(Base):
	def test_g_flood_wait_retries_only_unsent_part_after_retry_after(self):
		self.api.queue(
			"sendMessage",
			{"ok": True, "result": {"message_id": 500}},
			FakeBotApi.error("Too Many Requests: retry after 30", 429, retry_after=30),  # > inline wait: rescheduled
		)
		event = FakeEvent()
		text = "x" * 5000
		result = self.reply(event, text)
		self.assertEqual(result["reply_status"], "retrying")
		self.assertEqual(result["retry_in_seconds"], 31.0)
		self.assertEqual(event.reply_message_id, "500")
		kw = self.enqueue.call_args.kwargs
		self.assertEqual(kw["parts_remaining"], ["x" * 904])
		self.assertEqual(kw["attempt"], 2)

		# The queued retry job (retry_gateway_reply) re-enters the attempt with the remaining parts.
		retried = tp.attempt_parts(event, make_gateway(), kw["parts_remaining"], kw["attempt"])
		self.assertEqual(self.methods(), ["sendMessage", "sendMessage", "sendMessage"])
		last = self.payloads("sendMessage")[-1]
		self.assertEqual(last["text"], "x" * 904)
		self.assertNotIn("reply_parameters", last)
		self.assertEqual(retried["status"], "Succeeded")
		self.assertEqual(retried["attempts"], 2)

	def test_g_gives_up_after_max_attempts(self):
		self.api.queue("sendMessage", FakeBotApi.error("Bad Gateway", 502))
		event = FakeEvent()
		gateway = make_gateway()
		result = self.reply(event, "Hello")
		self.assertEqual(result["status"], "Running")
		kw = self.enqueue.call_args.kwargs
		self.api.queue("sendMessage", FakeBotApi.error("Bad Gateway", 502))
		final = tp.attempt_parts(event, gateway, kw["parts_remaining"], 4)
		self.assertEqual(final["status"], "Failed")
		self.assertIn("gave up after 4 attempts", event.values["delivery_error"])
		self.assertEqual(self.enqueue.call_count, 1)


class TestGuest(Base):
	def test_j_guest_event_is_answered_via_answerGuestQuery_not_sendMessage(self):
		self.assertIsNotNone(provider_hooks.get("Telegram", "guest_reply"))
		raw = {
			"update_id": 9,
			"guest_message": {
				"message_id": 5,
				"guest_query_id": "GQ1",
				"chat": {"id": CHAT, "type": "supergroup"},
				"from": {"id": 42, "first_name": "Gus"},
				"text": "hi there",
			},
			"telegram_meta": {"update_kind": "guest_message", "guest": True, "guest_query_id": "GQ1"},
		}
		event = FakeEvent(raw=raw, conversation_id="guest:555")
		result = self.reply(event, "Hello guest", make_gateway())
		self.assertEqual(self.methods(), ["answerGuestQuery"])
		payload = self.payloads("answerGuestQuery")[0]
		self.assertEqual(payload["guest_query_id"], "GQ1")
		self.assertIn("Hello guest", json.dumps(payload))
		self.assertEqual(
			result, {"event_name": "EVT-1", "status": "Succeeded", "agent_run_id": "RUN-1", "guest": True}
		)


if __name__ == "__main__":
	unittest.main()
