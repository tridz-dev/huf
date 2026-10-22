"""Telegram message templates against the fake Bot API (doctype access mocked)."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from huf.ai import telegram_templates as tt
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi


def tpl(**kw):
	base = {"template_name": "t", "is_active": 1, "parse_mode": "HTML", "body": "Hi {{name}}", "media_type": "none",
		"media": "", "buttons_json": "", "variables": [], "gateway": ""}
	base.update(kw)
	return base


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		client = TelegramBotClient(TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None)
		self.sender = TelegramSender(client)
		self.touched = []
		self.data = {}
		for p in (
			mock.patch.object(tt, "_load", lambda n: self.data.get(n)),
			mock.patch.object(tt, "_touch", self.touched.append),
			mock.patch.object(tt, "_file_bytes", lambda u: ("a.pdf", b"PDF")),
		):
			p.start()
			self.addCleanup(p.stop)

	def put(self, **kw):
		self.data["t"] = tpl(**kw)


class TestRender(Base):
	def test_substitution_defaults_and_override(self):
		self.put(body="{{greet}} {{ name }}!", variables=[{"variable": "greet", "default_value": "Hello"}])
		r = tt.render_template("t", {"name": "Ann"})
		self.assertEqual(r.text, "Hello Ann!")
		self.assertEqual(tt.render_template("t", {"name": "A", "greet": "Yo"}).text, "Yo A!")

	def test_missing_reported_not_raised_strict_raises(self):
		self.put(body="a {{x}} b {{y}} {{x}}")
		r = tt.render_template("t", {})
		self.assertEqual((r.text, r.missing), ("a  b  ", ["x", "y"]))
		with self.assertRaises(tt.TemplateError) as cm:
			tt.render_template("t", {}, strict=True)
		self.assertEqual(cm.exception.missing, ["x", "y"])

	def test_html_injection_escaped_body_trusted(self):
		self.put(body="<b>{{x}}</b>")
		self.assertEqual(tt.render_template("t", {"x": "<b>&"}).text, "<b>&lt;b&gt;&amp;</b>")

	def test_markdownv2_specials_escaped(self):
		self.put(parse_mode="MarkdownV2", body="*{{x}}*")
		self.assertEqual(tt.render_template("t", {"x": "a_b.c!"}).text, "*a\\_b\\.c\\!*")

	def test_plain_not_escaped_and_gateway_mode_inherited(self):
		self.put(parse_mode="Plain", body="{{x}}")
		self.assertEqual(tt.render_template("t", {"x": "<b>"}).text, "<b>")
		self.put(parse_mode="", body="{{x}}")
		gw = SimpleNamespace(name="g", telegram_parse_mode="MarkdownV2")
		self.assertEqual(tt.render_template("t", {"x": "a."}, gw).parse_mode, "MarkdownV2")

	def test_not_found_inactive_wrong_gateway(self):
		with self.assertRaises(tt.TemplateError):
			tt.render_template("nope")
		self.put(is_active=0)
		with self.assertRaises(tt.TemplateError):
			tt.render_template("t", {"name": "a"})
		self.put(gateway="g1")
		with self.assertRaises(tt.TemplateError):
			tt.render_template("t", {"name": "a"}, SimpleNamespace(name="g2"))

	def test_length_errors(self):
		self.put(body="x" * 4097)
		self.assertTrue(tt.render_template("t").errors)
		self.put(body="")
		self.assertTrue(tt.render_template("t").errors)

	def test_buttons_valid_url_and_variable(self):
		self.put(buttons_json='{"rows": [[{"text": "Go {{name}}", "url": "https://x.io/{{name}}"}]]}')
		r = tt.render_template("t", {"name": 'A"b'})
		self.assertEqual(r.errors, [])
		btn = r.reply_markup["inline_keyboard"][0][0]
		self.assertEqual(btn["text"], 'Go A"b')

	def test_buttons_callback_needs_signer(self):
		self.put(buttons_json='{"rows": [[{"text": "Yes", "callback": "yes"}]]}')
		self.assertTrue(any("signer" in e for e in tt.render_template("t", {"name": "a"}).errors))
		r = tt.render_template("t", {"name": "a"}, sign=lambda p: "S" + p)
		self.assertEqual(r.errors, [])
		self.assertTrue(r.reply_markup["inline_keyboard"][0][0]["callback_data"].startswith("Sb:"))

	def test_buttons_invalid(self):
		self.put(buttons_json="{not json")
		self.assertTrue(tt.render_template("t", {"name": "a"}).errors)

	def test_media_sources(self):
		self.put(media_type="photo", media="/files/a.jpg")
		self.assertEqual(tt.render_template("t", {"name": "a"}).media, {"type": "photo", "source": "file_url", "value": "/files/a.jpg"})
		self.put(media_type="photo", media="https://x/y.jpg")
		self.assertEqual(tt.render_template("t", {"name": "a"}).media["source"], "url")
		self.put(media_type="voice", media="AgADfileid")
		self.assertEqual(tt.render_template("t", {"name": "a"}).media["source"], "file_id")
		self.put(media_type="bogus", media="AgAD")
		self.assertTrue(tt.render_template("t", {"name": "a"}).errors)


class TestPreviewList(Base):
	def test_preview(self):
		self.put(buttons_json='{"rows": [[{"text": "Yes", "callback": "yes"}]]}')
		p = tt.preview_template("t", {"name": "Z"})
		self.assertEqual(p["text"], "Hi Z")
		self.assertEqual(p["errors"], [])
		self.assertEqual(json.loads(p["markup_json"])["inline_keyboard"][0][0]["text"], "Yes")
		self.assertEqual(self.api.calls, [])

	def test_list_filters_inactive(self):
		rows = [{"name": "a", "is_active": 1}, {"name": "b", "is_active": 0}]
		with mock.patch.object(tt, "_list_rows", lambda g: rows):
			self.assertEqual([r["name"] for r in tt.list_templates("g")], ["a"])


class TestSend(Base):
	def test_text_only_with_markup_and_options(self):
		self.put(buttons_json='{"rows": [[{"text": "S", "url": "https://x.io"}]]}')
		gw = SimpleNamespace(name="g", telegram_silent_replies=1, telegram_protect_content=1)
		out = tt.send_template(gw, 5, "t", {"name": "<b>"}, thread_id=7, reply_to=3, sender=self.sender)
		call = self.api.last("sendMessage")["payload"]
		self.assertEqual(call["text"], "Hi &lt;b&gt;")
		self.assertEqual(call["parse_mode"], "HTML")
		self.assertEqual(call["message_thread_id"], 7)
		self.assertTrue(call["disable_notification"] and call["protect_content"])
		self.assertIn("inline_keyboard", call["reply_markup"])
		self.assertEqual(out["template"], "t")
		self.assertEqual(len(out["message_ids"]), 1)
		self.assertEqual(self.touched, ["t"])

	def test_media_with_caption(self):
		self.put(media_type="document", media="/files/a.pdf")
		out = tt.send_template(None, 5, "t", {"name": "A"}, sender=self.sender)
		self.assertEqual(len(self.api.calls), 1)
		call = self.api.last("sendDocument")
		self.assertEqual(call["payload"]["caption"], "Hi A")
		self.assertEqual(call["payload"]["parse_mode"], "HTML")
		self.assertIn("document", call["files"])
		self.assertEqual(len(out["message_ids"]), 1)

	def test_long_text_media_then_text_with_markup(self):
		self.put(media_type="photo", media="https://x/y.jpg", body="y" * 1500,
			buttons_json='{"rows": [[{"text": "S", "url": "https://x.io"}]]}')
		tt.send_template(None, 5, "t", sender=self.sender)
		photo = self.api.last("sendPhoto")["payload"]
		self.assertNotIn("caption", photo)
		self.assertNotIn("reply_markup", photo)
		self.assertIn("reply_markup", self.api.last("sendMessage")["payload"])

	def test_sticker_text_separate(self):
		self.put(media_type="sticker", media="STICKERID")
		tt.send_template(None, 5, "t", {"name": "A"}, sender=self.sender)
		self.assertNotIn("caption", self.api.last("sendSticker")["payload"])
		self.assertEqual(self.api.last("sendMessage")["payload"]["text"], "Hi A")

	def test_missing_refuses_unless_allowed(self):
		self.put()
		with self.assertRaises(tt.TemplateError):
			tt.send_template(None, 5, "t", {}, sender=self.sender)
		self.assertEqual(self.api.calls, [])
		out = tt.send_template(None, 5, "t", {}, sender=self.sender, allow_missing=True)
		self.assertEqual(out["missing"], ["name"])

	def test_parse_error_falls_back_plain(self):
		self.put(body="Hi <b>{{name}}</b>")
		self.api.queue("sendMessage", FakeBotApi.error("Bad Request: can't parse entities", 400))
		tt.send_template(None, 5, "t", {"name": "A"}, sender=self.sender)
		last = self.api.last("sendMessage")["payload"]
		self.assertNotIn("parse_mode", last)
		self.assertEqual(last["text"], "Hi A")

	def test_touch_failure_ignored(self):
		self.put()
		with mock.patch.object(tt, "_touch", side_effect=RuntimeError):
			tt.send_template(None, 5, "t", {"name": "A"}, sender=self.sender)


if __name__ == "__main__":
	unittest.main()
