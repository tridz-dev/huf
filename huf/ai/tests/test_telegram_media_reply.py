"""Agent ``telegram-media`` block: parse/strip/validate, resolution, albums, sends, pipeline integration."""

from __future__ import annotations

import json
import unittest

from huf.ai.gateway_adapters import telegram_media_reply as mr
from huf.ai.gateway_adapters import telegram_pipeline as tp
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayAttachment, GatewayReply
from huf.ai.tests.telegram_fakes import SECRET, TOKEN, FakeBotApi

CHAT = 111


class Cache:
	def __init__(self):
		self.d = {}

	def set_value(self, key, value, expires_in_sec=None):
		self.d[key] = value

	def get_value(self, key):
		return self.d.get(key)

	def delete_value(self, key):
		self.d.pop(key, None)


def block(*items) -> str:
	return "```telegram-media\n" + json.dumps({"items": list(items)}) + "\n```"


def photo(value="AgAC", **kw):
	return {"type": "photo", "source": "file_id", "value": value, **kw}


def files(url):
	if url == "/private/files/missing.png":
		raise ValueError("file not found")
	return "a.png", b"PNGDATA"


def url_ok(url):
	return (False, "private address") if "169.254" in url else (True, "")


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.adapter = TelegramGatewayAdapter({"token": TOKEN, "webhook_secret": SECRET}, http_post=self.api.http_post,
			http_get=self.api.http_get, download_attachments=False)
		self.sender = self.adapter.sender

	def send(self, items, **kw):
		return mr.send_media_items(self.sender, CHAT, items, resolve_file=files, check_url=url_ok, **kw)


class TestParse(unittest.TestCase):
	def test_extract_strips_block(self):
		visible, items, errors = mr.extract("Here.\n\n" + block(photo(caption="c")) + "\n\nBye")
		self.assertEqual(visible, "Here.\n\nBye")
		self.assertEqual(items, [{"type": "photo", "source": "file_id", "value": "AgAC", "caption": "c"}])
		self.assertEqual(errors, [])

	def test_invalid_json_stripped_no_items(self):
		visible, items, errors = mr.extract("hi\n```telegram-media\n{nope\n```")
		self.assertEqual((visible, items), ("hi", []))
		self.assertTrue(errors)

	def test_limits(self):
		items, errors = mr.validate({"items": [photo(str(i)) for i in range(12)]})
		self.assertEqual(len(items), 10)
		self.assertTrue(any("too many" in e for e in errors))
		items, errors = mr.validate({"items": [photo(caption="x" * 2000)]})
		self.assertEqual(len(items[0]["caption"]), 1024)

	def test_gif_alias_spoiler_and_caption_rules(self):
		items, _ = mr.validate({"items": [{"type": "gif", "source": "url", "value": "https://a/b.gif", "has_spoiler": True},
			{"type": "sticker", "source": "file_id", "value": "s", "caption": "ignored", "has_spoiler": True}]})
		self.assertEqual(items[0]["type"], "animation")
		self.assertTrue(items[0]["has_spoiler"])
		self.assertNotIn("caption", items[1])
		self.assertNotIn("has_spoiler", items[1])

	def test_text_types_validation(self):
		items, errors = mr.validate({"items": [
			{"type": "location", "source": "text", "latitude": 200, "longitude": 1},
			{"type": "contact", "source": "text", "value": {"phone_number": "+1", "first_name": "A"}},
			{"type": "venue", "source": "text", "latitude": 1, "longitude": 2, "title": "T"},
			{"type": "poll", "source": "text", "question": "Q?", "options": ["a"]},
			{"type": "poll", "source": "text", "question": "Q?", "options": ["a", "b"]},
			{"type": "dice", "source": "text", "emoji": "x"},
			{"type": "bogus", "source": "text"}]})
		self.assertEqual([i["type"] for i in items], ["contact", "poll", "dice"])
		self.assertEqual(items[2]["emoji"], "🎲")
		self.assertEqual(len(errors), 4)


