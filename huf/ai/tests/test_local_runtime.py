# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for _resolve_api_base.

The _resolve_api_base function handles API base URL resolution for local
providers (Ollama, MLX, Laya). It prioritizes `api_base_url` field over
constructing from `url` + `port`, gated on `is_local_llm`. A defensive
frappe stub is installed before import so this file behaves identically
standalone and collected under a real bench.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_local_runtime.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock

try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe_mock.cache.return_value.get_value.return_value = None
	frappe_mock.cache.return_value.set_value.return_value = None
	frappe_utils_mock = MagicMock()
	frappe_utils_mock.cint = lambda x, default=0: int(x or default)
	sys.modules["frappe"] = frappe_mock
	sys.modules["frappe.utils"] = frappe_utils_mock

try:
	import requests  # noqa: F401
except ImportError:
	sys.modules["requests"] = MagicMock()

from huf.ai.local_runtime import _resolve_api_base  # noqa: E402


class TestResolveApiBase(unittest.TestCase):
	"""Test suite for _resolve_api_base function."""

	def test_returns_none_for_none_provider(self):
		"""Test that _resolve_api_base returns None for None provider."""
		result = _resolve_api_base(None)
		self.assertIsNone(result)

	def test_returns_none_for_is_local_llm_false(self):
		"""Test that _resolve_api_base returns None when is_local_llm is False."""
		provider_doc = {
			"is_local_llm": 0,
			"api_base_url": "http://localhost:11434",
		}
		result = _resolve_api_base(provider_doc)
		self.assertIsNone(result)

	def test_api_base_url_takes_precedence(self):
		"""Test that api_base_url field takes precedence over url+port.

		Protects: Ensuring explicit api_base_url override is used when set.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "http://192.168.1.50:8000",
			"url": "http://localhost",
			"port": 11434,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://192.168.1.50:8000")

	def test_api_base_url_stripped_of_whitespace(self):
		"""Test that api_base_url is stripped of leading/trailing whitespace."""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "  http://localhost:11434  ",
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:11434")

	def test_url_and_port_constructed(self):
		"""Test that url and port are combined when api_base_url is not set.

		Protects: Proper construction of URLs from separate url/port fields.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "http://192.168.1.50",
			"port": 8000,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://192.168.1.50:8000")

	def test_url_and_port_already_included(self):
		"""Test that port is not duplicated if url already ends with it."""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "http://192.168.1.50:8000",
			"port": 8000,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://192.168.1.50:8000")

	def test_url_with_trailing_slash_stripped(self):
		"""Test that trailing slashes are removed from url.

		Protects: Consistent URL formatting without double slashes in paths.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "http://localhost/",
			"port": 11434,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:11434")

	def test_url_only_without_port(self):
		"""Test that url is returned as-is when port is not set.

		Protects: Handling URLs that already contain the full address.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "http://localhost:11434",
			"port": "",
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:11434")

	def test_returns_none_for_missing_url(self):
		"""Test that None is returned when url is not set.

		Protects: Preventing resolution when no address information is available.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "",
			"port": 8000,
		}
		result = _resolve_api_base(provider_doc)
		self.assertIsNone(result)

	def test_url_stripped_of_whitespace(self):
		"""Test that url is stripped of leading/trailing whitespace."""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "  http://localhost  ",
			"port": 11434,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:11434")

	def test_port_stripped_of_whitespace(self):
		"""Test that port is stripped and converted to string properly."""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "",
			"url": "http://localhost",
			"port": "  8000  ",
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://localhost:8000")

	def test_precedence_api_base_url_over_url_port(self):
		"""Test that api_base_url takes precedence over url+port resolution.

		Protects: LAN scenario where both api_base_url and url/port are set,
		ensuring the explicit api_base_url (e.g., to a Mac's LAN IP) wins.
		"""
		provider_doc = {
			"is_local_llm": 1,
			"api_base_url": "http://192.168.1.50:8000",
			"url": "http://localhost",
			"port": 11434,
		}
		result = _resolve_api_base(provider_doc)
		self.assertEqual(result, "http://192.168.1.50:8000")


if __name__ == "__main__":
	unittest.main()
