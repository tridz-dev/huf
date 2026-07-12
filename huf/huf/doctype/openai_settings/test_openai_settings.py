# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestOpenAISettings(HufTestSuite):
	"""OpenAI Settings is a Single doctype — there is exactly one instance,
	so tests mutate and restore it via self.change_settings rather than
	inserting new documents."""

	def test_get_headers_requires_api_key(self):
		with self.change_settings("OpenAI Settings", api_key=""):
			settings = frappe.get_single("OpenAI Settings")
			with self.assertRaises(frappe.ValidationError):
				settings.get_headers()

	def test_get_headers_returns_bearer_token_when_key_set(self):
		with self.change_settings("OpenAI Settings", api_key="test-openai-key"):
			settings = frappe.get_single("OpenAI Settings")
			headers = settings.get_headers()

			self.assertEqual(headers["Authorization"], "Bearer test-openai-key")
