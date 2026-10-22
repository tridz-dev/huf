# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Pure helpers of telegram_management_settings (no site, no network)."""

from __future__ import annotations

import unittest

from huf.ai.telegram_management_settings import EDITABLE_FIELDS, FIELD_SPECS, build_settings, coerce_value, validate_updates

INFO = {n: {"options": list(s.get("options", []))} for n, s in FIELD_SPECS.items()}


class TestTelegramSettings(unittest.TestCase):
	def test_no_credential_fields_are_editable(self):
		for bad in ("integration_settings", "bot_token", "webhook_secret", "is_enabled", "execution_user"):
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
