"""Telegram Gateway fields: JSON contract (pure) and controller validation."""

import json
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace


GATEWAY_DIR = Path(__file__).resolve().parents[2] / "huf" / "doctype" / "gateway"
NEW_FIELDS = {
	"telegram_streaming": "Check",
	"telegram_parse_mode": "Select",
	"telegram_protect_content": "Check",
	"telegram_silent_replies": "Check",
	"telegram_business_policy": "Select",
	"telegram_join_policy": "Select",
	"telegram_inline_enabled": "Check",
	"telegram_agent_allow_group_admin": "Check",
	"telegram_agent_allow_business": "Check",
	"telegram_agent_allow_profile": "Check",
	"telegram_bot_allowlist": "Small Text",
	"telegram_bot_max_hops": "Int",
	"telegram_bot_rate_cap": "Int",
	"telegram_default_template": "Link",
	"telegram_welcome_template": "Link",
}


class TestGatewayJson(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.meta = json.loads((GATEWAY_DIR / "gateway.json").read_text())
		cls.fields = {f["fieldname"]: f for f in cls.meta["fields"]}

	def test_fields_present_ordered_and_gated(self):
		for name, ftype in NEW_FIELDS.items():
			self.assertIn(name, self.fields)
			self.assertEqual(self.fields[name]["fieldtype"], ftype)
			self.assertIn("Telegram", self.fields[name]["depends_on"])
			self.assertIn(name, self.meta["field_order"])
		self.assertEqual(len(self.meta["field_order"]), len(set(self.meta["field_order"])))

	def test_defaults_and_links(self):
		f = self.fields
		self.assertEqual(f["telegram_parse_mode"]["default"], "HTML")
		self.assertEqual(f["telegram_parse_mode"]["options"], "Plain\nHTML\nMarkdownV2")
		self.assertEqual(f["telegram_business_policy"]["default"], "Observe")
		self.assertEqual(f["telegram_join_policy"]["default"], "Queue")
		self.assertEqual(f["telegram_inline_enabled"]["default"], "1")
		self.assertEqual(f["telegram_default_template"]["options"], "Telegram Message Template")

	def test_shared_fields_widened(self):
		for name in ("preview_url", "agent_recipient_scope", "agent_send_cap_per_run", "agent_send_cap_per_day"):
			self.assertIn("Telegram", self.fields[name]["depends_on"], name)
		self.assertIn("Telegram", self.fields["agent_recipient_allowlist"]["depends_on"])


class TestTelegramValidation(unittest.TestCase):
	def _run(self, **kw):
		from huf.huf.doctype.gateway.gateway import Gateway

		base = {"provider": "Telegram", "default_target_type": "", "default_agent": "", "default_flow": ""}
		base.update(kw)
		doc = SimpleNamespace(**base)
		doc.get = lambda k, d=None: getattr(doc, k, d)
		with mock.patch("frappe.throw", side_effect=ValueError), mock.patch("frappe._", side_effect=lambda x: x):
			Gateway._validate_telegram_settings(doc)
		return doc

	def test_join_agent_needs_default_agent(self):
		with self.assertRaises(ValueError):
			self._run(telegram_join_policy="Agent")
		self._run(telegram_join_policy="Agent", default_agent="A")

	def test_business_draft_needs_target(self):
		with self.assertRaises(ValueError):
			self._run(telegram_business_policy="Reply")
		self._run(telegram_business_policy="Draft", default_target_type="Agent", default_agent="A")
		self._run(telegram_business_policy="Observe")

	def test_allowlist(self):
		doc = self._run(telegram_bot_allowlist="123\n456, 789")
		self.assertEqual(doc.telegram_bot_allowlist, "123, 456, 789")
		with self.assertRaises(ValueError):
			self._run(telegram_bot_allowlist="123, @bot")

	def test_other_providers_untouched(self):
		self._run(provider="WhatsApp", telegram_join_policy="Agent", telegram_bot_allowlist="x")


class TestGuardFieldValidation(unittest.TestCase):
	_run = TestTelegramValidation._run

	def test_negative_cooldown_rejected(self):
		with self.assertRaises(ValueError):
			self._run(telegram_welcome_cooldown_seconds=-1)
		self._run(telegram_welcome_cooldown_seconds=0)
		self._run(telegram_welcome_cooldown_seconds=60)

	def test_captcha_needs_non_decline_policy(self):
		with self.assertRaises(ValueError):
			self._run(telegram_guard_captcha="Emoji", telegram_join_policy="Decline")
		self._run(telegram_guard_captcha="Off", telegram_join_policy="Decline")
		self._run(telegram_guard_captcha="Arithmetic", telegram_join_policy="Queue")
		self._run(telegram_guard_captcha="Arithmetic")

	def test_new_fields_declared(self):
		fields = {f["fieldname"]: f for f in json.load(open(GATEWAY_DIR / "gateway.json"))["fields"]}
		self.assertEqual(fields["telegram_guard_captcha"]["options"], "Off\nArithmetic\nEmoji")
		self.assertEqual(fields["telegram_welcome_cooldown_seconds"]["default"], "60")
		self.assertEqual(fields["telegram_guard_question_text"]["fieldtype"], "Small Text")
