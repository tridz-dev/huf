# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestHufRolePermission(FrappeTestCase):
	"""`Huf Role Permission` is a child table (istable=1) of the `permissions`
	field on `Huf Role`, so it is tested as rows on a parent Huf Role."""

	def _make_role_with_permissions(self, capabilities):
		return frappe.get_doc({
			"doctype": "Huf Role",
			"role_name": "_Test Role Permission Parent",
			"permissions": [
				{"doctype": "Huf Role Permission", "capability": c} for c in capabilities
			],
		}).insert(ignore_permissions=True)

	def test_label_populated_from_capabilities_catalogue(self):
		# Regression test: label population moved from the child doctype's
		# before_save() (never fires on v16 for child-table rows) into the
		# parent HufRole.validate().
		role = self._make_role_with_permissions(["chat.use"])

		self.assertTrue(role.permissions[0].label)
		self.assertNotEqual(role.permissions[0].label, "chat.use")

	def test_multiple_permission_rows_each_get_a_label(self):
		role = self._make_role_with_permissions(["agent.use", "knowledge.use", "tools.manage"])

		self.assertEqual(len(role.permissions), 3)
		for row in role.permissions:
			self.assertTrue(row.label)
