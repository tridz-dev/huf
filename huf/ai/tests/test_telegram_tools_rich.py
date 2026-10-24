# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Rich Telegram agent-tool actions over the in-memory fake Bot API (no network, no live bot)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai import telegram_send_scope as scope
from huf.ai.gateway_adapters import telegram_senders_extra as extra
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi
from huf.ai.tools import telegram as tool

FILE_ID = "AgACAgIAAxkBAAIBQ2abcdefghijklmnopqrstuvwxyz0123"


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()

		def fake_make_client(token, *, timeout=30):
			return TelegramBotClient(
				token,
				http_post=self.api.http_post,
				http_get=self.api.http_get,
				timeout=timeout,
				sleep=lambda s: None,
			)

		self.addCleanup(patch.stopall)
		patch.object(tool, "update_last_error").start()
		patch.object(tool, "_make_client", side_effect=fake_make_client).start()
		patch.object(tool, "_get_token", return_value=TOKEN).start()
		patch.object(tool.scope, "run_gateway", return_value="").start()
		self.validate = patch("huf.ai.http_handler.validate_url", return_value=(True, None)).start()

	def run_action(self, **kwargs):
		return json.loads(tool.handle_action(**kwargs))

	def payload(self, method):
		return self.api.last(method)["payload"]


class TestMediaActions(Base):
	def test_each_media_action_hits_its_method_with_file_id(self):
		cases = {
			"send_voice": ("sendVoice", "voice"),
			"send_audio": ("sendAudio", "audio"),
			"send_video": ("sendVideo", "video"),
			"send_animation": ("sendAnimation", "animation"),
			"send_sticker": ("sendSticker", "sticker"),
		}
		for action, (method, field) in cases.items():
			result = self.run_action(action=action, chat_id="9", **{field: FILE_ID})
			self.assertTrue(result["success"], (action, result))
			self.assertEqual(self.payload(method)[field], FILE_ID)

	def test_caption_thread_silent_and_reply(self):
		self.run_action(
			action="send_video",
			chat_id="9",
			video="https://cdn.test/v.mp4",
			caption="hi",
			message_thread_id=5,
			disable_notification=True,
			reply_to_message_id=3,
			supports_streaming=True,
			parse_mode="HTML",
		)
		p = self.payload("sendVideo")
		self.assertEqual(p["caption"], "hi")
		self.assertEqual(p["message_thread_id"], 5)
		self.assertTrue(p["disable_notification"])
		self.assertEqual(p["reply_parameters"]["message_id"], 3)
		self.assertTrue(p["supports_streaming"])
		self.assertEqual(p["parse_mode"], "HTML")

	def test_audio_title_performer(self):
		self.run_action(action="send_audio", chat_id="9", audio=FILE_ID, title="T", performer="P")
		p = self.payload("sendAudio")
		self.assertEqual((p["title"], p["performer"]), ("T", "P"))

	def test_missing_source_and_chat(self):
		self.assertIn("required", self.run_action(action="send_voice", chat_id="9")["error"])
		self.assertIn("chat_id", self.run_action(action="send_voice", voice=FILE_ID)["error"])
		self.assertEqual(self.api.calls, [])

	def test_media_group(self):
		items = [
			{"type": "photo", "media": FILE_ID, "caption": "a"},
			{"type": "photo", "media": "https://cdn.test/b.jpg"},
		]
		result = self.run_action(action="send_media_group", chat_id="9", items=items)
		self.assertTrue(result["success"])
		media = self.payload("sendMediaGroup")["media"]
		if isinstance(media, str):
			media = json.loads(media)
		self.assertEqual([m["type"] for m in media], ["photo", "photo"])
		self.assertEqual(media[0]["caption"], "a")

	def test_media_group_validation(self):
		self.assertFalse(
			self.run_action(action="send_media_group", chat_id="9", items=[{"media": FILE_ID}])["success"]
		)
		bad = [{"type": "sticker", "media": FILE_ID}] * 2
		self.assertIn("type", self.run_action(action="send_media_group", chat_id="9", items=bad)["error"])
		self.assertFalse(self.run_action(action="send_media_group", chat_id="9", items="not json")["success"])
		self.assertEqual(self.api.calls, [])

	def test_media_group_items_as_json_string(self):
		items = json.dumps([{"media": FILE_ID}, {"media": FILE_ID}])
		self.assertTrue(self.run_action(action="send_media_group", chat_id="9", items=items)["success"])


