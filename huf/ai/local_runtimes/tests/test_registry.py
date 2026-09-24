# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for adapter registry.

The registry itself never imports frappe, but `huf/__init__.py:4` does, so a
defensive stub is installed before the import below -- the same pattern as
`huf/ai/local_runtimes/tests/test_ollama.py`, so this file behaves identically
standalone and collected under a real bench.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_registry.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock

try:
	import requests  # noqa: F401
except ImportError:
	sys.modules["requests"] = MagicMock()

from huf.ai.local_runtimes.registry import get_adapter  # noqa: E402
from huf.ai.local_runtimes.mlx_server import MlxServerAdapter  # noqa: E402
from huf.ai.local_runtimes.ollama import OllamaAdapter  # noqa: E402
from huf.ai.local_runtimes.generic_openai import GenericOpenAIAdapter  # noqa: E402


class TestRegistryGetAdapter(unittest.TestCase):
	"""Test suite for the adapter registry."""

	def test_get_adapter_ollama_exact_case(self):
		"""Test that 'ollama' brand returns OllamaAdapter."""
		adapter = get_adapter("ollama")
		self.assertIsInstance(adapter, OllamaAdapter)
		self.assertEqual(adapter.flavor(), "ollama")

	def test_get_adapter_ollama_lowercase(self):
		"""Test that 'Ollama' (mixed case) returns OllamaAdapter."""
		adapter = get_adapter("Ollama")
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_get_adapter_ollama_uppercase(self):
		"""Test that 'OLLAMA' (uppercase) returns OllamaAdapter."""
		adapter = get_adapter("OLLAMA")
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_get_adapter_lmstudio_exact_case(self):
		"""Test that 'lmstudio' brand returns GenericOpenAIAdapter."""
		adapter = get_adapter("lmstudio")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)
		self.assertEqual(adapter.flavor(), "generic_openai")

	def test_get_adapter_lmstudio_mixed_case(self):
		"""Test that 'LMStudio' (mixed case) returns GenericOpenAIAdapter."""
		adapter = get_adapter("LMStudio")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

	def test_get_adapter_lmstudio_uppercase(self):
		"""Test that 'LMSTUDIO' (uppercase) returns GenericOpenAIAdapter."""
		adapter = get_adapter("LMSTUDIO")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

	def test_get_adapter_vllm_exact_case(self):
		"""Test that 'vllm' brand returns GenericOpenAIAdapter."""
		adapter = get_adapter("vllm")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)
		self.assertEqual(adapter.flavor(), "generic_openai")

	def test_get_adapter_vllm_mixed_case(self):
		"""Test that 'vLLM' (mixed case) returns GenericOpenAIAdapter."""
		adapter = get_adapter("vLLM")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

	def test_get_adapter_vllm_uppercase(self):
		"""Test that 'VLLM' (uppercase) returns GenericOpenAIAdapter."""
		adapter = get_adapter("VLLM")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

	def test_get_adapter_none_returns_ollama(self):
		"""Test that None brand returns OllamaAdapter (default)."""
		adapter = get_adapter(None)
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_get_adapter_empty_string_returns_ollama(self):
		"""Test that empty string brand returns OllamaAdapter (default)."""
		adapter = get_adapter("")
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_get_adapter_unrecognized_returns_ollama(self):
		"""Test that unrecognized brand returns OllamaAdapter (default)."""
		adapter = get_adapter("unknown_brand")
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_get_adapter_unrecognized_uppercase_returns_ollama(self):
		"""Test that unrecognized uppercase brand returns OllamaAdapter."""
		adapter = get_adapter("UNKNOWN")
		self.assertIsInstance(adapter, OllamaAdapter)

	def test_flavors_are_distinct(self):
		"""Test that adapter flavors are distinct and stable."""
		ollama_adapter = get_adapter("ollama")
		generic_adapter = get_adapter("lmstudio")
		self.assertEqual(ollama_adapter.flavor(), "ollama")
		self.assertEqual(generic_adapter.flavor(), "generic_openai")
		self.assertNotEqual(
			ollama_adapter.flavor(),
			generic_adapter.flavor()
		)

	def test_generic_openai_adapter_supports_tools_always_none(self):
		"""Test that GenericOpenAIAdapter.capability_overrides returns supports_tools: None."""
		adapter = get_adapter("lmstudio")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

		# Test with ok=True and empty capabilities
		probe_result = {"ok": True, "capabilities": [], "error": None}
		overrides = adapter.capability_overrides(probe_result)
		self.assertIsNone(overrides["supports_tools"])
		self.assertFalse(overrides["is_reasoning_model"])

	def test_generic_openai_adapter_supports_tools_always_none_on_success(self):
		"""Test that supports_tools stays None even when probe succeeds."""
		adapter = get_adapter("vllm")
		self.assertIsInstance(adapter, GenericOpenAIAdapter)

		# Test with ok=True (successful probe)
		probe_result = {"ok": True, "capabilities": [], "error": None}
		overrides = adapter.capability_overrides(probe_result)

		# The honest answer is "unknown", not False
		self.assertIsNone(overrides["supports_tools"],
			msg="GenericOpenAIAdapter cannot tell us tool support even on success")
		self.assertFalse(overrides["is_reasoning_model"])

	def test_generic_openai_adapter_supports_tools_always_none_on_failure(self):
		"""Test that supports_tools is None when probe fails too."""
		adapter = get_adapter("lmstudio")

		# Test with ok=False (failed probe)
		probe_result = {"ok": False, "capabilities": [], "error": "connection failed"}
		overrides = adapter.capability_overrides(probe_result)

		self.assertIsNone(overrides["supports_tools"])
		self.assertFalse(overrides["is_reasoning_model"])

	def test_get_adapter_mlx_exact_case(self):
		"""Test that 'mlx' brand returns MlxServerAdapter."""
		adapter = get_adapter("mlx")
		self.assertIsInstance(adapter, MlxServerAdapter)
		self.assertEqual(adapter.flavor(), "mlx_server")

	def test_get_adapter_mlx_uppercase(self):
		"""Test that 'MLX' (uppercase) returns MlxServerAdapter."""
		adapter = get_adapter("MLX")
		self.assertIsInstance(adapter, MlxServerAdapter)

	def test_get_adapter_mlx_mixed_case(self):
		"""Test that 'Mlx' (mixed case) returns MlxServerAdapter."""
		adapter = get_adapter("Mlx")
		self.assertIsInstance(adapter, MlxServerAdapter)

	def test_get_adapter_none_returns_ollama_regression(self):
		"""Regression test: None still returns OllamaAdapter, not MLX."""
		adapter = get_adapter(None)
		self.assertIsInstance(adapter, OllamaAdapter)
		self.assertNotIsInstance(adapter, MlxServerAdapter)


if __name__ == "__main__":
	unittest.main()
