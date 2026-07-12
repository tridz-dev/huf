# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestHufRole(HufTestSuite):
	def _make_role(self, **overrides):
		doc = {
			"doctype": "Huf Role",
			"role_name": "_Test Huf Role",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_role_with_required_fields(self):
		role = self._make_role()

		# autoname is "field:role_name"
		self.assertEqual(role.name, "_Test Huf Role")
		self.assertFalse(role.is_system_role)

	def test_role_name_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Huf Role"}).insert(ignore_permissions=True)

	def test_unknown_capability_rejected(self):
		# HufRole._validate_capabilities() rejects anything not in CAPABILITIES.
		with self.assertRaises(frappe.ValidationError):
			self._make_role(
				role_name="_Test Huf Role Bad Capability",
				permissions=[{"doctype": "Huf Role Permission", "capability": "not.a.real.capability"}],
			)

	def test_known_capability_accepted_and_label_populated(self):
		role = self._make_role(
			role_name="_Test Huf Role Good Capability",
			permissions=[{"doctype": "Huf Role Permission", "capability": "agent.use"}],
		)

		self.assertEqual(len(role.permissions), 1)
		self.assertEqual(role.permissions[0].capability, "agent.use")
		# HufRolePermission.before_save() populates label from CAPABILITIES.
		self.assertTrue(role.permissions[0].label)

	def test_system_role_cannot_be_deleted(self):
		role = self._make_role(role_name="_Test Huf Role System", is_system_role=1)

		with self.assertRaises(frappe.PermissionError):
			role.delete()
