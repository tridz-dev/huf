# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestGroqSettings(HufTestSuite):
	"""Groq Settings is a Single doctype — mutate/restore via change_settings
	rather than inserting new documents."""

	def test_get_headers_requires_api_key(self):
		with self.change_settings("Groq Settings", api_key=""):
			settings = frappe.get_single("Groq Settings")
			with self.assertRaises(frappe.ValidationError):
				settings.get_headers()

	def test_get_headers_returns_bearer_token_when_key_set(self):
		with self.change_settings("Groq Settings", api_key="test-groq-key"):
			settings = frappe.get_single("Groq Settings")
			headers = settings.get_headers()

			self.assertEqual(headers["Authorization"], "Bearer test-groq-key")
