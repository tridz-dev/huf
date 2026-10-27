"""Conformance (TFIX-D L4): credential fields that look secret must be declared ``secret=True``.

Secret fields are write-only in the UI and never echoed back; a mis-flagged field would leak through the
credentials read path. Every registered gateway adapter is checked.
"""

import re
import unittest

from huf.ai.gateway_adapters.registered import _ADAPTER_LOCATIONS, get_adapter_class

SECRET_KEY_RE = re.compile(r"secret|token|password|passwd|private|api_?key|signing|hmac", re.I)

# Known offenders in OTHER providers, as {(provider_id, field_key): reason}. Listed here (not silently
# skipped) so they stay visible; remove an entry once its schema is fixed. Empty at TFIX-D (2026-10-27):
# every adapter's matching fields were already secret=True.
ALLOWED_OFFENDERS: dict[tuple[str, str], str] = {}


def _offenders(provider_id: str) -> list[str]:
	schema = getattr(get_adapter_class(provider_id), "credential_schema", None)
	return [
		f.key
		for f in (schema.fields if schema else ())
		if SECRET_KEY_RE.search(f.key) and not f.secret and (provider_id, f.key) not in ALLOWED_OFFENDERS
	]


class TestCredentialSecretFlags(unittest.TestCase):
	def test_teams_secret_like_fields_are_secret(self):
		self.assertEqual(_offenders("microsoft_teams"), [])

	def test_every_adapter_secret_like_fields_are_secret(self):
		self.assertIn("microsoft_teams", _ADAPTER_LOCATIONS)
		for provider_id in _ADAPTER_LOCATIONS:
			with self.subTest(provider=provider_id):
				self.assertEqual(_offenders(provider_id), [], f"set secret=True in {provider_id}")

	def test_pattern_catches_expected_names_only(self):
		for key in ("app_secret", "access_token", "app_password", "private_key", "api_key", "apikey", "hmac_key"):
			self.assertTrue(SECRET_KEY_RE.search(key), key)
		for key in ("app_id", "tenant_id", "allowed_tenant_ids", "phone_number_id", "bot_username"):
			self.assertFalse(SECRET_KEY_RE.search(key), key)
