"""F5-LIMITS: error classification, flood/migration retries, UTF-16 splitting, albums, upload limits, until_date."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai.gateway_adapters import telegram_commands
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram_client import TelegramApiError, TelegramBotClient, redact_token
from huf.ai.gateway_adapters.telegram_format import (
	MODE_HTML,
	TELEGRAM_TEXT_LIMIT,
	_hard_cut,
	clusters,
	render_parts,
	split_message,
	text_len,
)
from huf.ai.gateway_adapters.telegram_outbound import PHOTO_MAX_BYTES, TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi
from huf.ai.tests.test_telegram_pipeline import Base as PipelineBase
from huf.ai.tests.test_telegram_pipeline import FakeEvent
from huf.ai.tools import telegram_admin_tools as admin


def err(description, code=400, **kw):
	return TelegramApiError("sendMessage", description, error_code=code, **kw)


# (description, http code, kind, blocked_by_user, room_removed, missing_rights, retryable)
CLASSIFICATION = [
	("Forbidden: bot was blocked by the user", 403, "blocked", True, False, False, False),
	("Forbidden: user is deactivated", 403, "user_deactivated", True, False, False, False),
	("Forbidden: bot was kicked from the supergroup chat", 403, "room_removed", False, True, False, False),
	("Forbidden: bot was kicked from the group chat", 403, "room_removed", False, True, False, False),
	("Forbidden: bot is not a member of the channel chat", 403, "room_removed", False, True, False, False),
	("Forbidden: the group chat was deleted", 403, "room_removed", False, True, False, False),
	(
		"Forbidden: bot can't initiate conversation with a user",
		403,
		"cannot_initiate",
		False,
		False,
		False,
		False,
	),
	(
		"Bad Request: not enough rights to send text messages to the chat",
		400,
		"missing_rights",
		False,
		False,
		True,
		False,
	),
	(
		"Forbidden: not enough rights to send photos to the chat",
		403,
		"missing_rights",
		False,
		False,
		True,
		False,
	),
	("Bad Request: CHAT_ADMIN_REQUIRED", 400, "missing_rights", False, False, True, False),
	("Forbidden: some brand new 403 text", 403, None, False, False, False, False),
	("Bad Request: chat not found", 400, "chat_not_found", False, False, False, False),
	("Bad Request: BUTTON_URL_INVALID", 400, "button_url_invalid", False, False, False, False),
	("Bad Request: WEB_APP_URL_INVALID", 400, "web_app_url_invalid", False, False, False, False),
	("Bad Request: BUTTON_TYPE_INVALID", 400, "button_type_invalid", False, False, False, False),
	("Bad Request: BOT_DOMAIN_INVALID", 400, "bot_domain_invalid", False, False, False, False),
	("Bad Request: REPLY_MARKUP_TOO_LONG", 400, "reply_markup_too_long", False, False, False, False),
	("Bad Request: message to edit not found", 400, "message_to_edit_not_found", False, False, False, False),
	("Bad Request: message is too long", 400, "message_too_long", False, False, False, False),
	("Bad Request: message caption is too long", 400, "caption_too_long", False, False, False, False),
	("Bad Request: message is not modified", 400, "message_not_modified", False, False, False, False),
	("Bad Gateway", 502, None, False, False, False, True),
]


class TestClassification(unittest.TestCase):
	def test_table(self):
		for desc, code, kind, blocked, removed, rights, retryable in CLASSIFICATION:
			with self.subTest(desc):
				e = err(desc, code)
				self.assertEqual(e.kind, kind)
				self.assertEqual(
					(e.blocked_by_user, e.room_removed, e.missing_rights, e.retryable),
					(blocked, removed, rights, retryable),
				)

	def test_flood_is_rate_limited_and_retryable(self):
		e = err("Too Many Requests: retry after 9", 429, retry_after=9)
		self.assertEqual((e.code, e.retryable, e.kind), ("rate_limited", True, "rate_limited"))

	def test_classify_opt_out_target(self):
		cases = {
			"Forbidden: bot was blocked by the user": ("user", "blocked"),
			"Forbidden: user is deactivated": ("user", "blocked"),
			"Forbidden: bot was kicked from the supergroup chat": ("room", "room_removed"),
			"Forbidden: not enough rights to send text messages to the chat": (None, "missing_rights"),
			"Forbidden: some brand new 403 text": (None, "telegram_error"),
		}
		for desc, (opt_out, code) in cases.items():
			with self.subTest(desc):
				c = tp.classify(err(desc, 403))
				self.assertEqual((c["opt_out"], c["code"], c["retryable"]), (opt_out, code, False))

	def test_missing_rights_message_is_actionable(self):
		text = tp.classify(err("Bad Request: not enough rights to send text messages to the chat"))[
			"operator_text"
		]
		self.assertIn("Grant the bot the needed right", text)
		self.assertNotIn("blocked", text)

	def test_operator_texts_have_no_token(self):
		client = TelegramBotClient(
			TOKEN,
			http_post=lambda *a, **k: (_ for _ in ()).throw(
				RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMessage failed")
			),
		)
		with self.assertRaises(TelegramApiError) as ctx:
			client.call("sendMessage", {"chat_id": 1})
		secret = TOKEN.split(":")[1]
		for text in (
			str(ctx.exception),
			ctx.exception.description,
			ctx.exception.operator_message,
			tp.classify(ctx.exception)["operator_text"],
		):
			self.assertNotIn(secret, text)
			self.assertNotIn(TOKEN, text)
		for desc, *_ in CLASSIFICATION:
			body = FakeBotApi.error(f"{desc} {TOKEN}", 400)
			c = TelegramBotClient(TOKEN, http_post=lambda *a, _b=body, **k: _b)
			with self.assertRaises(TelegramApiError) as ctx:
				c.call("sendMessage", {"chat_id": 1})
			self.assertNotIn(secret, ctx.exception.operator_message)
			self.assertEqual(redact_token(f"x {TOKEN}", TOKEN), "x <redacted-token>")


class TestHandleFailureOptOut(PipelineBase):
	def setUp(self):
		super().setUp()
		self.svc = mock.MagicMock()
		self.svc._reply_max_attempts.return_value = 4
		self.svc._redact_error_text.side_effect = lambda s: s
		p = mock.patch.object(tp, "_svc", return_value=self.svc)
		p.start()
		self.addCleanup(p.stop)
		for target in (
			"frappe.enqueue",
			"frappe.log_error",
			"frappe.logger",
			"huf.ai.gateway_webhook._set_gateway_error",
		):
			m = mock.patch(target)
			m.start()
			self.addCleanup(m.stop)
		self.gw = SimpleNamespace(name="GW", provider="Telegram")

	def fail(self, desc, code, conversation="-100500"):
		event = FakeEvent(conversation_id=conversation)
		return tp.handle_failure(event, self.gw, err(desc, code), ["p"], 1), event

	def test_rights_403_in_room_does_not_opt_out(self):
		out, event = self.fail("Forbidden: not enough rights to send text messages to the chat", 403)
		self.svc._record_room_opt_out.assert_not_called()
		self.svc._record_opt_out.assert_not_called()
		self.assertEqual((out["status"], out["error_code"]), ("Failed", "missing_rights"))
		self.assertIn("Grant the bot the needed right", event.values["delivery_error"])

	def test_kicked_opts_out_room_only(self):
		out, _ = self.fail("Forbidden: bot was kicked from the supergroup chat", 403)
		self.svc._record_room_opt_out.assert_called_once_with(self.gw, "-100500")
		self.svc._record_opt_out.assert_not_called()
		self.assertEqual(out["error_code"], "room_removed")

	def test_blocked_and_deactivated_opt_out_sender(self):
		for desc in ("Forbidden: bot was blocked by the user", "Forbidden: user is deactivated"):
			with self.subTest(desc):
				self.svc.reset_mock()
				self.fail(desc, 403, conversation="555")
				self.svc._record_opt_out.assert_called_once_with(self.gw, "42")
				self.svc._record_room_opt_out.assert_not_called()


class TestBackoff(unittest.TestCase):
	def test_arithmetic(self):
		cases = [
			({"delay": None}, 1, 5.0),
			({"delay": None}, 3, 20.0),
			({"delay": None}, 10, 300.0),
			({"delay": 4.0}, 1, 5.0),  # retry_after 3 + 1 < backoff
			({"delay": 61.0}, 1, 61.0),
			({"delay": 901.0}, 1, 901.0),  # larger than the cap: never retried early
			({"delay": 901.0}, 9, 901.0),
		]
		for cls, attempt, expect in cases:
			with self.subTest((cls, attempt)):
				self.assertEqual(tp.backoff_seconds(cls, attempt), expect)

	def test_classify_flood_delay_is_retry_after_plus_one(self):
		c = tp.classify(err("Too Many Requests", 429, retry_after=900))
		self.assertEqual((c["delay"], tp.backoff_seconds(c, 1)), (901.0, 901.0))


class TestClientRetries(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.sleeps = []

	def client(self, **kw):
		return TelegramBotClient(TOKEN, http_post=self.api.http_post, sleep=self.sleeps.append, **kw)

	def test_default_allows_one_short_inline_retry(self):
		self.api.queue("sendMessage", FakeBotApi.error("Too Many Requests", 429, retry_after=2))
		self.client().call("sendMessage", {"chat_id": 1, "text": "x"})
		self.assertEqual(self.sleeps, [2])
		self.assertEqual(
			[c["payload"] for c in self.api.of("sendMessage")], [{"chat_id": 1, "text": "x"}] * 2
		)

	def test_only_one_inline_retry(self):
		flood = FakeBotApi.error("Too Many Requests", 429, retry_after=1)
		self.api.queue("sendMessage", flood, flood)
		with self.assertRaises(TelegramApiError):
			self.client().call("sendMessage", {"chat_id": 1, "text": "x"})
		self.assertEqual((self.sleeps, len(self.api.of("sendMessage"))), ([1], 2))

	def test_long_wait_left_to_scheduled_retry(self):
		self.api.queue("sendMessage", FakeBotApi.error("Too Many Requests", 429, retry_after=6))
		with self.assertRaises(TelegramApiError):
			self.client().call("sendMessage", {"chat_id": 1, "text": "x"})
		self.assertEqual((self.sleeps, len(self.api.of("sendMessage"))), ([], 1))


def migrate_body(new_id):
	return {
		"ok": False,
		"error_code": 400,
		"description": "Bad Request: group chat was upgraded to a supergroup chat",
		"parameters": {"migrate_to_chat_id": new_id},
	}


class TestMigrationRetry(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.moved = []
		self.client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, on_chat_migrated=lambda o, n: self.moved.append((o, n))
		)

	def test_retries_once_with_new_id_and_persists(self):
		self.api.queue("sendMessage", migrate_body(-1005))
		res = self.client.call("sendMessage", {"chat_id": -5, "text": "hi"})
		self.assertEqual(self.moved, [("-5", "-1005")])
		self.assertEqual(
			[c["payload"] for c in self.api.of("sendMessage")],
			[{"chat_id": -5, "text": "hi"}, {"chat_id": -1005, "text": "hi"}],
		)
		self.assertEqual(res["chat"]["id"], -1005)

	def test_second_migration_error_is_not_retried_again(self):
		self.api.queue("sendMessage", migrate_body(-1005), migrate_body(-2006))
		with self.assertRaises(TelegramApiError) as ctx:
			self.client.call("sendMessage", {"chat_id": -5, "text": "hi"})
		self.assertEqual(ctx.exception.migrate_to_chat_id, -2006)
		self.assertEqual(len(self.api.of("sendMessage")), 2)
		self.assertEqual(self.moved, [("-5", "-1005")])

	def test_same_id_or_no_chat_id_is_not_retried(self):
		self.api.queue("sendMessage", migrate_body(-5))
		with self.assertRaises(TelegramApiError):
			self.client.call("sendMessage", {"chat_id": -5, "text": "hi"})
		self.assertEqual((len(self.api.of("sendMessage")), self.moved), (1, []))

	def test_callback_failure_does_not_block_delivery(self):
		client = TelegramBotClient(TOKEN, http_post=self.api.http_post, on_chat_migrated=lambda o, n: 1 / 0)
		self.api.queue("sendMessage", migrate_body(-1005))
		client.call("sendMessage", {"chat_id": -5, "text": "hi"})
		self.assertEqual(self.api.last("sendMessage")["payload"]["chat_id"], -1005)

	def test_pipeline_persists_through_migrate_room(self):
		with mock.patch("huf.ai.gateway_adapters.telegram_groups.migrate_room", return_value=True) as mig:
			tp._persist_migration("GW", "-5", "-1005")
		mig.assert_called_once_with("GW", "-5", "-1005")


class TestUtf16Splitting(unittest.TestCase):
	def test_text_len_counts_utf16_units(self):
		self.assertEqual(
			[text_len(s) for s in ("abc", "é", "\U0001f600", "\U0001f468‍\U0001f469")], [3, 1, 2, 5]
		)

	def test_every_part_within_limit_for_astral_text(self):
		src = "\U0001f600" * 3000  # 6000 UTF-16 units, 3000 code points
		parts = split_message(src)
		self.assertGreater(len(parts), 1)
		self.assertTrue(all(text_len(p) <= TELEGRAM_TEXT_LIMIT for p in parts))
		self.assertEqual("".join(parts), src)
		rendered = render_parts(src, MODE_HTML)
		self.assertTrue(all(text_len(p.text) <= TELEGRAM_TEXT_LIMIT for p in rendered))
		self.assertEqual("".join(p.plain for p in rendered), src)

	def test_hard_cut_never_splits_zwj_family(self):
		family = "\U0001f468‍\U0001f469‍\U0001f467"  # 8 units
		src = family * 5
		chunks = _hard_cut(src, 10)
		self.assertEqual(chunks, [family] * 5)
		chunks = _hard_cut("a" + family + "b", 9)
		self.assertEqual(chunks, ["a" + family, "b"])

	def test_hard_cut_keeps_combining_variation_skin_tone_flags(self):
		for unit in ("é", "❤️", "\U0001f44d\U0001f3fd", "\U0001f1ee\U0001f1f3", "1️⃣"):
			with self.subTest(unit):
				chunks = _hard_cut(unit * 4, text_len(unit) + 1)
				self.assertEqual(chunks, [unit] * 4)
				self.assertEqual(clusters(unit * 2), [unit, unit])

	def test_two_flags_are_two_clusters(self):
		flags = "\U0001f1ee\U0001f1f3\U0001f1fa\U0001f1f8"
		self.assertEqual(clusters(flags), ["\U0001f1ee\U0001f1f3", "\U0001f1fa\U0001f1f8"])

	def test_caption_limit_counts_units(self):
		parts = render_parts("\U0001f600" * 600, "", 1024)  # 1200 units
		self.assertEqual([text_len(p.text) for p in parts], [1024, 176])


class SenderBase(unittest.TestCase):
	parse_mode = ""

	def setUp(self):
		self.api = FakeBotApi()
		self.client = TelegramBotClient(TOKEN, http_post=self.api.http_post, sleep=lambda s: None)
		self.sender = TelegramSender(self.client, parse_mode=self.parse_mode)


class TestMessageTooLong(SenderBase):
	parse_mode = MODE_HTML

	def test_resplits_once_smaller(self):
		text = ("word " * 700).strip()  # ~3500 chars, one part
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: message is too long", 400))
		out = self.sender.send_text(
			5, text, reply_to="9", markup={"inline_keyboard": [[{"text": "a", "callback_data": "b"}]]}
		)
		calls = [c["payload"] for c in self.api.of("sendMessage")]
		self.assertEqual(len(calls), 1 + len(out))
		self.assertGreaterEqual(len(out), 2)
		first, *rest = calls[1:]
		self.assertTrue(all(text_len(c["text"]) <= TELEGRAM_TEXT_LIMIT // 2 for c in calls[1:]))
		self.assertEqual(" ".join(c["text"] for c in calls[1:]).split(), text.split())
		self.assertIn("reply_parameters", first)
		self.assertNotIn("reply_markup", first)
		for c in rest[:-1]:
			self.assertEqual(set(c), {"chat_id", "text", "parse_mode"})
		self.assertEqual(
			rest[-1]["reply_markup"], {"inline_keyboard": [[{"text": "a", "callback_data": "b"}]]}
		)
		self.assertNotIn("reply_parameters", rest[-1])

	def test_second_too_long_propagates(self):
		too_long = FakeBotApi.error("Bad Request: message is too long", 400)
		self.api.queue("sendMessage", too_long, too_long)
		with self.assertRaises(TelegramApiError):
			self.sender.send_text(5, ("word " * 700).strip())


class TestAlbums(SenderBase):
	parse_mode = MODE_HTML

	def items(self, **first):
		return [
			{"type": "photo", "media": "FID1", **first},
			{"type": "audio", "media": "FID2", "title": "T", "performer": "P", "duration": 33},
			{"type": "video", "media": "FID3", "has_spoiler": True, "supports_streaming": True},
		]

	def test_full_payload_preserves_item_options(self):
		self.sender.send_media_group(
			7, self.items(has_spoiler=True, caption="**hi**"), thread_id="4", silent=True
		)
		self.assertEqual(
			self.api.last("sendMediaGroup")["payload"],
			{
				"chat_id": 7,
				"message_thread_id": 4,
				"disable_notification": True,
				"media": [
					{
						"type": "photo",
						"media": "FID1",
						"has_spoiler": True,
						"caption": "<b>hi</b>",
						"parse_mode": "HTML",
					},
					{"type": "audio", "media": "FID2", "title": "T", "performer": "P", "duration": 33},
					{"type": "video", "media": "FID3", "has_spoiler": True, "supports_streaming": True},
				],
			},
		)

	def test_caption_overflow_goes_out_as_text(self):
		long_caption = "x" * 1500
		out = self.sender.send_media_group(7, self.items(caption=long_caption), reply_to="3", parse_mode="")
		media = self.api.last("sendMediaGroup")["payload"]
		self.assertNotIn("caption", media["media"][0])
		self.assertEqual(media["reply_parameters"], {"message_id": 3, "allow_sending_without_reply": True})
		texts = [c["payload"] for c in self.api.of("sendMessage")]
		self.assertEqual([t["text"] for t in texts], [long_caption])
		self.assertEqual(texts[0].keys(), {"chat_id", "text"})
		self.assertEqual(len(out), 2 + 1)

	def test_parse_mode_override_and_markup_refused(self):
		self.sender.send_media_group(7, self.items(caption="a_b"), parse_mode="")
		self.assertEqual(self.api.last("sendMediaGroup")["payload"]["media"][0]["caption"], "a_b")
		self.assertNotIn("parse_mode", self.api.last("sendMediaGroup")["payload"]["media"][0])
		with self.assertRaisesRegex(ValueError, "keyboard"):
			self.sender.send_media_group(7, self.items(), reply_markup={"inline_keyboard": [[]]})
		with self.assertRaises(ValueError):
			self.sender.send_media_group(7, self.items(), parse_mode="Markdown")

	def test_oversized_photo_item_refused(self):
		items = self.items()
		items[0]["media"] = ("big.jpg", b"0" * (PHOTO_MAX_BYTES + 1))
		with self.assertRaisesRegex(ValueError, "Album item 1.*10 MB"):
			self.sender.send_media_group(7, items)
		self.assertEqual(self.api.calls, [])


class TestUploadLimits(SenderBase):
	def test_big_photo_falls_back_to_document(self):
		data = b"0" * (PHOTO_MAX_BYTES + 1)
		self.sender.send_photo(5, ("p.jpg", data), caption="c", extra={"has_spoiler": True, "foo": 1})
		call = self.api.last()
		self.assertEqual(call["method"], "sendDocument")
		self.assertEqual(call["payload"], {"chat_id": 5, "caption": "c", "foo": 1})
		self.assertEqual(list(call["files"]), ["document"])

	def test_photo_at_limit_stays_photo(self):
		self.sender.send_photo(5, ("p.jpg", b"0" * PHOTO_MAX_BYTES))
		self.assertEqual(self.api.last()["method"], "sendPhoto")

	def test_over_50mb_refused_without_calling_api(self):
		with self.assertRaisesRegex(ValueError, "50 MB"):
			self.sender.send_document(5, ("f.bin", b"0" * (50 * 1024 * 1024 + 1)))
		self.assertEqual(self.api.calls, [])

	def test_caption_too_long_error_resends_without_caption_then_text(self):
		self.api.queue("sendPhoto", FakeBotApi.error("Bad Request: message caption is too long", 400))
		self.sender.send_photo(5, "FID", caption="short")
		self.assertEqual(self.api.of("sendPhoto")[1]["payload"], {"chat_id": 5, "photo": "FID"})
		self.assertEqual(self.api.last("sendMessage")["payload"], {"chat_id": 5, "text": "short"})


class TestEditNotModified(SenderBase):
	def test_reply_markup_not_modified_returns_none(self):
		self.api.queue(
			"editMessageReplyMarkup", FakeBotApi.error("Bad Request: message is not modified", 400)
		)
		self.assertIsNone(self.sender.edit_message_reply_markup(5, 9, None))

	def test_message_to_edit_not_found_raises_with_kind(self):
		self.api.queue(
			"editMessageReplyMarkup", FakeBotApi.error("Bad Request: message to edit not found", 400)
		)
		with self.assertRaises(TelegramApiError) as ctx:
			self.sender.edit_message_reply_markup(5, 9, None)
		self.assertEqual(ctx.exception.code, "message_to_edit_not_found")
		self.assertIn("no longer exists", ctx.exception.operator_message)


class TestCommandsSingleValidatedPath(unittest.TestCase):
	def test_client_has_no_duplicate_set_my_commands(self):
		self.assertFalse(hasattr(TelegramBotClient, "set_my_commands"))

	def test_invalid_names_are_rejected_not_truncated(self):
		with self.assertRaises(ValueError):
			telegram_commands.build_commands([("a" * 33, "d")])
		with self.assertRaises(ValueError):
			telegram_commands.build_commands([("ok", "d" * 257)])


class TestUntilDate(unittest.TestCase):
	NOW = 1_800_000_000

	def until(self, **args):
		with mock.patch.object(admin.time, "time", return_value=self.NOW):
			return admin._until(args)

	def refused(self, **args):
		with self.assertRaises(admin.Refused) as ctx:
			self.until(**args)
		return ctx.exception.payload["message"]

	def test_valid(self):
		self.assertIsNone(self.until())
		self.assertEqual(self.until(duration_minutes=1), self.NOW + 60)
		self.assertEqual(self.until(duration_minutes="90"), self.NOW + 5400)
		self.assertEqual(self.until(until_date=self.NOW + 3600), self.NOW + 3600)
		self.assertEqual(self.until(duration_minutes=366 * 24 * 60 - 1), self.NOW + (366 * 24 * 60 - 1) * 60)

	def test_refused(self):
		self.assertIn("at least 1", self.refused(duration_minutes=0))
		self.assertIn("at least 1", self.refused(duration_minutes=-5))
		self.assertIn("at least 60 seconds", self.refused(until_date=self.NOW + 10))
		self.assertIn("at least 60 seconds", self.refused(until_date=self.NOW - 100))
		self.assertIn("at most 366 days", self.refused(until_date=self.NOW + 400 * 86400))
		self.assertIn("at most 366 days", self.refused(duration_minutes=367 * 24 * 60))


if __name__ == "__main__":
	unittest.main()
