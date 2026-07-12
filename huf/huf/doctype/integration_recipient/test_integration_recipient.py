# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestIntegrationRecipient(HufTestSuite):
	"""`Integration Recipient` is a child table (istable=1) of the
	`recipients` field on `Integration Settings`, so it is tested as rows
	on a parent Integration Settings. Controller has no custom logic, so
	tests cover creation + the required credential dependency + the
	optional User link."""

	def _make_service(self, service_name="_test_recipient_service"):
		if frappe.db.exists("Integration Service", service_name):
			return frappe.get_doc("Integration Service", service_name)
		return frappe.get_doc({
			"doctype": "Integration Service",
			"service_name": service_name,
			"category": "Other",
		}).insert(ignore_permissions=True)

	def _make_settings(self, recipients, service_name="_test_recipient_service"):
		service = self._make_service(service_name)
		return frappe.get_doc({
			"doctype": "Integration Settings",
			"service": service.name,
			"credentials": [{"doctype": "Integration Credential", "key": "api_key", "value": "secret"}],
			"recipients": recipients,
		}).insert(ignore_permissions=True)

	def test_recipient_row_saved_with_settings(self):
		settings = self._make_settings([
			{"doctype": "Integration Recipient", "recipient_name": "General Channel", "recipient_id": "C123"},
		])

		self.assertEqual(len(settings.recipients), 1)
		self.assertEqual(settings.recipients[0].recipient_name, "General Channel")
		self.assertEqual(settings.recipients[0].recipient_id, "C123")

	def test_recipient_optionally_links_a_user(self):
		settings = self._make_settings([
			{
				"doctype": "Integration Recipient",
				"recipient_name": "Admin DM",
				"recipient_id": "U456",
				"user": "Administrator",
			},
		])

		self.assertEqual(settings.recipients[0].user, "Administrator")

	def test_multiple_recipient_rows_kept(self):
		settings = self._make_settings([
			{"doctype": "Integration Recipient", "recipient_name": "Channel A", "recipient_id": "A1"},
			{"doctype": "Integration Recipient", "recipient_name": "Channel B", "recipient_id": "B1"},
		])

		self.assertEqual(
			{r.recipient_id for r in settings.recipients},
			{"A1", "B1"},
		)
