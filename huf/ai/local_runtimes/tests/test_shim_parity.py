# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) parity tests for T1.04 refactor.

The T1.04 refactor moved local probing behind huf.ai.local_runtimes adapter
package, delegating from the original huf.ai.local_runtime.py surface. This
suite proves the refactor preserved the module's externally observable contract:

1. Cache key format unchanged — reads/writes exactly `huf_local_probe|{api_base}|{model_name}`
2. TTL unchanged — set_value passes `expires_in_sec=3600`
3. Cache-before-probe ordering — when cached, adapter's probe_model is never called
4. test_provider_connection is still whitelisted — attribute present on function
5. Signature unchanged — exact five parameter names and defaults
6. supports_tools parity — None for unprobed/failed, False for no tools
7. _resolve_api_base precedence — api_base_url > url+port > None (when is_local_llm)
8. build_local_overrides always returns api_base key — even on early return paths

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_shim_parity.py -v
"""

import inspect
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Defensive frappe stub: only stub when the real package isn't importable,
# so this file behaves identically standalone and collected under a real bench.
# CRITICAL: @frappe.whitelist() must be a transparent identity decorator, or
# the imported test_provider_connection is a bare MagicMock and tests nothing.
try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock.utils = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock
	sys.modules["frappe.utils"] = frappe_mock.utils

try:
	import requests  # noqa: F401
except ImportError:
	sys.modules["requests"] = MagicMock()

# Import the module under test *after* stubs are in place
from huf.ai import local_runtime  # noqa: E402


def _make_provider_doc(**overrides):
	"""Create a mock provider document with common fields."""
	fields = {
		"is_local_llm": 1,
		"api_base_url": None,
		"url": None,
		"port": None,
		"provider_brand": "ollama",
	}
	fields.update(overrides)
	doc = SimpleNamespace(**fields)
	doc.get = lambda key, default=None: getattr(doc, key, default)
	doc.get_password = MagicMock(return_value="stored-secret-key")
	return doc


class TestCacheKeyFormat(unittest.TestCase):
	"""Assertion 1: Cache key format unchanged."""

	def test_cache_key_format(self):
		"""Assert cache key is exactly 'huf_local_probe|{api_base}|{model_name}'."""
		api_base = "http://localhost:11434"
		model_name = "llama2"
		expected_key = f"huf_local_probe|{api_base}|{model_name}"

		# Mock the cache to capture the key written
		mock_cache = MagicMock()
		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_cache.get_value.return_value = None  # Cache miss
			mock_adapter = MagicMock()
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": ["tools"],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": True,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				local_runtime.build_local_overrides(provider_doc, model_name)

		# Verify the exact cache key was passed
		mock_cache.set_value.assert_called_once()
		actual_key = mock_cache.set_value.call_args[0][0]
		self.assertEqual(actual_key, expected_key)


class TestCacheTTL(unittest.TestCase):
	"""Assertion 2: TTL unchanged (expires_in_sec=3600)."""

	def test_cache_ttl_is_3600(self):
		"""Assert set_value passes expires_in_sec=3600."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_cache.get_value.return_value = None  # Cache miss
			mock_adapter = MagicMock()
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": [],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": False,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				local_runtime.build_local_overrides(provider_doc, model_name)

		# Verify expires_in_sec is exactly 3600
		mock_cache.set_value.assert_called_once()
		self.assertEqual(mock_cache.set_value.call_args[1]["expires_in_sec"], 3600)


