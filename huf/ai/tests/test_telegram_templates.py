"""Telegram message templates against the fake Bot API (doctype access mocked)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from huf.ai import telegram_templates as tt
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi

FIXTURES = json.loads(
	(
		Path(__file__).resolve().parents[3]
		/ "frontend/src/components/telegram/templates/parity.fixtures.json"
	).read_text()
)


def tpl(**kw):
	base = {
		"template_name": "t",
		"is_active": 1,
		"parse_mode": "HTML",
		"body": "Hi {{name}}",
		"media_type": "none",
		"media": "",
		"buttons_json": "",
		"variables": [],
		"gateway": "",
	}
	base.update(kw)
	return base


class Base(unittest.TestCase):
	def setUp(self):
		self.api = FakeBotApi()
		client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None
		)
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
		self.assertEqual((r.text, r.missing), ("a  b", ["x", "y"]))
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
		self.assertEqual(
			tt.render_template("t", {"name": "a"}).media,
			{"type": "photo", "source": "file_url", "value": "/files/a.jpg"},
		)
		self.put(media_type="photo", media="https://x/y.jpg")
		self.assertEqual(tt.render_template("t", {"name": "a"}).media["source"], "url")
		self.put(media_type="voice", media="AgADfileid")
		self.assertEqual(tt.render_template("t", {"name": "a"}).media["source"], "file_id")
		self.put(media_type="bogus", media="AgAD")
		self.assertTrue(tt.render_template("t", {"name": "a"}).errors)


class TestParity(Base):
	"""Shared fixtures: previewModel.test.ts runs the SAME cases against the frontend preview."""

	def test_fixtures(self):
		for case in FIXTURES:
			with self.subTest(case["id"]):
				self.data["t"] = tpl(**case["template"])
				r = tt.render_template("t", case["values"])
				self.assertEqual((r.text, r.missing, r.split), (case["text"], case["missing"], case["split"]))

	def test_preview_and_send_use_the_same_render(self):
		self.put(
			body='<a href="{{u}}">{{n}}</a>', buttons_json='{"rows": [[{"text": "Go", "url": "{{u}}"}]]}'
		)
		vals = {"u": "https://x.io/a?b=1", "n": "<Ann>"}
		preview = tt.preview_template("t", vals)
		tt.send_template(None, 5, "t", vals, sender=self.sender, sign=lambda p: p)
		sent = self.api.last("sendMessage")["payload"]
		self.assertEqual(sent["text"], preview["text"])
		self.assertEqual(json.dumps(sent["reply_markup"], sort_keys=True), preview["markup_json"])

	def test_examples_fill_preview_only_when_asked(self):
		self.put(body="{{n}}", variables=[{"variable": "n", "example": "Sample"}])
		self.assertEqual(tt.preview_template("t", {})["missing"], ["n"])
		out = tt.preview_template("t", {}, examples=True)
		self.assertEqual((out["text"], out["missing"]), ("Sample", []))

	def test_unsaved_values_preview_matches_saved(self):
		self.put(body="Hi {{name}}", variables=[{"variable": "name", "example": "Ann"}])
		self.assertEqual(
			tt.preview_values(self.data["t"], {}),
			tt.preview_template("t", {}, examples=True) | {"template": ""},
		)


class TestSubstitutionSafety(Base):
	CASES = [
		# (body, value, expected text)
		('<a href="{{v}}">x</a>', 'a" onclick="z', '<a href="a&quot; onclick=&quot;z">x</a>'),
		("{{v}}", 'a" b', 'a" b'),
		('<a href="?q={{v|url}}">x</a>', "a&b=c", '<a href="?q=a%26b%3Dc">x</a>'),
		("{{ v | url }}", "ü/ ", "%C3%BC%2F%20"),
	]

	def test_table(self):
		for body, value, want in self.CASES:
			with self.subTest(body=body):
				self.put(body=body)
				self.assertEqual(tt.render_template("t", {"v": value}).text, want)

	def test_button_url_values(self):
		self.put(buttons_json='{"rows": [[{"text": "Go", "url": "https://x.io/?q={{q|url}}&k={{k}}"}]]}')
		r = tt.render_template("t", {"q": "a&b=c", "k": "1"})
		self.assertEqual(r.errors, [])
		self.assertEqual(
			r.reply_markup,
			{"inline_keyboard": [[{"text": "Go", "url": "https://x.io/?q=a%26b%3Dc&k=1"}]]},
		)

	def test_whole_url_variable_in_web_app_and_strict_send_validation(self):
		self.put(buttons_json='{"rows": [[{"text": "App", "web_app": "{{u}}"}]]}')
		ok = tt.render_template("t", {"u": "https://app.io/x"})
		self.assertEqual(ok.reply_markup["inline_keyboard"][0][0]["web_app"], {"url": "https://app.io/x"})
		bad = tt.render_template("t", {"u": "http://insecure"})
		self.assertTrue(bad.errors)
		self.assertTrue(tt.render_template("t", {}).errors)

	def test_variable_grammar_is_identifiers_only(self):
		self.put(body="{{a.b}} {{a-b}} {{ok_1}}")
		r = tt.render_template("t", {"ok_1": "v"})
		self.assertEqual((r.text, r.missing), ("{{a.b}} {{a-b}} v", []))
		self.assertEqual(len(tt.placeholder_problems("{{a.b}} {{a-b}} {{ok}} {{x|zip}}")), 3)

	def test_name_grammar(self):
		for good in ("a", "welcome_1-a", "0x" * 31 + "a"):
			self.assertTrue(tt.TEMPLATE_NAME_RE.match(good), good)
		for bad in ("My Tpl", "Welcome", "_a", "a" * 64, ""):
			self.assertFalse(tt.TEMPLATE_NAME_RE.match(bad), bad)

	def test_button_problems_probe(self):
		for raw in (
			'{"rows": [[{"text": "A", "web_app": "{{u}}"}]]}',
			'{"rows": [[{"text": "A", "login_url": "{{u|url}}"}]]}',
			'{"rows": [[{"text": "{{t}}", "callback": "go_{{id}}"}]]}',
		):
			self.assertEqual(tt.button_problems(raw), [], raw)
		self.assertTrue(tt.button_problems('{"rows": [[{"text": "A", "web_app": "http://x"}]]}'))
		self.assertTrue(tt.button_problems("{}"))


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
	def test_gateway_settings_apply_with_full_payload(self):
		gw = SimpleNamespace(
			name="g",
			telegram_silent_replies=1,
			telegram_protect_content=1,
			preview_url=0,
			telegram_parse_mode="HTML",
		)
		self.put(body='See <a href="{{u}}">here</a>')
		tt.send_template(gw, 5, "t", {"u": "https://x.io"}, sender=self.sender)
		self.assertEqual(
			self.api.last("sendMessage")["payload"],
			{
				"chat_id": 5,
				"text": 'See <a href="https://x.io">here</a>',
				"parse_mode": "HTML",
				"disable_notification": True,
				"protect_content": True,
				"link_preview_options": {"is_disabled": True},
			},
		)

	def test_explicit_silent_protect_only_add(self):
		gw = SimpleNamespace(name="g", telegram_silent_replies=0, telegram_protect_content=1)
		self.put()
		tt.send_template(gw, 5, "t", {"name": "A"}, sender=self.sender, silent=True, protect=False)
		call = self.api.last("sendMessage")["payload"]
		self.assertTrue(call["disable_notification"] and call["protect_content"])

	def test_default_sender_signs_callbacks_for_the_chat(self):
		self.put(buttons_json='{"rows": [[{"text": "Y", "callback": "yes"}]]}')
		adapter = mock.Mock(client=self.sender.client)
		adapter.sign_callback_data.side_effect = lambda p, chat: f"S{chat}|{p}"
		with mock.patch("huf.ai.gateway_webhook.get_gateway_adapter", return_value=adapter):
			tt.send_template(SimpleNamespace(name="g"), 5, "t", {"name": "A"})
		data = self.api.last("sendMessage")["payload"]["reply_markup"]["inline_keyboard"][0][0][
			"callback_data"
		]
		self.assertTrue(data.startswith("S5|"), data)

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
		self.put(
			media_type="photo",
			media="https://x/y.jpg",
			body="y" * 1500,
			buttons_json='{"rows": [[{"text": "S", "url": "https://x.io"}]]}',
		)
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
