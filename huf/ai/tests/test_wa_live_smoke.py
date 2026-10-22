"""Tests for huf/ai/tests/wa_live_smoke.py, driven by an injected fake Graph endpoint (no network)."""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SMOKE_PATH = os.path.normpath(os.path.join(_THIS_DIR, "wa_live_smoke.py"))

TOKEN = "EAAG-test-token-not-real"  # noqa: S105 - fake fixture, asserted never to be printed
PHONE_ID = "123456789012345"


def _load_smoke_module():
	module_name = "huf_wa_live_smoke_under_test"
	spec = importlib.util.spec_from_file_location(module_name, _SMOKE_PATH)
	module = importlib.util.module_from_spec(spec)
	sys.modules[module_name] = module
	spec.loader.exec_module(module)
	return module


S = _load_smoke_module()


class FakeGraph:
	"""Records calls and replays one canned ``(status, payload)`` or exception."""

	def __init__(self, status=200, payload=None, error=None):
		self.status = status
		self.payload = payload if payload is not None else {}
		self.error = error
		self.calls = []

	def __call__(self, url, params, timeout=None):
		self.calls.append({"url": url, "params": dict(params)})
		if self.error is not None:
			raise self.error
		return self.status, self.payload


def _valid_payload(expires_at):
	return {"data": {"is_valid": True, "expires_at": expires_at, "scopes": ["whatsapp_business_messaging"]}}


class TestCheckToken(unittest.TestCase):
	def test_valid_token_prints_expiry_date(self):
		expiry = int(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc).timestamp())
		fake = FakeGraph(payload=_valid_payload(expiry))

		line = S.check_token(TOKEN, http_get=fake)

		self.assertEqual(line, "token valid until 2026-11-01")
		self.assertEqual(fake.calls[0]["url"], "https://graph.facebook.com/v22.0/debug_token")
		self.assertEqual(fake.calls[0]["params"]["input_token"], TOKEN)
		self.assertNotIn(TOKEN, line)

	def test_rejected_token_is_invalid_and_never_echoed(self):
		fake = FakeGraph(
			status=400,
			payload={"error": {"message": f"Invalid OAuth access token {TOKEN}", "code": 190}},
		)

		line = S.check_token(TOKEN, http_get=fake)

		self.assertEqual(line, "token invalid")
		self.assertNotIn(TOKEN, line)

	def test_transport_error_is_invalid(self):
		fake = FakeGraph(error=RuntimeError(f"connection failed for access_token={TOKEN}"))

		line = S.check_token(TOKEN, http_get=fake)

		self.assertEqual(line, "token invalid")
		self.assertNotIn(TOKEN, line)

	def test_permanent_token_reports_no_expiry(self):
		fake = FakeGraph(payload=_valid_payload(0))

		line = S.check_token(TOKEN, http_get=fake)

		self.assertEqual(line, "token valid (no expiry)")
		self.assertNotIn(TOKEN, line)


if __name__ == "__main__":
	unittest.main()
