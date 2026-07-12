# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAIProvider(HufTestSuite):
	def _make_provider(self, **overrides):
		doc = {
			"doctype": "AI Provider",
			"provider_name": "_Test Provider Extra",
			"provider_brand": "openai",
			"api_key": "not-a-real-key",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_provider_with_required_fields(self):
		provider = self._make_provider()

		# autoname is "field:provider_name"
		self.assertEqual(provider.name, "_Test Provider Extra")
		self.assertEqual(provider.provider_brand, "openai")

	def test_missing_provider_name_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "AI Provider",
				"provider_brand": "openai",
				"api_key": "not-a-real-key",
			}).insert(ignore_permissions=True)

	def test_missing_api_key_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "AI Provider",
				"provider_name": "_Test Provider No Key",
				"provider_brand": "openai",
			}).insert(ignore_permissions=True)

	def test_invalid_provider_brand_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_provider(
				provider_name="_Test Provider Bad Brand",
				provider_brand="not-a-real-brand",
			)

	def test_api_key_stored_as_password_field(self):
		provider = self._make_provider(provider_name="_Test Provider Password")
		# Password fields are masked on normal get_doc reads; get_password decrypts.
		self.assertEqual(provider.get_password("api_key"), "not-a-real-key")
