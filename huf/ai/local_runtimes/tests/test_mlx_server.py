# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for MlxServerAdapter.

The adapter itself never imports frappe, but `huf/__init__.py:4` does, so a
defensive stub is installed before the import below -- the same pattern as
`huf/ai/local_runtimes/tests/test_ollama.py`, so this file behaves identically
standalone and collected under a real bench.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/local_runtimes/tests/test_mlx_server.py -v
"""

import sys
import types
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

from huf.ai.local_runtimes.mlx_server import MlxServerAdapter  # noqa: E402


class TestMlxServerAdapter(unittest.TestCase):
	"""Test suite for MlxServerAdapter."""

	def setUp(self):
		"""Set up test fixtures."""
		self.adapter = MlxServerAdapter()
		self.api_base = "http://localhost:8000"

	def test_flavor_returns_mlx_server(self):
		"""Test that flavor() returns 'mlx_server'."""
		self.assertEqual(self.adapter.flavor(), "mlx_server")

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_success(self, mock_get):
		"""Test successful server probe with available models."""
		mock_response = Mock()
		mock_response.json.return_value = {
			"object": "list",
			"data": [
				{"id": "qwen2-0.5b", "object": "model"},
				{"id": "qwen2-1.5b", "object": "model"},
				{"id": "mistral-7b", "object": "model"},
			]
		}
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertTrue(result["ok"])
		self.assertEqual(result["models"], ["qwen2-0.5b", "qwen2-1.5b", "mistral-7b"])
		self.assertIsNone(result["error"])
		mock_get.assert_called_once()

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_unreachable(self, mock_get):
		"""Test probe_server when server is unreachable."""
		mock_get.side_effect = ConnectionError("Connection refused")

		result = self.adapter.probe_server(self.api_base)

		self.assertFalse(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIn("Connection refused", result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_http_error(self, mock_get):
		"""Test probe_server when server returns HTTP error."""
		mock_response = Mock()
		mock_response.raise_for_status.side_effect = Exception("HTTP 500")
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertFalse(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIn("HTTP 500", result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_empty_models(self, mock_get):
		"""Test probe_server with empty model list."""
		mock_response = Mock()
		mock_response.json.return_value = {"data": []}
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertTrue(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIsNone(result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_404_on_models_endpoint(self, mock_get):
		"""Test probe_server when /v1/models endpoint returns 404."""
		mock_response = Mock()
		mock_response.raise_for_status.side_effect = Exception("404 Not Found")
		mock_get.return_value = mock_response

		result = self.adapter.probe_server(self.api_base)

		self.assertFalse(result["ok"])
		self.assertEqual(result["models"], [])
		self.assertIn("404", result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_model_found(self, mock_get):
		"""Test successful model probe when model is in listing."""
		mock_response = Mock()
		mock_response.json.return_value = {
			"object": "list",
			"data": [
				{"id": "qwen2-0.5b", "object": "model"},
				{"id": "qwen2-1.5b", "object": "model"},
			]
		}
		mock_get.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "qwen2-0.5b")

		self.assertTrue(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIsNone(result["error"])
		mock_get.assert_called_once()

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_model_not_found(self, mock_get):
		"""Test probe_model when model is not in listing."""
		mock_response = Mock()
		mock_response.json.return_value = {
			"object": "list",
			"data": [
				{"id": "qwen2-0.5b", "object": "model"},
			]
		}
		mock_get.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "nonexistent-model")

		self.assertFalse(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIn("nonexistent-model", result["error"])
		self.assertIn("not found", result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_model_connection_error(self, mock_get):
		"""Test probe_model when connection fails."""
		mock_get.side_effect = ConnectionError("Connection refused")

		result = self.adapter.probe_model(self.api_base, "qwen2-0.5b")

		self.assertFalse(result["ok"])
		self.assertEqual(result["capabilities"], [])
		self.assertIn("Connection refused", result["error"])

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_model_capabilities_always_empty(self, mock_get):
		"""Test that probe_model always returns empty capabilities list."""
		mock_response = Mock()
		mock_response.json.return_value = {
			"object": "list",
			"data": [
				{"id": "qwen2-0.5b", "object": "model"},
			]
		}
		mock_get.return_value = mock_response

		result = self.adapter.probe_model(self.api_base, "qwen2-0.5b")

		self.assertTrue(result["ok"])
		# MLX server does not expose capabilities, so list is always empty
		self.assertEqual(result["capabilities"], [])

	def test_capability_overrides_successful_probe_is_none(self):
		"""Test that capability_overrides returns supports_tools: None even when probe succeeds."""
		probe_result = {"ok": True, "capabilities": [], "error": None}
		result = self.adapter.capability_overrides(probe_result)

		self.assertIsNone(result["supports_tools"])
		self.assertFalse(result["is_reasoning_model"])

	def test_capability_overrides_failed_probe_is_none(self):
		"""Test that capability_overrides returns supports_tools: None when probe fails."""
		probe_result = {"ok": False, "capabilities": [], "error": "connection failed"}
		result = self.adapter.capability_overrides(probe_result)

		self.assertIsNone(result["supports_tools"])
		self.assertFalse(result["is_reasoning_model"])

	def test_capability_overrides_always_returns_none_not_false(self):
		"""Test that supports_tools is None (unknown), never False.

		Unlike Ollama where a successful probe yields a definite True/False,
		MLX's server cannot tell us tool support at all, so None is the
		only honest answer -- unknown, never False.
		"""
		# Even if probe succeeds, supports_tools should be None
		result = self.adapter.capability_overrides({"ok": True, "capabilities": [], "error": None})
		self.assertIsNone(result["supports_tools"],
			msg="MLX server cannot tell us tool support, so None is correct, not False")

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_server_url_normalization(self, mock_get):
		"""Test that probe_server normalizes URLs with trailing slashes."""
		mock_response = Mock()
		mock_response.json.return_value = {"data": []}
		mock_get.return_value = mock_response

		# Call with trailing slash
		self.adapter.probe_server(f"{self.api_base}/")

		# Verify the URL was called without double slashes
		called_url = mock_get.call_args[0][0]
		self.assertNotIn("//v1/models", called_url)
		self.assertTrue(called_url.endswith("/v1/models"))

	@patch("huf.ai.local_runtimes.mlx_server.requests.get")
	def test_probe_model_url_normalization(self, mock_get):
		"""Test that probe_model normalizes URLs with trailing slashes."""
		mock_response = Mock()
		mock_response.json.return_value = {"data": [{"id": "qwen2-0.5b"}]}
		mock_get.return_value = mock_response

		# Call with trailing slash
		self.adapter.probe_model(f"{self.api_base}/", "qwen2-0.5b")

		# Verify the URL was called without double slashes
		called_url = mock_get.call_args[0][0]
		self.assertNotIn("//v1/models", called_url)
		self.assertTrue(called_url.endswith("/v1/models"))

	@patch("huf.ai.local_runtimes.mlx_server.mlx_probe.probe_device")
	def test_get_device_info_calls_mlx_probe(self, mock_probe):
		"""Test that get_device_info() returns MLX probe results."""
		expected_result = {
			"import_ok": True,
			"device": "Device(gpu, 0)",
			"metal_available": True,
			"mlx_version": "0.32.0",
		}
		mock_probe.return_value = expected_result

		result = self.adapter.get_device_info()

		self.assertEqual(result, expected_result)
		mock_probe.assert_called_once()

	@patch("huf.ai.local_runtimes.mlx_server.mlx_probe.probe_device")
	def test_describe_device_calls_describe_probe_result(self, mock_probe):
		"""Test that describe_device() returns a human-readable description."""
		mock_probe.return_value = {
			"import_ok": True,
			"device": "Device(gpu, 0)",
			"metal_available": True,
			"mlx_version": "0.32.0",
		}

		result = self.adapter.describe_device()

		self.assertIsInstance(result, str)
		self.assertTrue(len(result) > 0)
		# Should contain "MLX" or "Metal" or similar
		self.assertTrue("MLX" in result or "Metal" in result or "installed" in result.lower())

	@patch("huf.ai.local_runtimes.mlx_server.mlx_probe.probe_device")
	def test_describe_device_for_not_installed(self, mock_probe):
		"""Test that describe_device() handles not-installed state."""
		mock_probe.return_value = {
			"import_ok": False,
			"device": None,
			"metal_available": False,
			"mlx_version": None,
		}

		result = self.adapter.describe_device()

		self.assertIn("not installed", result.lower())

	@patch("huf.ai.local_runtimes.mlx_server.mlx_probe.probe_device")
	def test_describe_device_for_degraded(self, mock_probe):
		"""Test that describe_device() handles degraded (no Metal) state."""
		mock_probe.return_value = {
			"import_ok": True,
			"device": "Device(cpu, 0)",
			"metal_available": False,
			"mlx_version": "0.32.0",
		}

		result = self.adapter.describe_device()

		self.assertIn("degraded", result.lower())


class TestMlxServerAdapterOpenAICompatibility(unittest.TestCase):
	"""Test that MlxServerAdapter behaves like generic OpenAI for capability probing."""

	def setUp(self):
		"""Set up test fixtures."""
		self.adapter = MlxServerAdapter()

	def test_supports_tools_is_never_false_only_none(self):
		"""Test that supports_tools is never False, only None.

		This is the key difference from Ollama: MLX server cannot tell us
		anything about tool support, so we preserve the "unknown" state.
		"""
		# Test both ok=True and ok=False cases
		for ok_value in [True, False]:
			probe_result = {"ok": ok_value, "capabilities": [], "error": None if ok_value else "test"}
			overrides = self.adapter.capability_overrides(probe_result)
			self.assertIsNone(overrides["supports_tools"],
				msg=f"For ok={ok_value}, supports_tools should be None, not {overrides['supports_tools']}")

	def test_models_endpoint_not_ollama_tags(self):
		"""Test that we use /v1/models, not /api/tags (Ollama endpoint)."""
		with patch("huf.ai.local_runtimes.mlx_server.requests.get") as mock_get:
			mock_response = Mock()
			mock_response.json.return_value = {"data": []}
			mock_get.return_value = mock_response

			self.adapter.probe_server("http://localhost:8000")

			# Verify the correct endpoint was called
			called_url = mock_get.call_args[0][0]
			self.assertIn("/v1/models", called_url)
			self.assertNotIn("/api/tags", called_url)


if __name__ == "__main__":
	unittest.main()