class TestSend(Base):
	def test_single_photo_with_extras(self):
		out = self.send([photo(caption="hi", has_spoiler=True)], thread_id=7, reply_to=5)
		call = self.api.last("sendPhoto")["payload"]
		self.assertEqual((call["photo"], call["caption"], call["has_spoiler"], call["message_thread_id"]), ("AgAC", "hi", True, 7))
		self.assertEqual(call["reply_parameters"]["message_id"], 5)
		self.assertEqual((len(out.sent_ids), out.errors), (1, []))

	def test_file_url_uploads_bytes_and_permission_error(self):
		out = self.send([{"type": "document", "source": "file_url", "value": "/private/files/a.pdf"},
			{"type": "audio", "source": "file_url", "value": "/private/files/missing.png"}])
		self.assertEqual(len(self.api.of("sendDocument")), 1)
		self.assertEqual(self.api.of("sendAudio"), [])
		self.assertEqual(self.api.last("sendDocument")["files"]["document"][1], b"PNGDATA")
		self.assertEqual(len(out.errors), 1)
		self.assertIn("not found", out.errors[0])

	def test_size_cap_rejected(self):
		big = lambda u: ("big.png", b"0" * (mr.MAX_PHOTO_BYTES + 1))  # noqa: E731
		out = mr.send_media_items(self.sender, CHAT, [{"type": "photo", "source": "file_url", "value": "/f"}],
			resolve_file=big, check_url=url_ok)
		self.assertEqual(self.api.calls, [])
		self.assertIn("limit", out.errors[0])

	def test_url_ssrf_guard(self):
		out = self.send([{"type": "photo", "source": "url", "value": "http://169.254.169.254/x.png"},
			{"type": "photo", "source": "url", "value": "https://ok.example/x.png"}])
		self.assertEqual(self.api.last("sendPhoto")["payload"]["photo"], "https://ok.example/x.png")
		self.assertEqual(self.api.of("sendMediaGroup"), [])  # the rejected item is dropped, one photo left
		self.assertEqual(len(self.api.of("sendPhoto")), 1)
		self.assertIn("private address", out.errors[0])

	def test_album_for_photos_and_videos(self):
		out = self.send([photo("a", caption="one"), {"type": "video", "source": "file_id", "value": "b"}, photo("c")])
		self.assertEqual(len(self.api.of("sendMediaGroup")), 1)
		media = self.api.last("sendMediaGroup")["payload"]["media"]
		self.assertEqual([m["type"] for m in media], ["photo", "video", "photo"])
		self.assertEqual(len(out.sent_ids), 2)  # fake returns 2 ids

	def test_incompatible_types_not_grouped(self):
		self.send([photo("a"), {"type": "document", "source": "file_id", "value": "d"}, photo("b")])
		self.assertEqual(self.api.of("sendMediaGroup"), [])
		self.assertEqual((len(self.api.of("sendPhoto")), len(self.api.of("sendDocument"))), (2, 1))

	def test_documents_group_and_over_ten_split(self):
		docs = [{"type": "document", "source": "file_id", "value": str(i)} for i in range(10)]
		self.send(docs)
		self.assertEqual(len(self.api.of("sendMediaGroup")), 1)
		self.assertEqual(len(self.api.last("sendMediaGroup")["payload"]["media"]), 10)

	def test_text_kinds(self):
		self.send([
			{"type": "location", "source": "text", "latitude": 1.5, "longitude": 2.5},
			{"type": "venue", "source": "text", "latitude": 1, "longitude": 2, "title": "Cafe", "address": "Road"},
			{"type": "contact", "source": "text", "phone_number": "+1", "first_name": "Al"},
			{"type": "poll", "source": "text", "question": "Q?", "options": ["a", "b"], "is_anonymous": False},
			{"type": "dice", "source": "text", "emoji": "🎯"},
		])
		self.assertEqual(self.api.last("sendLocation")["payload"]["latitude"], 1.5)
		self.assertEqual(self.api.last("sendVenue")["payload"]["title"], "Cafe")
		self.assertEqual(self.api.last("sendContact")["payload"]["first_name"], "Al")
		poll = self.api.last("sendPoll")["payload"]
		self.assertEqual((poll["options"], poll["is_anonymous"]), ([{"text": "a"}, {"text": "b"}], False))
		self.assertEqual(self.api.last("sendDice")["payload"]["emoji"], "🎯")

	def test_api_failure_collected_not_raised(self):
		self.api.queue("sendPhoto", self.api.error("Bad Request: wrong file identifier", 400))
		out = self.send([photo("bad"), {"type": "voice", "source": "file_id", "value": "v"}])
		self.assertEqual(len(out.sent_ids), 1)
		self.assertEqual(len(out.errors), 1)
		self.assertNotIn(TOKEN, out.errors[0])
		self.assertTrue(mr.failure_note(out.errors).startswith("(Could not send 1 attachment"))