class TestMediaSources(Base):
	def test_url_ssrf_rejected(self):
		self.validate.return_value = (False, "Requests to private/internal addresses are not allowed")
		result = self.run_action(action="send_photo", chat_id="9", photo="http://169.254.169.254/x.jpg")
		self.assertFalse(result["success"])
		self.assertIn("URL rejected", result["error"])
		self.assertEqual(self.api.calls, [])

	def test_url_in_album_ssrf_rejected(self):
		self.validate.return_value = (False, "nope")
		items = [{"media": "http://127.0.0.1/a.jpg"}, {"media": FILE_ID}]
		self.assertFalse(self.run_action(action="send_media_group", chat_id="9", items=items)["success"])
		self.assertEqual(self.api.calls, [])

	def test_unrecognised_source(self):
		with patch.object(
			tool.frappe, "db", SimpleNamespace(exists=lambda *a, **k: False, get_value=lambda *a, **k: None)
		):
			result = self.run_action(action="send_document", chat_id="9", document="/etc/passwd")
		self.assertIn("not recognised", result["error"])

	def _file_doc(self, size, mime="application/pdf", name="r.pdf"):
		fd, path = tempfile.mkstemp(suffix=name)
		os.write(fd, b"x" * min(size, 1024))
		os.close(fd)
		self.addCleanup(os.unlink, path)
		doc = SimpleNamespace(get_full_path=lambda: path, content_type=mime)
		patch.object(tool.frappe, "db", SimpleNamespace(exists=lambda *a, **k: True)).start()
		patch.object(tool.frappe, "get_doc", return_value=doc).start()
		return path

	def test_frappe_file_uploaded_multipart(self):
		self._file_doc(10)
		with patch.object(tool.frappe, "has_permission", return_value=True):
			result = self.run_action(action="send_document", chat_id="9", document="abc123")
		self.assertTrue(result["success"], result)
		call = self.api.last("sendDocument")
		name, content, mime = call["files"]["document"]
		self.assertEqual((content, mime), (b"x" * 10, "application/pdf"))
		self.assertNotIn("document", call["payload"])

	def test_frappe_file_permission_denied(self):
		self._file_doc(10)
		with patch.object(tool.frappe, "has_permission", return_value=False):
			result = self.run_action(action="send_document", chat_id="9", document="abc123")
		self.assertIn("permission", result["error"])
		self.assertEqual(self.api.calls, [])

	def test_size_limits(self):
		self._file_doc(10, mime="image/jpeg", name="p.jpg")
		with (
			patch.object(tool.frappe, "has_permission", return_value=True),
			patch.object(tool.os.path, "getsize", return_value=tool.PHOTO_MAX_BYTES + 1),
		):
			photo = self.run_action(action="send_photo", chat_id="9", photo="abc123")
			doc = self.run_action(
				action="send_document", chat_id="9", document="abc123"
			)  # 10MB+1 is fine for a document
		self.assertIn("at most 10 MB", photo["error"])
		self.assertTrue(doc["success"])
		with (
			patch.object(tool.frappe, "has_permission", return_value=True),
			patch.object(tool.os.path, "getsize", return_value=tool.FILE_MAX_BYTES + 1),
		):
			big = self.run_action(action="send_document", chat_id="9", document="abc123")
		self.assertIn("at most 50 MB", big["error"])
		self.assertEqual(len(self.api.of("sendDocument")), 1)

	def test_voice_mime_check(self):
		self._file_doc(10, mime="audio/wav", name="v.wav")
		with patch.object(tool.frappe, "has_permission", return_value=True):
			result = self.run_action(action="send_voice", chat_id="9", voice="abc123")
		self.assertIn("OGG", result["error"])


