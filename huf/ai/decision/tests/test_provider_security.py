"""Regression coverage for AI Provider API URL validation behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from huf.ai.provider_security import validate_api_base_url


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


if __name__ == "__main__":
	unittest.main()