class TestCacheBeforeProbeOrdering(unittest.TestCase):
	"""Assertion 3: Cache is checked before probe; cached value short-circuits probe."""

	def test_cached_value_skips_probe(self):
		"""Assert when cache hit, adapter.probe_model is never called."""
		api_base = "http://localhost:11434"
		model_name = "llama2"
		cached_overrides = {
			"supports_tools": True,
			"is_reasoning_model": False,
			"api_base": api_base,
		}

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = cached_overrides  # Cache HIT

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		# Verify cached value is returned and probe_model never runs
		self.assertEqual(result, cached_overrides)
		mock_adapter.probe_model.assert_not_called()

	def test_cache_miss_calls_probe(self):
		"""Assert when cache miss, adapter.probe_model is called."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache MISS

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": ["tools"],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": True,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				local_runtime.build_local_overrides(provider_doc, model_name)

		# Verify probe was called on cache miss
		mock_adapter.probe_model.assert_called_once_with(api_base, model_name)


class TestProviderConnectionWhitelistDecorator(unittest.TestCase):
	"""Assertion 4: test_provider_connection is still whitelisted."""

	def test_whitelisted_decorator_present(self):
		"""Assert test_provider_connection has whitelist marker."""
		# In the real frappe, @frappe.whitelist() sets __wrapped__ or similar;
		# in our stub, the decorator is identity, so we check the source code.
		source = inspect.getsource(local_runtime.test_provider_connection)
		self.assertIn("@frappe.whitelist()", source)


class TestProviderConnectionSignature(unittest.TestCase):
	"""Assertion 5: test_provider_connection signature is exactly 5 params + defaults."""

	def test_signature_has_five_parameters(self):
		"""Assert function has exactly 5 parameters."""
		sig = inspect.signature(local_runtime.test_provider_connection)
		params = list(sig.parameters.keys())
		self.assertEqual(len(params), 5)

	def test_parameter_names_and_defaults(self):
		"""Assert exact parameter names and defaults."""
		sig = inspect.signature(local_runtime.test_provider_connection)
		params = sig.parameters

		# Expected: provider_name (required), api_key, api_base_url, provider_brand, is_local_llm (all optional)
		self.assertIn("provider_name", params)
		self.assertEqual(params["provider_name"].default, inspect.Parameter.empty)

		self.assertIn("api_key", params)
		self.assertIsNone(params["api_key"].default)

		self.assertIn("api_base_url", params)
		self.assertIsNone(params["api_base_url"].default)

		self.assertIn("provider_brand", params)
		self.assertIsNone(params["provider_brand"].default)

		self.assertIn("is_local_llm", params)
		self.assertIsNone(params["is_local_llm"].default)


class TestSupportsToolsParity(unittest.TestCase):
	"""Assertion 6: supports_tools is None for unprobed/failed, False for definitively no tools."""

	def test_unprobed_returns_none(self):
		"""Assert unprobed/failed model yields supports_tools=None."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache miss

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			# Failed probe
			mock_adapter.probe_model.return_value = {
				"ok": False,
				"capabilities": [],
				"error": "Connection failed",
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": None,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertIsNone(result["supports_tools"])

	def test_probed_without_tools_returns_false(self):
		"""Assert successfully probed model without tools yields supports_tools=False."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache miss

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			# Successful probe with empty capabilities
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": [],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": False,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertFalse(result["supports_tools"])

	def test_probed_with_tools_returns_true(self):
		"""Assert successfully probed model with tools yields supports_tools=True."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache miss

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			# Successful probe with tools capability
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": ["tools"],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": True,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertTrue(result["supports_tools"])


class TestResolveApiBasePrecedence(unittest.TestCase):
	"""Assertion 7: _resolve_api_base precedence: api_base_url > url+port > None."""

	def test_api_base_url_wins(self):
		"""Assert api_base_url field wins when set."""
		provider_doc = _make_provider_doc(
			is_local_llm=1,
			api_base_url="http://custom.example.com:8000",
			url="http://localhost",
			port=11434,
		)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertEqual(result, "http://custom.example.com:8000")

	def test_url_port_compose_when_api_base_not_set(self):
		"""Assert url + port compose when api_base_url is not set."""
		provider_doc = _make_provider_doc(
			is_local_llm=1, api_base_url=None, url="http://localhost", port=11434
		)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:11434")

	def test_url_only_when_no_port(self):
		"""Assert url alone is returned when port is empty."""
		provider_doc = _make_provider_doc(is_local_llm=1, api_base_url=None, url="http://localhost", port=None)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost")

	def test_trailing_slash_stripped_from_url(self):
		"""Assert trailing slash is stripped from url."""
		provider_doc = _make_provider_doc(is_local_llm=1, api_base_url=None, url="http://localhost/", port=None)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost")

	def test_none_when_not_local_llm(self):
		"""Assert None when is_local_llm is falsy."""
		provider_doc = _make_provider_doc(is_local_llm=0, api_base_url="http://example.com", url="http://localhost", port=11434)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertIsNone(result)

	def test_none_when_no_url_set(self):
		"""Assert None when neither api_base_url nor url is set."""
		provider_doc = _make_provider_doc(is_local_llm=1, api_base_url=None, url=None, port=11434)
		result = local_runtime._resolve_api_base(provider_doc)
		self.assertIsNone(result)

	def test_none_when_provider_doc_is_none(self):
		"""Assert None when provider_doc is None."""
		result = local_runtime._resolve_api_base(None)
		self.assertIsNone(result)


class TestBuildLocalOverridesAlwaysReturnsApiBase(unittest.TestCase):
	"""Assertion 8: build_local_overrides always returns api_base key (even on early return)."""

	def test_returns_api_base_on_successful_probe(self):
		"""Assert api_base key is present in result after successful probe."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache miss

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			mock_adapter.probe_model.return_value = {
				"ok": True,
				"capabilities": ["tools"],
				"error": None,
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": True,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertIn("api_base", result)
		self.assertEqual(result["api_base"], api_base)

	def test_returns_api_base_on_failed_probe(self):
		"""Assert api_base key is present even when probe fails."""
		api_base = "http://localhost:11434"
		model_name = "llama2"

		mock_cache = MagicMock()
		mock_cache.get_value.return_value = None  # Cache miss

		with patch.object(local_runtime.frappe, "cache", return_value=mock_cache):
			mock_adapter = MagicMock()
			mock_adapter.probe_model.return_value = {
				"ok": False,
				"capabilities": [],
				"error": "Connection refused",
			}
			mock_adapter.capability_overrides.return_value = {
				"supports_tools": None,
				"is_reasoning_model": False,
			}

			with patch("huf.ai.local_runtime.get_adapter", return_value=mock_adapter):
				provider_doc = _make_provider_doc(api_base_url=api_base)
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertIn("api_base", result)
		self.assertEqual(result["api_base"], api_base)

	def test_returns_api_base_when_no_api_base_resolves(self):
		"""Assert api_base is present and None when _resolve_api_base returns None."""
		model_name = "llama2"

		# No api_base_url, no url, no port
		provider_doc = _make_provider_doc(is_local_llm=1, api_base_url=None, url=None, port=None)

		with patch.object(local_runtime.frappe, "cache"):
			with patch("huf.ai.local_runtime.get_adapter"):
				result = local_runtime.build_local_overrides(provider_doc, model_name)

		self.assertIn("api_base", result)
		self.assertIsNone(result["api_base"])


if __name__ == "__main__":
	unittest.main()
