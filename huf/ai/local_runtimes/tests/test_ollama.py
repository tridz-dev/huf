# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for OllamaAdapter implementation.
"""

import unittest
from unittest.mock import Mock, patch

from ..ollama import OllamaAdapter


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

	def test_capability_overrides_with_tools_and_thinking(self):
		"""Test capability_overrides when both tools and thinking are present."""
		result = self.adapter.capability_overrides(["tools", "thinking"])

		self.assertTrue(result["supports_tools"])
		self.assertTrue(result["is_reasoning_model"])

	def test_capability_overrides_with_tools_only(self):
		"""Test capability_overrides with only tools capability."""
		result = self.adapter.capability_overrides(["tools"])

		self.assertTrue(result["supports_tools"])
		self.assertFalse(result["is_reasoning_model"])

	def test_capability_overrides_with_thinking_only(self):
		"""Test capability_overrides with only thinking capability."""
		result = self.adapter.capability_overrides(["thinking"])

		self.assertIsNone(result["supports_tools"])
		self.assertTrue(result["is_reasoning_model"])

	def test_capability_overrides_with_unknown_capability(self):
		"""Test capability_overrides with unknown capability."""
		result = self.adapter.capability_overrides(["unknown_feature"])

		self.assertIsNone(result["supports_tools"])
		self.assertFalse(result["is_reasoning_model"])

	def test_capability_overrides_empty_list(self):
		"""Test capability_overrides when capabilities list is empty."""
		result = self.adapter.capability_overrides([])

		self.assertIsNone(result["supports_tools"])
		self.assertFalse(result["is_reasoning_model"])

	def test_capability_overrides_none_stays_unknown(self):
		"""Test that unknown supports_tools status stays None, never False."""
		# When capabilities is empty, supports_tools must be None (unknown)
		result = self.adapter.capability_overrides([])
		self.assertIsNone(result["supports_tools"], "supports_tools must be None for empty capabilities, not False")

		# When only thinking is present, supports_tools is still unknown
		result = self.adapter.capability_overrides(["thinking"])
		self.assertIsNone(result["supports_tools"], "supports_tools must be None when tools not probed")

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
