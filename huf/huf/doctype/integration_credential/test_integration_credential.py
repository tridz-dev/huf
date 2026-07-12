# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestIntegrationCredential(HufTestSuite):
	"""`Integration Credential` is a child table (istable=1) of the
	`credentials` field on `Integration Settings`, so it is tested as rows
	on a parent Integration Settings."""

	def _make_service(self, service_name="_test_cred_service"):
		if frappe.db.exists("Integration Service", service_name):
			return frappe.get_doc("Integration Service", service_name)
		return frappe.get_doc({
			"doctype": "Integration Service",
			"service_name": service_name,
			"category": "Other",
		}).insert(ignore_permissions=True)

	def _make_settings(self, credentials, service_name="_test_cred_service"):
		service = self._make_service(service_name)
		return frappe.get_doc({
			"doctype": "Integration Settings",
			"service": service.name,
			"credentials": credentials,
		}).insert(ignore_permissions=True)

	def test_credential_row_saved_with_settings(self):
		settings = self._make_settings([
			{"doctype": "Integration Credential", "key": "api_key", "value": "secret-value"},
		])

		self.assertEqual(len(settings.credentials), 1)
		self.assertEqual(settings.credentials[0].key, "api_key")
		self.assertEqual(settings.credentials[0].get_password("value"), "secret-value")

	def test_credential_key_required(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_settings([
				{"doctype": "Integration Credential", "value": "secret-value"},
			], service_name="_test_cred_service_no_key")

	def test_credential_value_required(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_settings([
				{"doctype": "Integration Credential", "key": "api_key"},
			], service_name="_test_cred_service_no_value")
