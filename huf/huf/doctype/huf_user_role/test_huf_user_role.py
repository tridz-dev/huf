# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestHufUserRole(HufTestSuite):
	TEST_USER_EMAIL = "_test_huf_user_role@example.com"

	def _make_user(self):
		if frappe.db.exists("User", self.TEST_USER_EMAIL):
			return frappe.get_doc("User", self.TEST_USER_EMAIL)
		return frappe.get_doc({
			"doctype": "User",
			"email": self.TEST_USER_EMAIL,
			"first_name": "_Test Huf User Role",
			"send_welcome_email": 0,
		}).insert(ignore_permissions=True)

	def _make_huf_role(self, role_name, frappe_role="Huf User"):
		if frappe.db.exists("Huf Role", role_name):
			return frappe.get_doc("Huf Role", role_name)
		return frappe.get_doc({
			"doctype": "Huf Role",
			"role_name": role_name,
			"frappe_role": frappe_role,
		}).insert(ignore_permissions=True)

	def test_required_fields(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Huf User Role"}).insert(ignore_permissions=True)

	def test_invited_on_and_by_set_on_insert(self):
		user = self._make_user()
		role = self._make_huf_role("_Test Huf User Role Role")

		link = frappe.get_doc({
			"doctype": "Huf User Role",
			"user": user.name,
			"huf_role": role.name,
		}).insert(ignore_permissions=True)

		self.assertTrue(link.invited_on)
		self.assertEqual(link.invited_by, frappe.session.user)

	def test_enabled_defaults_to_true(self):
		user = self._make_user()
		role = self._make_huf_role("_Test Huf User Role Enabled Default")

		link = frappe.get_doc({
			"doctype": "Huf User Role",
			"user": user.name,
			"huf_role": role.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(link.enabled, 1)

	def test_invalid_user_link_rejected(self):
		role = self._make_huf_role("_Test Huf User Role Bad User")

		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Huf User Role",
				"user": "_nonexistent@example.com",
				"huf_role": role.name,
			}).insert(ignore_permissions=True)

	def test_grants_mapped_frappe_role_on_insert(self):
		user = self._make_user()
		role = self._make_huf_role("_Test Huf User Role Grant", frappe_role="Huf User")

		frappe.get_doc({
			"doctype": "Huf User Role",
			"user": user.name,
			"huf_role": role.name,
		}).insert(ignore_permissions=True)

		# _sync_frappe_role() on after_insert should have appended "Huf User".
		user.reload()
		self.assertIn("Huf User", {r.role for r in user.roles})
