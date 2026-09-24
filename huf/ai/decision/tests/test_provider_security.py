"""Regression coverage for AI Provider API URL validation behavior.

Layer A (mocked-frappe, no bench) unit tests for validate_api_base_url. A
defensive frappe stub is installed before import so this file behaves
identically standalone and collected under a real bench.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/decision/tests/test_provider_security.py -v
"""

from __future__ import annotations

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

from huf.ai.provider_security import validate_api_base_url  # noqa: E402


class URLValidationError(Exception):
	pass


class TestProviderSecurity(unittest.TestCase):
	def test_allows_empty_remote_https_and_local_http_urls(self):
		"""Test allow_private=False (default): empty, HTTPS remote, localhost HTTP allowed."""
		allowed_urls = (
			None,
			"",
			"https://api.example.com/v1",
			"http://localhost:11434",
			"http://127.0.0.1:11434",
			"http://[::1]:11434",
		)
		for url in allowed_urls:
			with self.subTest(url=url):
				validate_api_base_url(url)

	def test_rejects_non_http_remote_http_and_private_ip_urls(self):
		"""Test allow_private=False (default): FTP, remote HTTP, and private IPs rejected."""
		rejected_urls = (
			"ftp://api.example.com",
			"http://api.example.com",
			"https://10.0.0.5",
			"https://192.168.1.2",
			"https://[fd00::1]",
		)
		for url in rejected_urls:
			with self.subTest(url=url), patch(
				"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
			):
				with self.assertRaises(URLValidationError):
					validate_api_base_url(url)

	def test_allow_private_true_accepts_private_ips_and_http(self):
		"""Test allow_private=True: private IPs and HTTP scheme accepted for any host."""
		allowed_urls = (
			"http://10.0.0.5:8000",
			"http://192.168.1.2:8000",
			"https://192.168.1.2",
			"http://[fd00::1]:8000",
			"http://172.16.0.1:8000",
			"http://169.254.1.1:8000",
			"http://[fe80::1]:8000",
		)
		for url in allowed_urls:
			with self.subTest(url=url):
				validate_api_base_url(url, allow_private=True)

	def test_allow_private_true_still_rejects_invalid_schemes(self):
		"""Test allow_private=True: invalid schemes (non-HTTP/HTTPS) still rejected."""
		rejected_urls = (
			"ftp://10.0.0.5",
			"gopher://192.168.1.2",
			"telnet://[fd00::1]",
		)
		for url in rejected_urls:
			with self.subTest(url=url), patch(
				"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
			):
				with self.assertRaises(URLValidationError):
					validate_api_base_url(url, allow_private=True)

	def test_allow_private_false_still_rejects_private_ips(self):
		"""Test allow_private=False (default): private IPs rejected even with HTTP."""
		rejected_urls = (
			"http://10.0.0.5",
			"https://192.168.1.2",
			"http://[fd00::1]",
		)
		for url in rejected_urls:
			with self.subTest(url=url), patch(
				"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
			):
				with self.assertRaises(URLValidationError):
					validate_api_base_url(url, allow_private=False)

	def test_localhost_explicitly_passes_with_allow_private_false(self):
		"""Test that localhost, 127.0.0.1, and ::1 pass even with allow_private=False.

		Protects: Linux bench reaching local development providers over localhost.
		"""
		localhost_urls = (
			"http://localhost:11434",
			"http://127.0.0.1:11434",
			"http://[::1]:11434",
			"https://localhost:11434",
			"https://127.0.0.1:11434",
			"https://[::1]:11434",
		)
		for url in localhost_urls:
			with self.subTest(url=url):
				validate_api_base_url(url, allow_private=False)

	def test_private_lan_ip_rejected_with_allow_private_false(self):
		"""Test that private LAN IPs are rejected when allow_private=False.

		Protects: Preventing unauthorized access to private network addresses
		without explicit opt-in.
		"""
		rejected_urls = (
			"http://192.168.1.50:8000",
			"http://192.168.1.50",
			"https://192.168.1.50:8000",
			"http://10.0.0.100:8888",
			"http://172.16.0.50:8080",
		)
		for url in rejected_urls:
			with self.subTest(url=url), patch(
				"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
			):
				with self.assertRaises(URLValidationError):
					validate_api_base_url(url, allow_private=False)

	def test_private_lan_ip_accepted_with_allow_private_true(self):
		"""Test that private LAN IPs are accepted when allow_private=True.

		Protects: Linux bench reaching an MLX server on a Mac at a private LAN IP.
		This is the deployment shape that makes MLX useful to non-Mac deployments.
		"""
		allowed_urls = (
			"http://192.168.1.50:8000",
			"http://192.168.1.50",
			"https://192.168.1.50:8000",
			"http://10.0.0.100:8888",
			"http://172.16.0.50:8080",
			"https://172.16.0.50",
		)
		for url in allowed_urls:
			with self.subTest(url=url):
				validate_api_base_url(url, allow_private=True)

	def test_no_hostname_rejected(self):
		"""Test that URLs with no hostname are rejected.

		Protects: Malformed URLs that fail to parse a hostname.
		"""
		with patch(
			"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
		):
			with self.assertRaises(URLValidationError):
				validate_api_base_url("http://")

	def test_public_http_rejected_with_allow_private_false(self):
		"""Test that plain HTTP for public hosts is rejected when allow_private=False.

		Protects: Enforcing HTTPS for remote public endpoints, while allowing HTTP
		for localhost (the local development case).
		"""
		with patch(
			"huf.ai.provider_security.frappe.throw", side_effect=URLValidationError
		):
			with self.assertRaises(URLValidationError):
				validate_api_base_url("http://api.example.com:8080", allow_private=False)

	def test_public_https_accepted_with_allow_private_false(self):
		"""Test that HTTPS for public hosts is accepted when allow_private=False.

		Protects: Permitting secure remote endpoints.
		"""
		validate_api_base_url("https://api.example.com:8080", allow_private=False)


if __name__ == "__main__":
	unittest.main()
