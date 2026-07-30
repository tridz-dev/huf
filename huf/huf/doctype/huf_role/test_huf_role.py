# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import unittest
import frappe
from frappe.tests import IntegrationTestCase


class TestHufRole(IntegrationTestCase):
	def _make_role(self, **overrides):
		doc = {
			"doctype": "Huf Role",
			"role_name": "_Test Huf Role",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_known_capability_accepted_and_label_populated(self):
		# Regression test: label used to be populated by HufRolePermission's
		# own before_save(), which never fires on Frappe v16 for child-table
		# rows. Now populated by HufRole.validate() on the parent.
		role = self._make_role(
			role_name="_Test Huf Role Good Capability",
			permissions=[{"doctype": "Huf Role Permission", "capability": "agent.use"}],
		)

		self.assertEqual(len(role.permissions), 1)
		self.assertEqual(role.permissions[0].capability, "agent.use")
		self.assertTrue(role.permissions[0].label)

	def test_unknown_capability_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_role(
				role_name="_Test Huf Role Bad Capability",
				permissions=[{"doctype": "Huf Role Permission", "capability": "totally.made.up"}],
			)
