# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Provider failures map to specific plain-English reasons (shown on the failed Flow node)."""

import unittest

import litellm

from huf.ai.providers.litellm import ProviderUnavailableError, _raise_provider_unavailable


def _raise(exc, provider="OpenAI", model="openai/gpt-x"):
	try:
		_raise_provider_unavailable(f"LiteLLM error: {exc}", model, provider, getattr(exc, "status_code", None))
	except ProviderUnavailableError as e:
		return e
	raise AssertionError("did not raise")


class TestProviderErrorMessages(unittest.TestCase):
	def test_auth_401(self):
		e = _raise(litellm.AuthenticationError("Incorrect API key sk-abcdefghijklmnopqrstuv", "openai", "gpt-x"))
		self.assertEqual(e.kind, "auth")
		self.assertIn("The OpenAI key was rejected", e.public_message)
		self.assertIn("AI Providers", e.public_message)
		self.assertNotIn("sk-", e.public_message)

	def test_auth_403(self):
		e = _raise(litellm.PermissionDeniedError("forbidden", "openai", "gpt-x", response=_resp(403)))
		self.assertEqual(e.kind, "auth")
		self.assertIn("key was rejected", e.public_message)

	def test_rate_limit_429(self):
		e = _raise(litellm.RateLimitError("Too many requests", "openai", "gpt-x"))
		self.assertEqual(e.kind, "rate_limited")
		self.assertIn("rate-limiting", e.public_message)

	def test_quota_429(self):
		e = _raise(litellm.RateLimitError("insufficient_quota: You exceeded your current quota", "openai", "gpt-x"))
		self.assertEqual(e.kind, "quota_exceeded")
		self.assertIn("quota", e.public_message)

	def test_model_not_found_404(self):
		e = _raise(litellm.NotFoundError("The model `zzz` does not exist", "gpt-x", "openai"))
		self.assertEqual(e.kind, "model_not_found")
		self.assertIn("was not found at OpenAI", e.public_message)
		self.assertIn("gpt-x", e.public_message)

	def test_timeout(self):
		e = _raise(litellm.Timeout("Request timed out", "gpt-x", "openai"))
		self.assertEqual(e.kind, "timeout")
		self.assertIn("took too long", e.public_message)

	def test_network(self):
		e = _raise(litellm.APIConnectionError("Connection error", "openai", "gpt-x", request=None))
		self.assertEqual(e.kind, "server_error")
		self.assertIn("Could not reach OpenAI", e.public_message)

	def test_unknown_keeps_generic(self):
		e = _raise(RuntimeError("weird"))
		self.assertIn("could not complete this request", e.public_message)


def _resp(code):
	import httpx
	return httpx.Response(code, request=httpx.Request("POST", "https://x"))
