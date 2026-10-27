"""Regression coverage for AI Provider API URL validation behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from huf.ai.provider_security import validate_api_base_url


class URLValidationError(Exception):
	pass


class TestProviderSecurity(unittest.TestCase):
	def test_allows_empty_remote_https_and_local_http_urls(self):
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


if __name__ == "__main__":
	unittest.main()
