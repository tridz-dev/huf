"""Gateway reply settings (silent, protect, parse mode, link previews) reach the FULL outgoing payload of
every reply kind, and template sends use the same sender helper."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai import telegram_templates as tt
from huf.ai.gateway_adapters import telegram_pipeline as pipe
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import gateway_sender_options, sender_for_gateway
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi

NO_PREVIEW = {"is_disabled": True}


def gateway(**kw):
	values = {
		"name": "GW",
		"telegram_parse_mode": "HTML",
		"telegram_silent_replies": 0,
		"telegram_protect_content": 0,
		"preview_url": "Default (off)",
	}
	values.update(kw)
	return SimpleNamespace(**values, get=lambda k, d=None: values.get(k, d))


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		self.client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None
		)

	def sender(self, **kw):
		return sender_for_gateway(self.client, gateway(**kw))

	def payloads(self, method="sendMessage"):
		return [c["payload"] for c in self.api.of(method)]


class TestOptions(Base):
	def test_defaults(self):
		self.assertEqual(
			gateway_sender_options(gateway()),
			{"parse_mode": "HTML", "silent": False, "protect": False, "link_previews": False},
		)

	def test_mapping_of_every_setting(self):
		o = gateway_sender_options(
			gateway(
				telegram_parse_mode="MarkdownV2",
				telegram_silent_replies=1,
				telegram_protect_content=1,
				preview_url="On",
			)
		)
		self.assertEqual(o, {"parse_mode": "MarkdownV2", "silent": True, "protect": True, "link_previews": True})
		self.assertEqual(gateway_sender_options(gateway(telegram_parse_mode="Plain"))["parse_mode"], "")
		self.assertFalse(gateway_sender_options(gateway(preview_url="Off"))["link_previews"])


class TestReplyPayloads(Base):
	def test_text_reply_default_settings(self):
		pipe.send_parts_with(self.sender(), 5, ["Hello **world**"], thread_id=3, reply_to=9)
		self.assertEqual(
			self.payloads(),
			[
				{
					"chat_id": 5,
					"message_thread_id": 3,
					"reply_parameters": {"message_id": 9, "allow_sending_without_reply": True},
					"text": "Hello <b>world</b>",
					"parse_mode": "HTML",
					"link_preview_options": NO_PREVIEW,
				}
			],
		)

	def test_text_reply_all_settings_on(self):
		s = self.sender(telegram_silent_replies=1, telegram_protect_content=1, preview_url="On")
		pipe.send_parts_with(s, 5, ["see https://x.io"])
		self.assertEqual(
			self.payloads(),
			[
				{
					"chat_id": 5,
					"text": "see https://x.io",
					"parse_mode": "HTML",
					"disable_notification": True,
					"protect_content": True,
				}
			],
		)

	def test_plain_parse_mode_sends_no_parse_mode(self):
		pipe.send_parts_with(self.sender(telegram_parse_mode="Plain"), 5, ["a *b* <c>"])
		self.assertEqual(
			self.payloads(), [{"chat_id": 5, "text": "a *b* <c>", "link_preview_options": NO_PREVIEW}]
		)

	def test_markdown_v2_parse_mode(self):
		pipe.send_parts_with(self.sender(telegram_parse_mode="MarkdownV2"), 5, ["Hi **there**"])
		(payload,) = self.payloads()
		self.assertEqual(payload["parse_mode"], "MarkdownV2")
		self.assertEqual(payload["text"], "Hi *there*")

	def test_long_split_reply_every_chunk_carries_settings(self):
		s = self.sender(telegram_silent_replies=1, telegram_protect_content=1)
		text = "\n\n".join(["word " * 300] * 4)
		pipe.send_parts_with(s, 5, [text], reply_to=9)
		sent = self.payloads()
		self.assertGreater(len(sent), 1)
		for i, p in enumerate(sent):
			self.assertLessEqual(len(p["text"]), 4096)
			expected_keys = {
				"chat_id", "text", "parse_mode", "disable_notification", "protect_content", "link_preview_options",
			} | ({"reply_parameters"} if i == 0 else set())
			self.assertEqual(set(p), expected_keys)
			self.assertEqual(
				(p["disable_notification"], p["protect_content"], p["link_preview_options"]),
				(True, True, NO_PREVIEW),
			)

	def test_buttons_ride_on_last_part_with_settings(self):
		markup = {"inline_keyboard": [[{"text": "Yes", "callback_data": "y"}]]}
		s = self.sender(telegram_silent_replies=1)
		pipe.send_parts_with(s, 5, ["one", "two"], markup=markup)
		self.assertEqual(
			self.payloads(),
			[
				{
					"chat_id": 5,
					"text": "one",
					"parse_mode": "HTML",
					"disable_notification": True,
					"link_preview_options": NO_PREVIEW,
				},
				{
					"chat_id": 5,
					"text": "two",
					"parse_mode": "HTML",
					"disable_notification": True,
					"link_preview_options": NO_PREVIEW,
					"reply_markup": markup,
				},
			],
		)

	def test_media_reply_payload(self):
		s = self.sender(telegram_silent_replies=1, telegram_protect_content=1)
		s.send_media("photo", 5, "https://x.io/a.jpg", caption="A **cap**", reply_to=9)
		self.assertEqual(
			self.payloads("sendPhoto"),
			[
				{
					"chat_id": 5,
					"reply_parameters": {"message_id": 9, "allow_sending_without_reply": True},
					"disable_notification": True,
					"protect_content": True,
					"photo": "https://x.io/a.jpg",
					"caption": "A <b>cap</b>",
					"parse_mode": "HTML",
				}
			],
		)

	def test_explicit_flags_only_add(self):
		s = self.sender(telegram_silent_replies=1, telegram_protect_content=1)
		s.send_text(5, "x", silent=False, protect=False)
		p = self.payloads()[0]
		self.assertTrue(p["disable_notification"] and p["protect_content"])
		t = self.sender()
		t.send_text(5, "y", silent=True, protect=True, link_preview=True)
		p = self.payloads()[1]
		self.assertTrue(p["disable_notification"] and p["protect_content"])

	def test_explicit_link_preview_false_wins_over_gateway_on(self):
		self.sender(preview_url="On").send_text(5, "x", link_preview=False)
		self.assertEqual(self.payloads()[0]["link_preview_options"], NO_PREVIEW)

	def test_pipeline_build_sender_applies_gateway(self):
		adapter = SimpleNamespace(client=self.client)
		s = pipe.build_sender(adapter, gateway(telegram_silent_replies=1, preview_url="On"))
		self.assertEqual((s.silent, s.protect, s.link_previews, s.parse_mode), (True, False, True, "HTML"))
		legacy = pipe.build_sender(adapter)
		self.assertEqual((legacy.silent, legacy.protect, legacy.parse_mode), (False, False, "HTML"))


class TestTemplateUsesSameHelper(Base):
	def test_template_payload_matches_reply_settings(self):
		data = {
			"t": {
				"template_name": "t", "is_active": 1, "parse_mode": "HTML", "body": "Hi {{name}}",
				"media_type": "none", "media": "", "buttons_json": "", "variables": [], "gateway": "",
			}
		}
		gw = gateway(telegram_silent_replies=1, telegram_protect_content=1, preview_url="Off")
		with mock.patch.object(tt, "_load", lambda n: data.get(n)), mock.patch.object(tt, "_touch", lambda n: None):
			tt.send_template(gw, 5, "t", {"name": "Ann"}, sender=self.sender())
			(via_template,) = self.payloads()
			self.api.calls.clear()
			pipe.send_parts_with(self.sender(telegram_silent_replies=1, telegram_protect_content=1), 5, ["Hi Ann"])
			(via_reply,) = self.payloads()
		self.assertEqual(via_template, via_reply)
		self.assertEqual(
			via_template,
			{
				"chat_id": 5,
				"text": "Hi Ann",
				"parse_mode": "HTML",
				"disable_notification": True,
				"protect_content": True,
				"link_preview_options": NO_PREVIEW,
			},
		)


if __name__ == "__main__":
	unittest.main()
