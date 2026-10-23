"""Senders and client against the in-memory fake Bot API."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters.telegram_client import ALLOWED_UPDATES, TelegramApiError, TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi


class Base(unittest.TestCase):
	parse_mode = ""

	def setUp(self):
		self.api = FakeBotApi()
		self.sleeps = []
		self.client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=self.sleeps.append
		)
		self.sender = TelegramSender(self.client, parse_mode=self.parse_mode)


class TestSenders(Base):
	def test_send_text_plain_payload_and_reply_parameters(self):
		self.sender.send_text(5, "hi", reply_to="9", thread_id="3", silent=True)
		call = self.api.last("sendMessage")
		self.assertEqual(call["url"], f"https://api.telegram.org/bot{TOKEN}/sendMessage")
		self.assertEqual(
			call["payload"],
			{
				"chat_id": 5,
				"message_thread_id": 3,
				"text": "hi",
				"disable_notification": True,
				"reply_parameters": {"message_id": 9, "allow_sending_without_reply": True},
			},
		)

	def test_send_text_splits_at_4096_reply_only_on_first_markup_only_on_last(self):
		markup = {"inline_keyboard": [[{"text": "ok", "callback_data": "x"}]]}
		results = self.sender.send_text(5, "x" * 9000, reply_to=1, markup=markup)
		calls = self.api.of("sendMessage")
		self.assertEqual(len(calls), 3)
		self.assertEqual(len(results), 3)
		self.assertTrue(all(len(c["payload"]["text"]) <= 4096 for c in calls))
		self.assertIn("reply_parameters", calls[0]["payload"])
		self.assertNotIn("reply_parameters", calls[1]["payload"])
		self.assertEqual([("reply_markup" in c["payload"]) for c in calls], [False, False, True])

	def test_link_preview_disabled(self):
		self.sender.send_text(5, "x", link_preview=False)
		self.assertEqual(self.api.last()["payload"]["link_preview_options"], {"is_disabled": True})

	def test_media_by_file_id_url_and_upload(self):
		self.sender.send_photo(5, "FILE_ID", caption="cap")
		self.assertEqual(self.api.last()["payload"], {"chat_id": 5, "photo": "FILE_ID", "caption": "cap"})
		self.sender.send_document(5, "https://x/y.pdf")
		self.assertEqual(self.api.last("sendDocument")["payload"]["document"], "https://x/y.pdf")
		self.sender.send_voice(5, b"ogg")
		call = self.api.last("sendVoice")
		self.assertEqual(call["files"]["voice"], ("voice.ogg", b"ogg", "audio/ogg"))
		self.assertNotIn("voice", call["payload"])
		self.sender.send_document(5, ("r.pdf", b"%PDF"))
		self.assertEqual(self.api.last("sendDocument")["files"]["document"][0], "r.pdf")

	def test_every_media_method(self):
		expected = {
			"photo": "sendPhoto",
			"document": "sendDocument",
			"audio": "sendAudio",
			"voice": "sendVoice",
			"video": "sendVideo",
			"animation": "sendAnimation",
			"sticker": "sendSticker",
			"video_note": "sendVideoNote",
		}
		for kind, method in expected.items():
			with self.subTest(kind):
				self.sender.send_media(kind, 5, "FID")
				self.assertEqual(self.api.last()["method"], method)
				self.assertEqual(self.api.last()["payload"][kind], "FID")
		with self.assertRaises(ValueError):
			self.sender.send_media("nope", 5, "x")

	def test_long_caption_goes_as_followup_text(self):
		self.sender.send_photo(5, "FID", caption="c" * 1500)
		self.assertNotIn("caption", self.api.last("sendPhoto")["payload"])
		self.assertEqual(len(self.api.of("sendMessage")), 1)

	def test_sticker_has_no_caption(self):
		self.sender.send_sticker(5, "FID", caption="ignored")
		self.assertNotIn("caption", self.api.last()["payload"])

	def test_media_group_with_upload(self):
		self.sender.send_media_group(
			5, [{"type": "photo", "media": "A", "caption": "one"}, {"type": "photo", "media": b"jpg"}]
		)
		call = self.api.last("sendMediaGroup")
		media = json.loads(call["payload"]["media"])  # multipart: non-scalar fields are JSON strings
		self.assertEqual(media[0], {"type": "photo", "media": "A", "caption": "one"})
		self.assertEqual(media[1]["media"], "attach://file1")
		self.assertIn("file1", call["files"])
		with self.assertRaises(ValueError):
			self.sender.send_media_group(5, [{"type": "photo", "media": "A"}])

	def test_location_and_contact(self):
		self.sender.send_location(5, 1.5, 2.5)
		self.assertEqual(self.api.last()["payload"], {"chat_id": 5, "latitude": 1.5, "longitude": 2.5})
		self.sender.send_contact(5, "+1", "Asha", last_name="K")
		self.assertEqual(self.api.last()["payload"]["last_name"], "K")

	def test_reaction_set_and_clear(self):
		self.sender.set_reaction(5, "9", "👍", big=True)
		self.assertEqual(
			self.api.last()["payload"],
			{"chat_id": 5, "message_id": 9, "reaction": [{"type": "emoji", "emoji": "👍"}], "is_big": True},
		)
		self.sender.set_reaction(5, 9, None)
		self.assertEqual(self.api.last()["payload"]["reaction"], [])
		self.assertEqual(self.api.last()["method"], "setMessageReaction")

	def test_chat_action(self):
		self.sender.send_chat_action(5, "upload_photo", thread_id=2)
		self.assertEqual(
			self.api.last()["payload"], {"chat_id": 5, "action": "upload_photo", "message_thread_id": 2}
		)
		with self.assertRaises(ValueError):
			self.sender.send_chat_action(5, "dance")

	def test_edit_delete_pin_answer(self):
		self.sender.edit_message_text(5, 9, "new", markup={"inline_keyboard": []})
		self.assertEqual(self.api.last()["method"], "editMessageText")
		self.assertEqual(self.api.last()["payload"]["message_id"], 9)
		self.sender.edit_message_caption(5, 9, "cap")
		self.assertEqual(self.api.last()["payload"]["caption"], "cap")
		self.sender.edit_message_reply_markup(5, 9)
		self.assertEqual(self.api.last()["payload"]["reply_markup"], {"inline_keyboard": []})
		self.sender.delete_message(5, 9)
		self.assertEqual(self.api.last()["payload"], {"chat_id": 5, "message_id": 9})
		self.sender.pin_message(5, 9)
		self.assertEqual(self.api.last()["payload"]["disable_notification"], True)
		self.sender.unpin_message(5, 9)
		self.assertEqual(self.api.last()["method"], "unpinChatMessage")
		self.sender.answer_callback_query("cbq", "done", show_alert=True, cache_time=0)
		self.assertEqual(
			self.api.last()["payload"],
			{"callback_query_id": "cbq", "text": "done", "show_alert": True, "cache_time": 0},
		)

	def test_edit_not_modified_returns_none(self):
		self.api.queue("editMessageText", FakeBotApi.error("Bad Request: message is not modified", 400))
		self.assertIsNone(self.sender.edit_message_text(5, 9, "same"))

	def test_drafts_and_rich_messages(self):
		self.sender.send_message_draft(5, 7, "thinking", can_stop=True)
		self.assertEqual(
			self.api.last()["payload"], {"chat_id": 5, "draft_id": 7, "text": "thinking", "can_stop": True}
		)
		with self.assertRaises(ValueError):
			self.sender.send_message_draft(5, 0)
		self.sender.send_rich_message(5, markdown="# hi")
		self.assertEqual(self.api.last()["payload"]["rich_message"], {"markdown": "# hi"})
		self.sender.send_rich_message_draft(5, 3, html="<b>x</b>")
		self.assertEqual(self.api.last()["method"], "sendRichMessageDraft")
		with self.assertRaises(ValueError):
			self.sender.send_rich_message(5, markdown="a", html="b")


class TestFormattedSend(Base):
	parse_mode = "HTML"

	def test_html_parse_mode_applied(self):
		self.sender.send_text(5, "**hi** <x>")
		payload = self.api.last()["payload"]
		self.assertEqual((payload["text"], payload["parse_mode"]), ("<b>hi</b> &lt;x&gt;", "HTML"))

	def test_parse_error_falls_back_to_plain(self):
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: can't parse entities: bad", 400))
		self.sender.send_text(5, "**hi** there")
		first, second = self.api.of("sendMessage")
		self.assertEqual(first["payload"]["parse_mode"], "HTML")
		self.assertNotIn("parse_mode", second["payload"])
		self.assertEqual(second["payload"]["text"], "hi there")

	def test_non_parse_errors_propagate(self):
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		with self.assertRaises(TelegramApiError):
			self.sender.send_text(5, "hi")
		self.assertEqual(len(self.api.of("sendMessage")), 1)


class TestClientErrors(Base):
	def test_flood_control_retry_after_not_retried_by_default(self):
		self.api.queue(
			"sendMessage", FakeBotApi.error("Too Many Requests: retry after 7", 429, retry_after=7)
		)
		with self.assertRaises(TelegramApiError) as ctx:
			self.client.call("sendMessage", {"chat_id": 1, "text": "x"})
		err = ctx.exception
		self.assertEqual((err.retry_after, err.error_code), (7, 429))
		self.assertTrue(err.flood_control and err.retryable)
		self.assertFalse(err.blocked_by_user)

	def test_flood_control_auto_retry_when_short(self):
		client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, max_flood_retries=1, sleep=self.sleeps.append
		)
		self.api.queue("sendMessage", FakeBotApi.error("Too Many Requests", 429, retry_after=2))
		client.call("sendMessage", {"chat_id": 1, "text": "x"})
		self.assertEqual(self.sleeps, [2])
		self.assertEqual(len(self.api.of("sendMessage")), 2)

	def test_flood_control_not_auto_retried_when_long(self):
		client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, max_flood_retries=1, sleep=self.sleeps.append
		)
		self.api.queue("sendMessage", FakeBotApi.error("Too Many Requests", 429, retry_after=60))
		with self.assertRaises(TelegramApiError):
			client.call("sendMessage", {"chat_id": 1, "text": "x"})
		self.assertEqual(self.sleeps, [])

	def test_blocked_by_user_classification(self):
		self.api.queue("sendMessage", FakeBotApi.error("Forbidden: bot was blocked by the user", 403))
		with self.assertRaises(TelegramApiError) as ctx:
			self.client.call("sendMessage", {"chat_id": 1, "text": "x"})
		err = ctx.exception
		self.assertTrue(err.blocked_by_user)
		self.assertFalse(err.retryable)
		self.assertFalse(err.chat_not_found)

	def test_chat_not_found_parse_error_and_5xx(self):
		cases = [
			("Bad Request: chat not found", 400, "chat_not_found", False),
			("Bad Request: can't parse entities: x", 400, "parse_error", False),
			("Internal Server Error", 502, "retryable", True),
		]
		for desc, code, attr, retryable in cases:
			with self.subTest(desc):
				err = TelegramApiError("m", desc, error_code=code)
				self.assertTrue(getattr(err, attr))
				self.assertEqual(err.retryable, retryable)

	def test_token_redacted_in_errors(self):
		def boom(*a, **k):
			raise RuntimeError(f"connection failed for https://api.telegram.org/bot{TOKEN}/sendMessage")

		client = TelegramBotClient(TOKEN, http_post=boom)
		with self.assertRaises(TelegramApiError) as ctx:
			client.call("sendMessage", {})
		self.assertNotIn(TOKEN.split(":")[1], str(ctx.exception))
		self.assertTrue(ctx.exception.retryable)

	def test_non_json_response(self):
		class Bad:
			status_code = 502

			def json(self):
				raise ValueError("no json")

		client = TelegramBotClient(TOKEN, http_post=lambda *a, **k: Bad())
		with self.assertRaises(TelegramApiError) as ctx:
			client.call("getMe")
		self.assertTrue(ctx.exception.retryable)

	def test_webhook_and_commands(self):
		self.client.set_webhook("https://h/x", secret_token="s", drop_pending_updates=True)
		payload = self.api.last("setWebhook")["payload"]
		self.assertEqual(payload["allowed_updates"], list(ALLOWED_UPDATES))
		for needed in (
			"message",
			"edited_message",
			"callback_query",
			"message_reaction",
			"my_chat_member",
			"channel_post",
		):
			self.assertIn(needed, payload["allowed_updates"])
		self.assertTrue(payload["drop_pending_updates"])
		self.assertEqual(self.client.get_webhook_info()["pending_update_count"], 0)
		self.client.set_my_commands(
			[("/Start", "Begin"), {"command": "help", "description": "Help"}], language_code="en"
		)
		self.assertEqual(
			self.api.last("setMyCommands")["payload"],
			{
				"commands": [
					{"command": "start", "description": "Begin"},
					{"command": "help", "description": "Help"},
				],
				"language_code": "en",
			},
		)

	def test_download_file(self):
		content, path = self.client.download_file("FID")
		self.assertEqual((content, path), (b"file-bytes", "photos/f.jpg"))
		self.assertTrue(self.api.gets[0].endswith("/file/bot" + TOKEN + "/photos/f.jpg"))