class TestSimpleActions(Base):
	def test_location(self):
		self.assertTrue(
			self.run_action(action="send_location", chat_id="9", latitude="12.5", longitude=-70)["success"]
		)
		p = self.payload("sendLocation")
		self.assertEqual((p["latitude"], p["longitude"]), (12.5, -70.0))

	def test_location_validation(self):
		self.assertFalse(
			self.run_action(action="send_location", chat_id="9", latitude=91, longitude=0)["success"]
		)
		self.assertFalse(self.run_action(action="send_location", chat_id="9", latitude=1)["success"])

	def test_contact(self):
		self.run_action(
			action="send_contact", chat_id="9", phone_number="+100", first_name="Ann", last_name="Lee"
		)
		p = self.payload("sendContact")
		self.assertEqual((p["phone_number"], p["first_name"], p["last_name"]), ("+100", "Ann", "Lee"))
		self.assertFalse(self.run_action(action="send_contact", chat_id="9", phone_number="+1")["success"])

	def test_reaction_set_and_clear(self):
		self.run_action(action="set_reaction", chat_id="9", message_id="7", emoji="👍", big=True)
		p = self.payload("setMessageReaction")
		self.assertEqual(p["reaction"], [{"type": "emoji", "emoji": "👍"}])
		self.assertEqual((p["message_id"], p["is_big"]), (7, True))
		self.run_action(action="set_reaction", chat_id="9", message_id=7, remove=True)
		self.assertEqual(self.payload("setMessageReaction")["reaction"], [])
		self.assertFalse(self.run_action(action="set_reaction", chat_id="9", emoji="x")["success"])

	def test_chat_action(self):
		self.run_action(
			action="send_chat_action", chat_id="9", chat_action="upload_photo", message_thread_id=4
		)
		p = self.payload("sendChatAction")
		self.assertEqual((p["action"], p["message_thread_id"]), ("upload_photo", 4))
		self.run_action(action="send_chat_action", chat_id="9")
		self.assertEqual(self.payload("sendChatAction")["action"], "typing")
		bad = self.run_action(action="send_chat_action", chat_id="9", chat_action="dance")
		self.assertIn("Unsupported chat action", bad["error"])

	def test_edit_caption(self):
		self.run_action(action="edit_message_caption", chat_id="9", message_id=3, caption="new")
		p = self.payload("editMessageCaption")
		self.assertEqual((p["caption"], p["message_id"]), ("new", 3))
		self.assertFalse(self.run_action(action="edit_message_caption", chat_id="9", message_id=3)["success"])

	def test_edit_reply_markup_set_and_remove(self):
		kb = {"inline_keyboard": [[{"text": "Go", "url": "https://x.test"}]]}
		self.run_action(action="edit_message_reply_markup", chat_id="9", message_id=3, reply_markup=kb)
		self.assertEqual(self.payload("editMessageReplyMarkup")["reply_markup"], kb)
		self.run_action(action="edit_message_reply_markup", chat_id="9", message_id=3)
		self.assertEqual(self.payload("editMessageReplyMarkup")["reply_markup"], {"inline_keyboard": []})
		bad = self.run_action(
			action="edit_message_reply_markup",
			chat_id="9",
			message_id=3,
			reply_markup={"remove_keyboard": True},
		)
		self.assertIn("inline_keyboard", bad["error"])

	def test_pin_unpin_refused_and_never_call_telegram(self):
		for action, kw in (
			("pin_message", {"message_id": 3}),
			("pin_message", {"message_id": 3, "notify": True}),
			("unpin_message", {"message_id": 3}),
			("unpin_message", {}),
		):
			r = self.run_action(action=action, chat_id="9", **kw)
			self.assertEqual(r["error"], "owner_required", action)
			self.assertIn("telegram_admin", r["message"])
		self.assertEqual(self.api.of("pinChatMessage"), [])
		self.assertEqual(self.api.of("unpinChatMessage"), [])

	def test_forward_and_copy(self):
		self.run_action(
			action="forward_message", chat_id="9", from_chat_id="5", message_id=2, message_thread_id=1
		)
		p = self.payload("forwardMessage")
		self.assertEqual(
			(p["chat_id"], p["from_chat_id"], p["message_id"], p["message_thread_id"]), ("9", "5", 2, 1)
		)
		self.run_action(
			action="copy_message",
			chat_id="9",
			from_chat_id="5",
			message_id=2,
			caption="c",
			reply_markup={"inline_keyboard": [[{"text": "a", "url": "https://x.test"}]]},
		)
		p = self.payload("copyMessage")
		self.assertEqual(p["caption"], "c")
		self.assertIn("inline_keyboard", p["reply_markup"])
		self.assertFalse(self.run_action(action="copy_message", chat_id="9", message_id=2)["success"])

	def test_answer_callback_query(self):
		self.run_action(action="answer_callback_query", callback_query_id="cq1", text="ok", show_alert=True)
		p = self.payload("answerCallbackQuery")
		self.assertEqual((p["callback_query_id"], p["text"], p["show_alert"]), ("cq1", "ok", True))
		self.assertFalse(self.run_action(action="answer_callback_query")["success"])

	def test_api_error_redacted(self):
		self.api.queue("setMessageReaction", FakeBotApi.error(f"Bad Request: REACTION_INVALID {TOKEN}", 400))
		result = self.run_action(action="set_reaction", chat_id="9", message_id=1, emoji="x")
		self.assertFalse(result["success"])
		self.assertNotIn(TOKEN, json.dumps(result))


