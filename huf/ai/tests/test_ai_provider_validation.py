# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Unit tests for AI Provider URL validation (ST-R3.4).

Tests that the api_base_url field validation correctly:
- Allows HTTPS to public hostnames (e.g., api.openai.com)
- Allows HTTP/HTTPS to localhost and 127.0.0.1
- Rejects HTTP to private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Rejects HTTP to cloud metadata endpoints (169.254.169.254)
- Rejects HTTP to non-localhost remote hosts

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_ai_provider_validation
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.exceptions import ValidationError


class TestAIProviderURLValidation(IntegrationTestCase):
	"""Integration tests for AI Provider api_base_url validation."""

	def setUp(self):
		self._providers = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._providers:
			try:
				frappe.delete_doc("AI Provider", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	def _create_provider(self, api_base_url=None, **kwargs):
		"""Helper to create an AI Provider with the given api_base_url."""
		frappe.set_user("Administrator")
		defaults = {
			"provider_name": f"test-provider-{frappe.generate_hash(length=8)}",
			"provider_brand": "openai",
			"is_local_llm": 0,
			"api_key": "test-key-12345",
		}
		if api_base_url:
			defaults["api_base_url"] = api_base_url
		defaults.update(kwargs)

		provider = frappe.get_doc("AI Provider", defaults)
		self._providers.append(provider.name)
		return provider

	def test_empty_api_base_url_is_allowed(self):
		"""If api_base_url is not set, no validation error should be raised."""
		provider = self._create_provider(api_base_url=None)
		try:
			provider.insert()
		except ValidationError:
			self.fail("Empty api_base_url should be allowed")

	def test_https_public_hostname_is_allowed(self):
		"""HTTPS to a public hostname like api.openai.com should be allowed."""
		provider = self._create_provider(api_base_url="https://api.openai.com")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"HTTPS to public hostname should be allowed, got: {e}")

	def test_https_localhost_is_allowed(self):
		"""HTTPS to localhost:3000 should be allowed."""
		provider = self._create_provider(api_base_url="https://localhost:3000")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"HTTPS to localhost should be allowed, got: {e}")

	def test_http_localhost_is_allowed(self):
		"""HTTP to localhost:3000 should be allowed."""
		provider = self._create_provider(api_base_url="http://localhost:3000")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"HTTP to localhost should be allowed, got: {e}")

	def test_http_127_0_0_1_is_allowed(self):
		"""HTTP to 127.0.0.1 (loopback) should be allowed."""
		provider = self._create_provider(api_base_url="http://127.0.0.1:3000")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"HTTP to 127.0.0.1 should be allowed, got: {e}")

	def test_https_127_0_0_1_is_allowed(self):
		"""HTTPS to 127.0.0.1 (loopback) should be allowed."""
		provider = self._create_provider(api_base_url="https://127.0.0.1:3000")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"HTTPS to 127.0.0.1 should be allowed, got: {e}")

	def test_http_private_range_10_0_0_0_is_rejected(self):
		"""HTTP to 10.0.0.5 (private range 10.0.0.0/8) should be rejected."""
		provider = self._create_provider(api_base_url="http://10.0.0.5")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("private", str(ctx.exception).lower())

	def test_http_private_range_172_16_is_rejected(self):
		"""HTTP to 172.16.1.1 (private range 172.16.0.0/12) should be rejected."""
		provider = self._create_provider(api_base_url="http://172.16.1.1")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("private", str(ctx.exception).lower())

	def test_http_private_range_192_168_is_rejected(self):
		"""HTTP to 192.168.1.1 (private range 192.168.0.0/16) should be rejected."""
		provider = self._create_provider(api_base_url="http://192.168.1.1")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("private", str(ctx.exception).lower())

	def test_http_cloud_metadata_endpoint_is_rejected(self):
		"""HTTP to 169.254.169.254 (cloud metadata endpoint, link-local) should be rejected."""
		provider = self._create_provider(api_base_url="http://169.254.169.254")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("private", str(ctx.exception).lower())

	def test_https_private_range_is_rejected(self):
		"""HTTPS to a private IP should also be rejected."""
		provider = self._create_provider(api_base_url="https://10.0.0.5")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("private", str(ctx.exception).lower())

	def test_http_non_localhost_hostname_is_rejected(self):
		"""HTTP to a non-localhost remote hostname should be rejected."""
		provider = self._create_provider(api_base_url="http://example.com")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("http", str(ctx.exception).lower())

	def test_invalid_scheme_is_rejected(self):
		"""Non-HTTP/HTTPS schemes like ftp:// should be rejected."""
		provider = self._create_provider(api_base_url="ftp://example.com")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("http", str(ctx.exception).lower())

	def test_url_without_hostname_is_rejected(self):
		"""URLs without a hostname should be rejected."""
		provider = self._create_provider(api_base_url="http://")
		with self.assertRaises(ValidationError) as ctx:
			provider.insert()
		self.assertIn("hostname", str(ctx.exception).lower())

	def test_case_insensitive_localhost(self):
		"""localhost matching should be case-insensitive."""
		provider = self._create_provider(api_base_url="https://LOCALHOST:3000")
		try:
			provider.insert()
		except ValidationError as e:
			self.fail(f"Case-insensitive localhost should be allowed, got: {e}")

	def test_validation_on_update(self):
		"""api_base_url validation should also run on updates."""
		provider = self._create_provider(api_base_url="https://api.openai.com")
		provider.insert()

		# Update to an invalid URL
		provider.api_base_url = "http://10.0.0.5"
		with self.assertRaises(ValidationError) as ctx:
			provider.save()
		self.assertIn("private", str(ctx.exception).lower())


if __name__ == "__main__":
	import unittest
	unittest.main()
