# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for _normalize_model_name().

The module being tested is huf.ai.providers.litellm, which imports frappe and
litellm. This test file installs defensive stubs before importing the module,
matching the pattern in huf/ai/local_runtimes/tests/test_ollama.py. Runs both
standalone (no bench) and under pytest with a real Frappe environment.

Run standalone (no bench) from the repo root:
	PYTHONPATH=. python3 huf/ai/tests/test_litellm_providers.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock

# Stub frappe before any imports
try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe_mock.logger = lambda *args, **kwargs: MagicMock()
	sys.modules["frappe"] = frappe_mock
	sys.modules["frappe.utils"] = MagicMock()
	sys.modules["frappe.model.document"] = MagicMock()
	sys.modules["frappe.client"] = MagicMock()

# Stub litellm and its submodules before importing litellm.py
try:
	import litellm  # noqa: F401
except ImportError:
	litellm_mock = MagicMock()
	litellm_mock.InternalServerError = Exception
	litellm_mock.RateLimitError = Exception
	litellm_mock.APIError = Exception
	litellm_mock.BadRequestError = Exception
	litellm_mock.ContextWindowExceededError = Exception
	litellm_mock.utils.trim_messages = lambda x: x
	sys.modules["litellm"] = litellm_mock
	sys.modules["litellm.utils"] = litellm_mock.utils

# Now we can safely import the module under test
from huf.ai.providers.litellm import _normalize_model_name  # noqa: E402


class TestNormalizeModelName(unittest.TestCase):
	"""Test suite for _normalize_model_name() routing logic."""

	def test_mlx_brand_routes_to_openai_prefix(self):
		"""Test that provider_brand='mlx' yields openai/ prefix."""
		result = _normalize_model_name("phi-3", provider="mlx", brand="mlx")
		self.assertEqual(result, "openai/phi-3")

	def test_mlx_provider_document_name_routes_to_openai(self):
		"""Test that provider document name 'mlx' routes to openai/ prefix.

		This tests the provider_prefix_map fallback when brand is None.
		The identity fallback (.get(provider.lower(), provider.lower()))
		would otherwise produce 'mlx/phi-3', which is not recognized by LiteLLM.
		"""
		result = _normalize_model_name("phi-3", provider="mlx", brand=None)
		self.assertEqual(result, "openai/phi-3")

	def test_ollama_brand_regression(self):
		"""Regression: ollama brand must still route to ollama_chat/."""
		result = _normalize_model_name("gpt-oss", provider="ollama", brand="ollama")
		self.assertEqual(result, "ollama_chat/gpt-oss")

	def test_ollama_provider_document_name_regression(self):
		"""Regression: ollama provider document name must route to ollama_chat/."""
		result = _normalize_model_name("gpt-oss", provider="ollama", brand=None)
		self.assertEqual(result, "ollama_chat/gpt-oss")

	def test_lmstudio_brand_regression(self):
		"""Regression: lmstudio brand must route to openai/."""
		result = _normalize_model_name("mistral", provider="lmstudio", brand="lmstudio")
		self.assertEqual(result, "openai/mistral")

	def test_lmstudio_provider_document_name_regression(self):
		"""Regression: lmstudio provider document name must route to openai/."""
		result = _normalize_model_name("mistral", provider="lmstudio", brand=None)
		self.assertEqual(result, "openai/mistral")

	def test_already_formatted_model_passthrough(self):
		"""Test that models already in LiteLLM format (with /) pass through unchanged."""
		result = _normalize_model_name("openai/gpt-4-turbo", provider="mlx", brand="mlx")
		self.assertEqual(result, "openai/gpt-4-turbo")

	def test_already_formatted_model_with_different_provider(self):
		"""Test that formatted model passes through even if provider/brand differ."""
		result = _normalize_model_name("anthropic/claude-3", provider="mlx", brand="openai")
		self.assertEqual(result, "anthropic/claude-3")

	def test_case_insensitive_mlx_brand_uppercase(self):
		"""Test that brand matching is case-insensitive: 'MLX' behaves like 'mlx'."""
		result = _normalize_model_name("phi-3", provider="mlx", brand="MLX")
		self.assertEqual(result, "openai/phi-3")

	def test_case_insensitive_mlx_provider_uppercase(self):
		"""Test that provider matching is case-insensitive: 'MLX' provider routes correctly."""
		result = _normalize_model_name("phi-3", provider="MLX", brand=None)
		self.assertEqual(result, "openai/phi-3")

	def test_brand_takes_precedence_over_provider(self):
		"""Test that brand-based routing takes precedence over provider name.

		If both brand and provider are specified, brand wins.
		"""
		# provider says "openai", but brand says "ollama" -> ollama_chat wins
		result = _normalize_model_name("llama2", provider="openai", brand="ollama")
		self.assertEqual(result, "ollama_chat/llama2")

	def test_none_brand_uses_provider_fallback(self):
		"""Test that None brand falls through to provider_prefix_map."""
		result = _normalize_model_name("test-model", provider="anthropic", brand=None)
		self.assertEqual(result, "anthropic/test-model")


if __name__ == "__main__":
	unittest.main()
