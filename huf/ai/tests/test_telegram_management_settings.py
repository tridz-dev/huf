# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers of telegram_management_settings (no site, no network)."""

from __future__ import annotations

import unittest

from huf.ai.telegram_management_settings import EDITABLE_FIELDS, FIELD_SPECS, build_settings, coerce_value, validate_updates

INFO = {n: {"options": list(s.get("options", []))} for n, s in FIELD_SPECS.items()}


class TestTelegramSettings(unittest.TestCase):
	def test_no_credential_fields_are_editable(self):
		for bad in ("integration_settings", "bot_token", "webhook_secret", "is_enabled"):
			self.assertNotIn(bad, EDITABLE_FIELDS)

	def test_unknown_field_is_an_error(self):
		clean, skipped, errors = validate_updates({"integration_settings": "x"}, INFO)
		self.assertEqual((clean, skipped), ({}, []))
		self.assertEqual(errors[0]["field"], "integration_settings")

	def test_missing_doctype_field_is_skipped(self):
		info = {k: v for k, v in INFO.items() if k != "telegram_streaming"}
		clean, skipped, errors = validate_updates({"telegram_streaming": True, "mention_required": False}, info)
		self.assertEqual(clean, {"mention_required": 0})
		self.assertEqual(skipped[0]["field"], "telegram_streaming")
		self.assertEqual(errors, [])

	def test_select_uses_meta_options(self):
		info = dict(INFO, telegram_parse_mode={"options": ["Plain", "HTML"]})
		_, _, errors = validate_updates({"telegram_parse_mode": "MarkdownV2"}, info)
		self.assertEqual(errors[0]["field"], "telegram_parse_mode")
		clean, _, errors = validate_updates({"telegram_parse_mode": "Plain"}, info)
		self.assertEqual((clean, errors), ({"telegram_parse_mode": "Plain"}, []))

	def test_int_bounds(self):
		spec = FIELD_SPECS["retry_max_attempts"]
		self.assertEqual(coerce_value(spec, "3"), 3)
		for bad in (0, 11, "x", "", None, True):
			with self.assertRaises(ValueError):
				coerce_value(spec, bad)

	def test_check_coercion(self):
		spec = FIELD_SPECS["typing_indicator"]
		self.assertEqual([coerce_value(spec, v) for v in (True, 0, "1", "off")], [1, 0, 1, 0])
		with self.assertRaises(ValueError):
			coerce_value(spec, "maybe")

	def test_text_length(self):
		with self.assertRaises(ValueError):
			coerce_value(FIELD_SPECS["telegram_bot_allowlist"], "x" * 2001)

	def test_build_settings_reports_unavailable(self):
		info = {"mention_required": {"options": []}, "direct_policy": {"options": ["Open"]}}
		out = build_settings({"mention_required": None, "direct_policy": "Open"}, info)
		self.assertEqual(out["values"], {"mention_required": 0, "direct_policy": "Open"})
		self.assertEqual(out["options"], {"direct_policy": ["Open"]})
		self.assertIn("telegram_streaming", out["unavailable"])
		self.assertNotIn("direct_policy", out["unavailable"])


class TestTelegramSettingsExtended(unittest.TestCase):
	def test_new_fields_are_allow_listed(self):
		for name in (
			"telegram_guard_captcha", "telegram_guard_question_text", "telegram_welcome_cooldown_seconds",
			"default_target_type", "default_agent", "default_flow", "execution_user", "error_reply_text",
		):
			self.assertIn(name, FIELD_SPECS)
		for bad in ("integration_settings", "bot_token", "webhook_secret", "is_enabled"):
			self.assertNotIn(bad, FIELD_SPECS)

	def test_captcha_choices_and_target_type_empty(self):
		spec = FIELD_SPECS["telegram_guard_captcha"]
		self.assertEqual(coerce_value(spec, "Emoji"), "Emoji")
		with self.assertRaises(ValueError):
			coerce_value(spec, "Hard")
		spec = FIELD_SPECS["default_target_type"]
		self.assertEqual(coerce_value(spec, "", ["Agent", "Flow"]), "")
		self.assertEqual(coerce_value(spec, "Flow", ["Agent", "Flow"]), "Flow")

	def test_cooldown_and_text_bounds(self):
		self.assertEqual(coerce_value(FIELD_SPECS["telegram_welcome_cooldown_seconds"], "0"), 0)
		with self.assertRaises(ValueError):
			coerce_value(FIELD_SPECS["telegram_welcome_cooldown_seconds"], -1)
		with self.assertRaises(ValueError):
			coerce_value(FIELD_SPECS["error_reply_text"], "x" * 501)

	def test_link_fields_are_trimmed(self):
		self.assertEqual(coerce_value(FIELD_SPECS["execution_user"], " a@b.c "), "a@b.c")

	def test_validate_updates_accepts_routing(self):
		clean, _, errors = validate_updates({"default_target_type": "Agent", "default_agent": "Bot"}, INFO)
		self.assertEqual((clean, errors), ({"default_target_type": "Agent", "default_agent": "Bot"}, []))


def _raw(fn):
	return getattr(fn, "__wrapped__", fn)


class TestListGatewayUsersPermission(unittest.TestCase):
	def test_denied_without_gateway_admin(self):
		from unittest import mock

		import frappe

		from huf.ai import telegram_management_settings as m

		with mock.patch.object(m, "_load_gateway", side_effect=frappe.PermissionError("no")):
			with self.assertRaises(frappe.PermissionError):
				_raw(m.list_gateway_users)("G")

	def test_excludes_administrator_and_disabled(self):
		from unittest import mock

		from huf.ai import telegram_management_settings as m

		def fake_get_all(doctype, **kw):
			if doctype == "Has Role":
				return ["Administrator", "a@x.com", "a@x.com"]
			return [{"name": "Administrator", "full_name": "Administrator"}, {"name": "a@x.com", "full_name": ""}]

		with mock.patch.object(m, "_load_gateway", return_value={"name": "G"}), mock.patch.object(m.frappe, "get_all", fake_get_all), mock.patch.object(m, "_execution_roles", return_value=["Huf Gateway User"]):
			out = _raw(m.list_gateway_users)("G")
		self.assertEqual(out["users"], [{"name": "a@x.com", "full_name": "a@x.com"}])
