# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestIntegrationSettings(HufTestSuite):
	def _make_service(self, service_name="_test_settings_service"):
		if frappe.db.exists("Integration Service", service_name):
			return frappe.get_doc("Integration Service", service_name)
		return frappe.get_doc({
			"doctype": "Integration Service",
			"service_name": service_name,
			"category": "Other",
		}).insert(ignore_permissions=True)

	def _make_settings(self, credentials=None, **overrides):
		service = self._make_service(overrides.pop("service_name", "_test_settings_service"))
		doc = {
			"doctype": "Integration Settings",
			"service": service.name,
			"credentials": credentials if credentials is not None else [
				{"doctype": "Integration Credential", "key": "api_key", "value": "secret"},
			],
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_settings_with_required_fields(self):
		settings = self._make_settings()

		self.assertEqual(settings.service, "_test_settings_service")
		self.assertEqual(len(settings.credentials), 1)

	def test_service_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Integration Settings",
				"credentials": [{"doctype": "Integration Credential", "key": "api_key", "value": "secret"}],
			}).insert(ignore_permissions=True)

	def test_at_least_one_credential_required(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_settings(credentials=[], service_name="_test_settings_no_creds")

	def test_invalid_service_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Integration Settings",
				"service": "_Nonexistent Service",
				"credentials": [{"doctype": "Integration Credential", "key": "api_key", "value": "secret"}],
			}).insert(ignore_permissions=True)

	def test_get_credential_returns_matching_value(self):
		settings = self._make_settings(
			credentials=[
				{"doctype": "Integration Credential", "key": "api_key", "value": "key-value"},
				{"doctype": "Integration Credential", "key": "api_secret", "value": "secret-value"},
			],
			service_name="_test_settings_get_credential",
		)

		self.assertEqual(settings.get_credential("api_secret"), "secret-value")

	def test_get_credential_returns_none_for_missing_key(self):
		settings = self._make_settings(service_name="_test_settings_missing_key")

		self.assertIsNone(settings.get_credential("nonexistent_key"))
