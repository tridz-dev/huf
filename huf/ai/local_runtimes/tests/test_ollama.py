# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for OllamaAdapter.

The adapter itself never imports frappe, but `huf/__init__.py:4` does, so a
defensive stub is installed before the import below -- the same pattern as
`huf/ai/tests/test_local_runtime_provider_connection_permission.py`, so this
file behaves identically standalone and collected under a real bench.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_ollama.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

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

from huf.ai.local_runtimes.ollama import OllamaAdapter  # noqa: E402


class TestOllamaAdapter(unittest.TestCase):
	"""Test suite for OllamaAdapter."""

	def setUp(self):
		"""Set up test fixtures."""
		self.adapter = OllamaAdapter()
		self.api_base = "http://localhost:11434"

	def test_flavor_returns_ollama(self):
		"""Test that flavor() returns 'ollama'."""
		self.assertEqual(self.adapter.flavor(), "ollama")

	@patch("huf.ai.local_runtimes.ollama.requests.get")
	def test_probe_server_success(self, mock_get):
		"""Test successful server probe with available models."""
		mock_response = Mock()
		mock_response.json.return_value = {
			"models": [
				{"name": "llama2"},
				{"name": "mistral"},
				{"name": "neural-chat"},
			]
		}
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertTrue(result["ok"])
		self.assertEqual(result["models"], ["llama2", "mistral", "neural-chat"])
		self.assertIsNone(result["error"])
		mock_get.assert_called_once()

	@patch("huf.ai.local_runtimes.ollama.requests.get")
	def test_probe_server_unreachable(self, mock_get):
		"""Test probe_server when server is unreachable."""
		mock_get.side_effect = ConnectionError("Connection refused")

		result = self.adapter.probe_server(self.api_base)

		self.assertFalse(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIn("Connection refused", result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.get")
	def test_probe_server_http_error(self, mock_get):
		"""Test probe_server when server returns HTTP error."""
		mock_response = Mock()
		mock_response.raise_for_status.side_effect = Exception("HTTP 500")
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertFalse(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIn("HTTP 500", result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.get")
	def test_probe_server_empty_models(self, mock_get):
		"""Test probe_server with empty model list."""
		mock_response = Mock()
		mock_response.json.return_value = {"models": []}
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertTrue(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIsNone(result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_success_with_capabilities(self, mock_post):
		"""Test successful model probe with capabilities."""
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {
			"capabilities": ["tools", "thinking"]
		}
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "llama2")

		self.assertTrue(result["ok"])
		self.assertEqual(result["capabilities"], ["tools", "thinking"])
		self.assertIsNone(result["error"])
		mock_post.assert_called_once()
		# Verify that the model name was sent correctly (no prefix stripping needed)
		call_args = mock_post.call_args
		self.assertEqual(call_args[1]["json"]["name"], "llama2")

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_strips_ollama_chat_prefix(self, mock_post):
		"""Test that probe_model strips ollama_chat/ prefix."""
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"capabilities": ["tools"]}
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "ollama_chat/llama2")

		self.assertTrue(result["ok"])
		# Verify the prefix was stripped before sending
		call_args = mock_post.call_args
		self.assertEqual(call_args[1]["json"]["name"], "llama2")

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_strips_ollama_prefix(self, mock_post):
		"""Test that probe_model strips ollama/ prefix."""
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"capabilities": ["thinking"]}
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "ollama/mistral")

		self.assertTrue(result["ok"])
		# Verify the prefix was stripped before sending
		call_args = mock_post.call_args
		self.assertEqual(call_args[1]["json"]["name"], "mistral")

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_not_found(self, mock_post):
		"""Test probe_model when model is not pulled."""
		mock_response = Mock()
		mock_response.status_code = 404
		mock_response.json.return_value = {"error": "model not found"}
		mock_response.text = "model not found"
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "nonexistent")

		self.assertFalse(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIn("model not found", result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_http_error_without_json(self, mock_post):
		"""Test probe_model when server returns HTTP error without JSON."""
		mock_response = Mock()
		mock_response.status_code = 500
		mock_response.json.side_effect = Exception("Invalid JSON")
		mock_response.text = "Internal Server Error"
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "llama2")

		self.assertFalse(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIn("Internal Server Error", result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_connection_error(self, mock_post):
		"""Test probe_model when connection fails."""
		mock_post.side_effect = ConnectionError("Connection refused")

		result = self.adapter.probe_model(self.api_base, "llama2")

		self.assertFalse(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIn("Connection refused", result["error"])

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_empty_capabilities(self, mock_post):
		"""Test probe_model when capabilities list is empty."""
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"capabilities": []}
		mock_post.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "llama2")

		self.assertTrue(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIsNone(result["error"])

	def test_capability_overrides_probed_with_tools_and_thinking(self):
		"""A successful probe reporting both flags sets both True."""
		result = self.adapter.capability_overrides({"ok": True, "capabilities": ["tools", "thinking"], "error": None})
		self.assertEqual(result, {"supports_tools": True, "is_reasoning_model": True})

	def test_capability_overrides_probed_tools_only(self):
		"""A successful probe reporting only tools leaves reasoning False."""
		result = self.adapter.capability_overrides({"ok": True, "capabilities": ["tools"], "error": None})
		self.assertEqual(result, {"supports_tools": True, "is_reasoning_model": False})

	def test_capability_overrides_probed_thinking_only_is_definite_false(self):
		"""A successful probe WITHOUT tools is a definite False, not unknown.

		This is the case that a capabilities-list-only signature got wrong: the
		model was probed and did not advertise tools, so False -- not None.
		Mirrors local_runtime.py:183 (`"tools" in capabilities`).
		"""
		result = self.adapter.capability_overrides({"ok": True, "capabilities": ["thinking"], "error": None})
		self.assertEqual(result, {"supports_tools": False, "is_reasoning_model": True})

	def test_capability_overrides_probed_empty_list_is_definite_false(self):
		"""A successful probe returning no capabilities is False, not unknown."""
		result = self.adapter.capability_overrides({"ok": True, "capabilities": [], "error": None})
		self.assertEqual(result, {"supports_tools": False, "is_reasoning_model": False})

	def test_capability_overrides_failed_probe_stays_unknown(self):
		"""A FAILED probe is the only case that yields None -- unknown, not False."""
		result = self.adapter.capability_overrides({"ok": False, "capabilities": [], "error": "boom"})
		self.assertEqual(result, {"supports_tools": None, "is_reasoning_model": False})

	def test_capability_overrides_unknown_capability_only(self):
		"""An unrecognised capability does not imply tool support."""
		result = self.adapter.capability_overrides({"ok": True, "capabilities": ["vision"], "error": None})
		self.assertEqual(result, {"supports_tools": False, "is_reasoning_model": False})

	@patch("huf.ai.local_runtimes.ollama.requests.get")
	def test_probe_server_url_normalization(self, mock_get):
		"""Test that probe_server normalizes URLs with trailing slashes."""
		mock_response = Mock()
		mock_response.json.return_value = {"models": []}
		mock_get.return_value = mock_response

		# Call with trailing slash
		self.adapter.probe_server(f"{self.api_base}/")

		# Verify the URL was called without double slashes
		called_url = mock_get.call_args[0][0]
		self.assertNotIn("//api/tags", called_url)
		self.assertTrue(called_url.endswith("/api/tags"))

	@patch("huf.ai.local_runtimes.ollama.requests.post")
	def test_probe_model_url_normalization(self, mock_post):
		"""Test that probe_model normalizes URLs with trailing slashes."""
		mock_response = Mock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"capabilities": []}
		mock_post.return_value = mock_response

		# Call with trailing slash
		self.adapter.probe_model(f"{self.api_base}/", "llama2")

		# Verify the URL was called without double slashes
		called_url = mock_post.call_args[0][0]
		self.assertNotIn("//api/show", called_url)
		self.assertTrue(called_url.endswith("/api/show"))


if __name__ == "__main__":
	unittest.main()
