# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""FIX-E: legacy provider modules raise typed ProviderError instead of returning
"... API Error ..." strings (which used to be stored as a Success reply).

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_provider_errors.py -v
"""

import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "testing"))
import _stub_env  # noqa: E402

_stub_env.install()

from huf.ai.providers import google as google_provider  # noqa: E402
from huf.ai.providers.errors import ProviderError, redact_text  # noqa: E402

SECRET = "AIzaSyDUMMYDUMMYDUMMYDUMMYDUMMY123456"


class _Resp:
	def __init__(self, status, text="{}", reason="X"):
		self.status_code = status
		self.text = text
		self.reason = reason

	def json(self):
		return {}


class TestClassification(unittest.TestCase):
	def test_status_to_kind(self):
		cases = {
			401: "auth",
			403: "auth",
			404: "model_not_found",
			429: "rate_limited",
			500: "server_error",
			503: "server_error",
			504: "timeout",
			400: "bad_request",
			402: "quota_exceeded",
		}
		for status, kind in cases.items():
			self.assertEqual(ProviderError.from_http(status, "boom").kind, kind, status)

	def test_429_with_quota_text_is_quota_exceeded(self):
		err = ProviderError.from_http(429, "You exceeded your current quota; spend cap reached")
		self.assertEqual(err.kind, "quota_exceeded")
		self.assertEqual(err.status_code, 429)

	def test_public_message_hides_raw_text_and_log_message_is_redacted(self):
		err = ProviderError.from_http(404, f"models/x not found ?key={SECRET} project 123", "Gemini")
		self.assertNotIn("project 123", str(err))
		self.assertNotIn(SECRET, err.log_message)
		self.assertNotIn("API Error", str(err))

	def test_redact_text(self):
		out = redact_text(f"url?key={SECRET} Authorization: Bearer abcdefghijkl1234 x-goog-api-key: {SECRET}")
		self.assertNotIn(SECRET, out)
		self.assertNotIn("abcdefghijkl1234", out)


class TestGoogleLegacyRaises(unittest.IsolatedAsyncioTestCase):
	async def _run(self, post):
		doc = MagicMock()
		doc.get_password.return_value = SECRET
		agent = SimpleNamespace(instructions="hi", tools=[], temperature=0.1)
		with patch.object(google_provider.frappe, "get_doc", return_value=doc), \
			patch.object(google_provider.frappe, "log_error", MagicMock()), \
			patch.object(google_provider.requests, "post", post):
			return await google_provider.run(agent, "hello", "Google", "google/gemini-x")

	async def test_http_errors_raise_typed_error(self):
		for status, kind in ((404, "model_not_found"), (429, "rate_limited"), (401, "auth"), (500, "server_error")):
			with self.assertRaises(ProviderError) as ctx:
				await self._run(MagicMock(return_value=_Resp(status, f"raw body ?key={SECRET}")))
			self.assertEqual(ctx.exception.kind, kind)
			self.assertEqual(ctx.exception.status_code, status)
			self.assertNotIn("API Error", str(ctx.exception))
			self.assertNotIn(SECRET, ctx.exception.log_message)

	async def test_timeout_raises_timeout_kind(self):
		post = MagicMock(side_effect=google_provider.requests.exceptions.Timeout("slow"))
		with self.assertRaises(ProviderError) as ctx:
			await self._run(post)
		self.assertEqual(ctx.exception.kind, "timeout")


class TestAnthropicAndOpenRouterRaise(unittest.IsolatedAsyncioTestCase):
	async def test_anthropic_sdk_error_raises(self):
		sys.modules.setdefault("anthropic", MagicMock())
		from huf.ai.providers import anthropic as anth

		class Boom(Exception):
			status_code = 429

		client = MagicMock()
		client.messages.create = MagicMock(side_effect=Boom("rate limit"))

		async def create(**kw):
			raise Boom("rate limit")

		client.messages.create = create
		doc = MagicMock()
		doc.get_password.return_value = "k"
		with patch.object(anth.frappe, "get_doc", return_value=doc), \
			patch.object(anth.frappe, "log_error", MagicMock()), \
			patch.object(anth.anthropic, "AsyncAnthropic", return_value=client):
			with self.assertRaises(ProviderError) as ctx:
				await anth.run(SimpleNamespace(instructions="", tools=[]), "hi", "Anthropic", "claude-x")
		self.assertEqual(ctx.exception.kind, "rate_limited")

	async def test_openrouter_request_error_raises(self):
		from huf.ai.providers import openrouter

		resp = _Resp(401, "no key")
		exc = openrouter.requests.exceptions.HTTPError("401", response=resp)

		async def boom(*a, **k):
			raise exc

		doc = MagicMock()
		doc.get_password.return_value = "k"
		with patch.object(openrouter.frappe, "get_doc", return_value=doc), \
			patch.object(openrouter, "_post_with_retry", boom):
			with self.assertRaises(ProviderError) as ctx:
				await openrouter.run(SimpleNamespace(instructions="", tools=[]), "hi", "OpenRouter", "m")
		self.assertEqual(ctx.exception.kind, "auth")


if __name__ == "__main__":
	unittest.main()
