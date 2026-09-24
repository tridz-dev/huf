# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for AI Provider's local
network-exposed-API-key validation gate.

The check is exercised as a plain function (`requires_auth_for_network_exposed_local_llm`)
against light stub inputs, rather than constructing a real Frappe Document,
since a Document subclass is awkward to instantiate without a bench.

`huf/__init__.py` imports frappe, so a defensive stub is installed before the
import below -- the same pattern as `huf/ai/local_runtimes/tests/test_ollama.py`.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_ai_provider.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
	import frappe  # noqa: F401
	from frappe.model.document import Document  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock

	frappe_model_mock = MagicMock()
	sys.modules["frappe.model"] = frappe_model_mock

	frappe_model_document_mock = MagicMock()
	frappe_model_document_mock.Document = object
	sys.modules["frappe.model.document"] = frappe_model_document_mock

from huf.ai import provider_security  # noqa: E402
from huf.huf.doctype.ai_provider.ai_provider import (  # noqa: E402
	requires_auth_for_network_exposed_local_llm,
)


class TestRequiresAuthForNetworkExposedLocalLLM(unittest.TestCase):
	"""Test suite for the mlx/laya network-exposure validation gate."""

	def test_mlx_lan_ip_no_key_raises(self):
		"""mlx + LAN IP + no key -> must be flagged."""
		self.assertTrue(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://192.168.1.50:8080", ""
			)
		)

	def test_mlx_lan_ip_sentinel_raises(self):
		"""mlx + LAN IP + 'not-needed' sentinel -> must be flagged.

		This is the case a naive `if not self.api_key` check would miss,
		since validate_api_key() always stamps the sentinel first.
		"""
		self.assertTrue(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://192.168.1.50:8080", "not-needed"
			)
		)

	def test_mlx_lan_ip_real_key_passes(self):
		"""mlx + LAN IP + real key -> not flagged."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://192.168.1.50:8080", "sk-real-secret-key"
			)
		)

	def test_mlx_localhost_no_key_passes(self):
		"""mlx + localhost + no key -> not flagged (loopback exemption)."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://localhost:8080", ""
			)
		)

	def test_mlx_127_0_0_1_no_key_passes(self):
		"""mlx + 127.0.0.1 + no key -> not flagged (loopback exemption)."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://127.0.0.1:8080", ""
			)
		)

	def test_mlx_ipv6_loopback_no_key_passes(self):
		"""mlx + ::1 + no key -> not flagged (loopback exemption)."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 1, "http://[::1]:8080", ""
			)
		)

	def test_laya_lan_ip_sentinel_raises(self):
		"""laya + LAN IP + sentinel -> must be flagged."""
		self.assertTrue(
			requires_auth_for_network_exposed_local_llm(
				"laya", 1, "http://10.0.0.5:9000", "not-needed"
			)
		)

	def test_mlx_schemeless_loopback_host_passes(self):
		"""A scheme-less loopback value in the free-form `url` field is exempt.

		`url` is a Data field with no scheme validation -- only `api_base_url`
		goes through validate_api_base_url -- so "localhost" / "127.0.0.1" with a
		separate port is a legitimate config. Without normalisation urlparse
		returns no hostname for these and the guard would block the commonest
		local setup.
		"""
		for value in ("localhost", "127.0.0.1", "::1"):
			with self.subTest(url=value):
				self.assertFalse(
					requires_auth_for_network_exposed_local_llm("mlx", 1, value, "not-needed")
				)

	def test_mlx_schemeless_lan_ip_still_raises(self):
		"""Normalising a scheme-less value must not open the LAN hole it closes."""
		self.assertTrue(
			requires_auth_for_network_exposed_local_llm("mlx", 1, "192.168.1.50", "not-needed")
		)

	def test_ollama_lan_ip_sentinel_passes(self):
		"""ollama + LAN IP + sentinel -> NOT flagged.

		Trap-2 regression guard: Ollama/LM Studio providers are is_local_llm=1
		and unauthenticated by design, carrying the 'not-needed' sentinel on
        every existing row. This rule must not generalise to them, or every
        existing install with a LAN-reachable Ollama server becomes
        unsaveable on its next edit.
		"""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"ollama", 1, "http://192.168.1.50:11434", "not-needed"
			)
		)

	def test_lm_studio_lan_ip_sentinel_passes(self):
		"""lm_studio + LAN IP + sentinel -> NOT flagged (Trap-2 guard)."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"lm_studio", 1, "http://192.168.1.50:1234", "not-needed"
			)
		)

	def test_mlx_not_local_llm_passes(self):
		"""mlx but is_local_llm=0 -> rule does not apply."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm(
				"mlx", 0, "http://192.168.1.50:8080", ""
			)
		)

	def test_mlx_no_base_url_passes(self):
		"""mlx with no base URL at all -> nothing to evaluate, not flagged."""
		self.assertFalse(
			requires_auth_for_network_exposed_local_llm("mlx", 1, "", "")
		)


class _Rejected(Exception):
	"""Stand-in for the error frappe.throw would raise under a real bench."""


class TestApiBaseUrlAllowsPrivateForLocalProviders(unittest.TestCase):
	"""F-A3: the DocType validation path must honour is_local_llm.

	`validate_api_base_url(self.api_base_url)` was called with the default
	`allow_private=False`, so a local provider pointed at a LAN address was
	rejected before it could be saved -- which is exactly the documented
	cross-platform shape (a Linux/Docker bench driving MLX or laya-serve on
	another machine). The decision transport already got this right
	(`systemone_http.py` passes `allow_private=bool(is_local_llm)`); the
	DocType path did not.

	The earlier tests in this file all call the pure guard helper directly,
	which is precisely why none of them caught this -- so these go through
	`validate_api_base_url` itself.
	"""

	def test_lan_url_rejected_when_not_local(self):
		"""A cloud provider must still not point at a private address.

		`frappe.throw` is a MagicMock under the module-level stub and therefore
		does NOT raise, so asserting a rejection requires giving it a
		side_effect -- otherwise this test would pass vacuously whether or not
		the rejection happened. (`huf/ai/decision/tests/test_provider_security.py`
		uses the same technique for the same reason.)
		"""
		with patch(
			"huf.ai.provider_security.frappe.throw", side_effect=_Rejected
		) as mock_throw:
			with self.assertRaises(_Rejected):
				provider_security.validate_api_base_url(
					"http://192.168.1.50:8080", allow_private=False
				)
			self.assertTrue(mock_throw.called)

	def test_lan_url_allowed_when_local(self):
		"""is_local_llm=1 is what makes the LAN deployment shape saveable."""
		provider_security.validate_api_base_url(
			"http://192.168.1.50:8080", allow_private=True
		)

	def test_loopback_allowed_either_way(self):
		"""Loopback never needed allow_private and must not start needing it."""
		for allow in (False, True):
			with self.subTest(allow_private=allow):
				provider_security.validate_api_base_url(
					"http://127.0.0.1:8080", allow_private=allow
				)


if __name__ == "__main__":
	unittest.main()