class TestReplyMarkup(Base):
	def test_passthrough_on_text_photo_document(self):
		kb = {
			"inline_keyboard": [
				[{"text": "Open", "url": "https://x.test"}, {"text": "Docs", "url": "tg://resolve?domain=a"}]
			]
		}
		self.run_action(action="send_message", chat_id="9", text="hi", reply_markup=json.dumps(kb))
		self.assertEqual(self.payload("sendMessage")["reply_markup"], kb)
		self.run_action(action="send_photo", chat_id="9", photo=FILE_ID, reply_markup=kb)
		self.assertEqual(self.payload("sendPhoto")["reply_markup"], kb)
		self.run_action(action="send_document", chat_id="9", document=FILE_ID, reply_markup=kb)
		self.assertEqual(self.payload("sendDocument")["reply_markup"], kb)

	def test_reply_keyboard_and_remove_and_force(self):
		r = self.run_action(
			action="send_message",
			chat_id="9",
			text="x",
			reply_markup={"keyboard": [["A", "B"]], "one_time_keyboard": True},
		)
		self.assertTrue(r["success"])
		self.assertEqual(
			self.payload("sendMessage")["reply_markup"]["keyboard"], [[{"text": "A"}, {"text": "B"}]]
		)
		self.run_action(action="send_message", chat_id="9", text="x", reply_markup={"remove_keyboard": True})
		self.assertEqual(self.payload("sendMessage")["reply_markup"], {"remove_keyboard": True})
		self.run_action(action="send_message", chat_id="9", text="x", reply_markup={"force_reply": True})
		self.assertEqual(self.payload("sendMessage")["reply_markup"], {"force_reply": True})

	def test_invalid_markup_rejected_before_any_call(self):
		bad = [
			"{not json",
			{"inline_keyboard": [[{"text": "x", "web_app": {"url": "https://x.test"}}]]},
			{"inline_keyboard": [[{"text": "x", "url": "javascript:alert(1)"}]]},
			{"inline_keyboard": [[{"text": "x", "callback_data": "raw"}]]},  # no gateway signer -> rejected
			{"inline_keyboard": [[{"text": "x"}]]},
			{"inline_keyboard": [[{"text": "x", "url": "https://a.test"}]], "keyboard": [["a"]]},
			{"keyboard": [[{"text": "x", "web_app": {"url": "https://x.test"}}]]},
			{"inline_keyboard": [[{"text": "x", "url": "https://a.test"}] * 9]},
			{"inline_keyboard": "nope"},
		]
		for markup in bad:
			result = self.run_action(action="send_message", chat_id="9", text="x", reply_markup=markup)
			self.assertFalse(result["success"], markup)
		self.assertEqual(self.api.calls, [])

	def test_callback_buttons_are_signed_in_gateway_runs(self):
		key = b"k" * 32
		sign = lambda p: f"{p}|sig"
		out = extra.normalize_reply_markup(
			{"inline_keyboard": [[{"text": "Yes", "callback": "ok:1"}]]}, sign=sign
		)
		self.assertEqual(out["inline_keyboard"][0][0]["callback_data"], "ok:1|sig")
		self.assertTrue(key)

	def test_empty_markup_is_none(self):
		self.assertIsNone(extra.normalize_reply_markup(None))
		self.assertIsNone(extra.normalize_reply_markup(""))