class TestPipeline(Base):
	def setUp(self):
		super().setUp()
		mr._LOCAL.d.clear()

	def test_make_parts_strips_and_media_goes_first(self):
		parts = tp.make_parts("Report ready.\n" + block(photo(caption="chart")))
		self.assertEqual(parts, ["Report ready."])
		tp.send_parts_with(self.sender, CHAT, parts, media=True, reply_to=9)
		methods = [c["method"] for c in self.api.calls]
		self.assertEqual(methods, ["sendPhoto", "sendMessage"])
		self.assertEqual(self.api.of("sendMessage")[0]["payload"].get("reply_parameters"), None)

	def test_media_only_reply_sends_no_text(self):
		parts = tp.make_parts(block(photo()))
		self.assertTrue(mr.is_media_only(parts[0]))
		res = tp.send_parts_with(self.sender, CHAT, parts, media=True)
		self.assertEqual([c["method"] for c in self.api.calls], ["sendPhoto"])
		self.assertTrue(res.provider_message_id)

	def test_media_failure_keeps_text_and_adds_note(self):
		self.api.queue("sendPhoto", self.api.error("Bad Request: wrong file identifier", 400))
		parts = tp.make_parts("The answer.\n" + block(photo("bad")))
		tp.send_parts_with(self.sender, CHAT, parts, media=True)
		texts = [c["payload"]["text"] for c in self.api.of("sendMessage")]
		self.assertEqual(texts[0], "The answer.")
		self.assertIn("Could not send 1 attachment", texts[-1])

	def test_media_sent_once_across_retry(self):
		parts = tp.make_parts("Hello.\n" + block(photo()))
		self.api.queue("sendMessage", self.api.error("Bad Gateway", 502))
		with self.assertRaises(tp.TelegramPartsError):
			tp.send_parts_with(self.sender, CHAT, parts, media=True)
		tp.send_parts_with(self.sender, CHAT, parts, media=True)
		self.assertEqual(len(self.api.of("sendPhoto")), 1)

	def test_buttons_and_media_coexist(self):
		buttons = "```telegram-buttons\n" + json.dumps({"rows": [[{"text": "Ok", "callback": "ok"}]]}) + "\n```"
		parts = tp.make_parts("Pick.\n" + block(photo()) + "\n" + buttons)
		self.assertEqual(parts, ["Pick."])
		self.assertIsNotNone(mr.take_items(parts))

	def test_no_block_unchanged(self):
		self.assertEqual(tp.make_parts("plain"), ["plain"])


class TestAdapterSendReply(Base):
	def test_attachments_then_text_with_thread(self):
		reply = GatewayReply(conversation_id=str(CHAT), text="caption text", thread_id="42", attachments=(
			GatewayAttachment(file_id="F1", kind="photo"), GatewayAttachment(url="https://x/a.gif", mime_type="image/gif")))
		out = self.adapter.send_reply(reply)
		self.assertEqual([c["method"] for c in self.api.calls], ["sendPhoto", "sendAnimation", "sendMessage"])
		self.assertEqual(self.api.last("sendAnimation")["payload"]["message_thread_id"], 42)
		self.assertTrue(out.provider_message_id)


if __name__ == "__main__":
	unittest.main()


class TestFileAllowList(unittest.TestCase):
	def doc(self, private, dt=None, dn=None):
		from types import SimpleNamespace

		return SimpleNamespace(is_private=private, attached_to_doctype=dt, attached_to_name=dn)

	def test_public_and_inbound_for_this_chat_only(self):
		from unittest.mock import MagicMock, patch

		self.assertTrue(mr._file_allowed_for_chat(self.doc(0), CHAT))
		self.assertFalse(mr._file_allowed_for_chat(self.doc(1), CHAT))
		self.assertFalse(mr._file_allowed_for_chat(self.doc(1, "ToDo", "T1"), CHAT))
		import frappe

		with patch.object(frappe, "db", MagicMock(**{"get_value.return_value": str(CHAT)})):
			self.assertTrue(mr._file_allowed_for_chat(self.doc(1, "Gateway Event", "E1"), CHAT))
			self.assertFalse(mr._file_allowed_for_chat(self.doc(1, "Gateway Event", "E1"), 999))

	def test_default_resolver_refuses_private_file(self):
		from unittest.mock import MagicMock, patch

		import frappe

		d = MagicMock(is_private=1, attached_to_doctype=None, attached_to_name=None)
		with patch.object(frappe, "db", MagicMock(**{"get_value.return_value": "F1"})), patch.object(frappe, "get_doc", return_value=d):
			with self.assertRaisesRegex(ValueError, "not allowed"):
				mr.default_resolve_file("/private/files/secret.pdf", CHAT)
		d.get_content.assert_not_called()
