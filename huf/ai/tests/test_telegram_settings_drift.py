# Copyright (c) 2026, Huf and contributors
"""Drift guard for the Telegram Gateway controls.

Every Telegram field in ``gateway.json`` must be (a) editable through the Settings API or explicitly exempt,
(b) present in the Settings tab model, and (c) read by backend code. A control nobody reads is a dead control.
The Gateway doctype is the single source of truth: no site-config or credential key may shadow a field.
"""

import json
import re
import unittest
from pathlib import Path

from huf.ai.telegram_management_settings import FIELD_SPECS

ROOT = Path(__file__).resolve().parents[3]
GATEWAY_JSON = ROOT / "huf" / "huf" / "doctype" / "gateway" / "gateway.json"
HUF_AI = ROOT / "huf" / "ai"
SETTINGS_MODEL = ROOT / "frontend" / "src" / "components" / "telegram" / "settingsModel.ts"

# Shared (non-prefixed) fields that carry Telegram behaviour and so are held to the same rules.
SHARED_TELEGRAM_FIELDS = {"preview_url", "retry_max_attempts", "agent_recipient_allowlist"}

# Telegram fields deliberately not editable from the Settings tab (reason required).
NOT_EDITABLE: dict[str, str] = {}
# Telegram fields deliberately not shown in the Settings tab model (reason required).
NOT_IN_UI: dict[str, str] = {}
# Fields read only through a generic reader (reason required); everything else needs a literal reference.
GENERIC_READERS: dict[str, str] = {}


def _telegram_fields() -> list[str]:
	fields = json.loads(GATEWAY_JSON.read_text())["fields"]
	return [
		f["fieldname"]
		for f in fields
		if f["fieldname"].startswith("telegram_") or f["fieldname"] in SHARED_TELEGRAM_FIELDS
	]


def _backend_sources() -> dict[Path, str]:
	return {
		p: p.read_text()
		for p in HUF_AI.rglob("*.py")
		if "tests" not in p.parts and p.name != "telegram_management_settings.py"
	}


class TestGatewayTelegramDrift(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.fields = _telegram_fields()
		cls.ui = SETTINGS_MODEL.read_text()
		cls.backend = _backend_sources()

	def test_fields_found(self):
		self.assertGreater(len(self.fields), 20)

	def test_every_field_is_allow_listed_or_exempt(self):
		for name in self.fields:
			if name in NOT_EDITABLE:
				continue
			self.assertIn(name, FIELD_SPECS, f"{name}: not in FIELD_SPECS and not exempt")

	def test_every_allow_listed_field_exists_in_doctype(self):
		doc_fields = {f["fieldname"] for f in json.loads(GATEWAY_JSON.read_text())["fields"]}
		for name in FIELD_SPECS:
			self.assertIn(name, doc_fields, name)

	def test_every_field_is_in_the_ui_model(self):
		for name in self.fields:
			if name in NOT_EDITABLE or name in NOT_IN_UI:
				continue
			self.assertRegex(self.ui, rf"name: '{re.escape(name)}'", f"{name}: missing from settingsModel.ts")

	def test_every_ui_field_is_allow_listed(self):
		for name in re.findall(r"name: '([a-z_]+)'", self.ui):
			self.assertIn(name, FIELD_SPECS, f"{name}: in the UI but the API would refuse it")

	def test_every_field_has_a_backend_reader(self):
		for name in self.fields:
			if name in GENERIC_READERS:
				continue
			readers = [p.name for p, text in self.backend.items() if re.search(rf"\b{re.escape(name)}\b", text)]
			self.assertTrue(readers, f"{name}: nothing in huf/ai reads it (dead control)")

	def test_exemptions_are_real_fields(self):
		doc_fields = {f["fieldname"] for f in json.loads(GATEWAY_JSON.read_text())["fields"]}
		for name in (*NOT_EDITABLE, *NOT_IN_UI, *GENERIC_READERS):
			self.assertIn(name, doc_fields, f"stale exemption: {name}")

	def test_no_site_or_credential_override_of_gateway_fields(self):
		banned = ("huf_telegram_streaming", "huf_telegram_guard_captcha", '"bot_allowlist"', '"bot_max_hops"', '"bot_rate_cap"')
		for path, text in self.backend.items():
			for key in banned:
				self.assertNotIn(key, text, f"{path.name}: {key} shadows a Gateway field")

	def test_field_specs_ranges_match_doctype_defaults(self):
		defaults = {f["fieldname"]: f.get("default") for f in json.loads(GATEWAY_JSON.read_text())["fields"]}
		for name, spec in FIELD_SPECS.items():
			if spec["type"] != "int" or defaults.get(name) in (None, ""):
				continue
			value = int(defaults[name])
			self.assertTrue(spec["min"] <= value <= spec["max"], f"{name}: default {value} outside range")


if __name__ == "__main__":
	unittest.main()
