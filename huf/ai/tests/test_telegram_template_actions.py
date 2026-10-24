# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Agent template actions (send/list/preview) over the fake Bot API: gateway resolution + real payloads."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest import mock

import frappe

from huf.ai import telegram_templates as tt
from huf.ai.gateway_adapters.telegram_client import TelegramBotClient
from huf.ai.gateway_adapters.telegram_outbound import TelegramSender
from huf.ai.tests.telegram_fakes import TOKEN, FakeBotApi
from huf.ai.tools import telegram as tool
from huf.ai.tools._registry import TELEGRAM_TOOLS

GATEWAY = SimpleNamespace(
	name="gw",
	provider="Telegram",
	telegram_silent_replies=1,
	telegram_protect_content=0,
	preview_url=0,
	telegram_parse_mode="HTML",
)
TEMPLATE = {
	"template_name": "welcome",
	"is_active": 1,
	"parse_mode": "HTML",
	"body": 'Hi {{name}} <a href="{{u}}">link</a>',
	"media_type": "none",
	"media": "",
	"buttons_json": '{"rows": [[{"text": "Yes", "callback": "yes"}]]}',
	"variables": [],
	"gateway": "",
}


class Base(unittest.TestCase):
	run_gateway = ""  # the run's gateway ("" = not inside a gateway run)
	state = "none"

	def setUp(self):
		self.api = FakeBotApi()
		client = TelegramBotClient(
			TOKEN, http_post=self.api.http_post, http_get=self.api.http_get, sleep=lambda s: None
		)
		sender = TelegramSender(client)
		fr = mock.MagicMock()
		fr.PermissionError = frappe.PermissionError
		fr.db.get_value.side_effect = lambda dt, name, *a, **k: (
			{"provider": GATEWAY.provider, "is_enabled": 1} if name == "gw" else None
		)
		fr.get_doc.side_effect = lambda dt, name: GATEWAY
		self.denied = False

		def admin(name):
			if self.denied:
				raise frappe.PermissionError

		for p in (
			mock.patch.object(tool, "frappe", fr),
			mock.patch.object(tool.scope, "run_gateway", lambda: self.run_gateway),
			mock.patch.object(tool.scope, "gateway_state", lambda: (self.state, self.run_gateway)),
			mock.patch("huf.ai.telegram_management._require_gateway_admin", admin),
			mock.patch.object(tt, "_load", lambda n: dict(TEMPLATE) if n == "welcome" else None),
			mock.patch.object(tt, "_touch", lambda n: None),
			mock.patch.object(
				tt, "build_sender", lambda gw: (sender, lambda payload, chat: f"S{chat}|{payload}")
			),
			mock.patch.object(tt, "_list_rows", lambda g: [{"name": "welcome", "is_active": 1, "gw": g}]),
		):
			p.start()
			self.addCleanup(p.stop)

	def act(self, fn, **kw):
		return json.loads(fn(**kw))

	def last(self, method="sendMessage"):
		return self.api.last(method)["payload"]


class TestOutsideGatewayRun(Base):
	def test_gateway_required_and_authorised(self):
		r = self.act(tool._handle_send_template, chat_id="9", template_name="welcome")
		self.assertFalse(r["success"])
		self.assertIn("gateway is required", r["error"])
		self.denied = True
		r = self.act(tool._handle_send_template, chat_id="9", template_name="welcome", gateway="gw")
		self.assertIn("gateway is required", r["error"])
		self.assertEqual(self.api.calls, [])

	def test_unknown_or_foreign_gateway_refused(self):
		r = self.act(tool._handle_list_templates, gateway="other")
		self.assertIn("not an enabled Telegram gateway", r["error"])

	def test_invalid_run_gateway_state_refused(self):
		type(self).state = "invalid"
		self.addCleanup(setattr, type(self), "state", "none")
		r = self.act(tool._handle_list_templates, gateway="gw")
		self.assertFalse(r["success"])

	def test_send_uses_real_gateway_document_settings(self):
		r = self.act(
			tool._handle_send_template,
			chat_id="9",
			template_name="welcome",
			gateway="gw",
			variables={"name": "<Ann>", "u": "https://x.io/?a=1"},
		)
		self.assertTrue(r["success"], r)
		self.assertEqual(
			self.last(),
			{
				"chat_id": "9",
				"text": 'Hi &lt;Ann&gt; <a href="https://x.io/?a=1">link</a>',
				"parse_mode": "HTML",
				"disable_notification": True,  # gateway telegram_silent_replies
				"link_preview_options": {"is_disabled": True},  # gateway preview_url = 0
				"reply_markup": {"inline_keyboard": [[{"text": "Yes", "callback_data": mock.ANY}]]},
			},
		)
		cb = self.last()["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
		self.assertTrue(cb.startswith("S9|"), cb)

	def test_declared_options_honoured_and_undeclared_ignored(self):
		self.act(
			tool._handle_send_template,
			chat_id="9",
			template_name="welcome",
			gateway="gw",
			variables={"name": "A", "u": "https://x.io"},
			protect_content=True,
			message_thread_id=4,
			reply_to_message_id=8,
			thread_id=99,  # undeclared: ignored
		)
		p = self.last()
		self.assertTrue(p["protect_content"])
		self.assertEqual(p["message_thread_id"], 4)
		self.assertEqual(p["reply_parameters"], {"message_id": 8, "allow_sending_without_reply": True})

	def test_name_is_not_a_template_alias(self):
		r = self.act(tool._handle_send_template, chat_id="9", name="welcome", gateway="gw")
		self.assertIn("template_name is required", r["error"])

	def test_preview_shows_buttons_and_does_not_send(self):
		r = self.act(
			tool._handle_preview_template,
			template_name="welcome",
			gateway="gw",
			variables={"name": "A", "u": "https://x.io"},
		)["results"]
		self.assertEqual(r["errors"], [])
		self.assertEqual(r["markup"], {"inline_keyboard": [[{"text": "Yes", "callback_data": mock.ANY}]]})
		self.assertEqual(r["text"], 'Hi A <a href="https://x.io">link</a>')
		self.assertEqual(self.api.calls, [])

	def test_preview_reports_missing(self):
		r = self.act(tool._handle_preview_template, template_name="welcome", gateway="gw")["results"]
		self.assertEqual(r["missing"], ["name", "u"])

	def test_list_uses_gateway(self):
		r = self.act(tool._handle_list_templates, gateway="gw")["results"]
		self.assertEqual(r, [{"name": "welcome", "is_active": 1, "gw": "gw"}])


class TestInsideGatewayRun(Base):
	run_gateway = "gw"
	state = "telegram"

	def test_model_supplied_gateway_is_never_used(self):
		self.assertEqual(tool._template_gateway({"gateway": "attacker"}), "gw")
		self.assertEqual(tool._template_gateway({}), "gw")

	def test_send_without_gateway_argument(self):
		r = self.act(
			tool._handle_send_template,
			chat_id="9",
			template_name="welcome",
			variables={"name": "A", "u": "https://x.io"},
		)
		self.assertTrue(r["success"], r)
		self.assertTrue(self.last()["disable_notification"])


class TestSchema(unittest.TestCase):
	def test_template_params_declared(self):
		params = {p["fieldname"] for p in TELEGRAM_TOOLS[0]["parameters"]}
		for name in ("template_name", "variables", "gateway", "disable_notification", "protect_content",
					"message_thread_id", "reply_to_message_id"):  # fmt: skip
			self.assertIn(name, params)


if __name__ == "__main__":
	unittest.main()