class TestGatewayRun(Base):
	"""Inside a Telegram gateway run the chat is scoped and sends are capped."""

	def setUp(self):
		super().setUp()
		tool.scope.run_gateway.return_value = "GW"
		patch.object(tool.scope, "effective_run_id", return_value="RUN").start()
		patch.object(tool.scope, "current_chat", return_value="111").start()
		self.conf = {"scope": "Current contact", "allowlist": [], "per_run": 20, "per_day": 200}
		patch.object(scope, "settings", side_effect=lambda g: dict(self.conf)).start()
		self.claim = patch.object(tool.scope, "claim_send", return_value=None).start()
		self.release = patch.object(tool.scope, "release_send").start()

	def test_defaults_to_current_chat(self):
		self.assertTrue(self.run_action(action="send_message", text="hi")["success"])
		self.assertEqual(self.payload("sendMessage")["chat_id"], "111")

	def test_model_chat_id_outside_scope_refused_for_every_chat_action(self):
		for action, extra_args in {
			"send_message": {"text": "x"},
			"send_photo": {"photo": FILE_ID},
			"send_voice": {"voice": FILE_ID},
			"send_location": {"latitude": 1, "longitude": 1},
			"set_reaction": {"message_id": 1, "emoji": "x"},
			"delete_message": {"message_id": 1},
			"get_chat_info": {},
			"send_chat_action": {},
			"edit_message_text": {"message_id": 1, "text": "x"},
		}.items():
			out = self.run_action(action=action, chat_id="999", **extra_args)
			self.assertEqual(out["error"], "recipient_not_permitted", action)
		self.assertEqual(self.api.calls, [])

	def test_matching_chat_id_allowed(self):
		self.assertTrue(self.run_action(action="send_message", chat_id="111", text="x")["success"])

	def test_forward_checks_source_chat_too(self):
		out = self.run_action(action="forward_message", chat_id="111", from_chat_id="999", message_id=1)
		self.assertEqual(out["error"], "recipient_not_permitted")
		self.assertEqual(self.api.calls, [])
		self.assertTrue(
			self.run_action(action="copy_message", chat_id="111", from_chat_id="111", message_id=1)["success"]
		)

	def test_allow_list_widens(self):
		self.conf.update(scope="Allow-list", allowlist=["999"])
		self.assertTrue(self.run_action(action="send_message", chat_id="999", text="x")["success"])
		self.assertEqual(
			self.run_action(action="send_message", chat_id="5", text="x")["error"], "recipient_not_permitted"
		)

	def test_gateway_name_arg_ignored_and_webhook_actions_blocked(self):
		for action in ("set_webhook", "delete_webhook", "get_updates"):
			out = self.run_action(action=action, url="https://x.test")
			self.assertEqual(out["error"], "action_not_permitted")
		self.assertEqual(self.api.calls, [])

	def test_cap_refusal_sends_nothing(self):
		self.claim.return_value = json.dumps({"success": False, "error": "send_cap_exceeded"})
		out = self.run_action(action="send_message", text="x")
		self.assertEqual(out["error"], "send_cap_exceeded")
		self.assertEqual(self.api.calls, [])

	def test_only_new_messages_are_counted_and_failures_released(self):
		self.run_action(action="set_reaction", message_id=1, emoji="x")
		self.run_action(action="delete_message", message_id=1)
		self.claim.assert_not_called()
		self.run_action(action="send_message", text="x")
		self.claim.assert_called_once_with("GW", "RUN")
		self.release.assert_not_called()
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: chat not found", 400))
		self.run_action(action="send_message", text="x")
		self.release.assert_called_once_with("GW", "RUN")

	def test_recipient_name_cannot_bypass_scope(self):
		with patch.object(tool, "_resolve_chat_id", return_value="777"):
			out = self.run_action(action="send_message", recipient_name="boss", text="x")
		self.assertEqual(out["error"], "recipient_not_permitted")

	def test_gateway_token_preferred(self):
		seen = []
		real = tool._make_client

		def spy(token, *, timeout=30):
			seen.append(token)
			return real(token, timeout=timeout)

		with (
			patch.object(
				tool, "_gateway_values", return_value={"token": "999:gateway-token-abcdefghijklmnop"}
			),
			patch.object(tool, "_make_client", side_effect=spy),
		):
			self.run_action(action="send_message", text="x")
		self.assertEqual(seen, ["999:gateway-token-abcdefghijklmnop"])


class TestLegacyPath(Base):
	def test_non_gateway_run_keeps_explicit_chat_id(self):
		self.assertTrue(self.run_action(action="send_message", chat_id="5", text="x")["success"])

	def test_unknown_action_lists_new_actions(self):
		err = self.run_action(action="nope")["error"]
		for name in (
			"send_voice",
			"send_media_group",
			"set_reaction",
			"copy_message",
			"answer_callback_query",
		):
			self.assertIn(name, err)


if __name__ == "__main__":
	unittest.main()
