# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestMeeting(IntegrationTestCase):
	def setUp(self):
		self._names = []

	def tearDown(self):
		for name in self._names:
			frappe.db.delete("Meeting", {"name": name})
		frappe.db.commit()

	def test_create_meeting(self):
		doc = frappe.get_doc({
			"doctype": "Meeting",
			"title": "__test_meeting__",
			"status": "Draft",
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		self.assertTrue(frappe.db.exists("Meeting", doc.name))

	def test_is_system_owned_defaults_to_one(self):
		doc = frappe.get_doc({
			"doctype": "Meeting",
			"title": "__test_meeting_default__",
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		self.assertEqual(doc.is_system_owned, 1)

	def test_system_owned_meeting_delete_guard(self):
		"""Deleting a system-owned meeting should be blocked outside install/migrate/uninstall."""
		meeting = frappe.new_doc("Meeting")
		meeting.title = "__test_meeting_guard__"
		meeting.is_system_owned = 1

		with self.assertRaises(frappe.ValidationError):
			meeting.on_trash()

	def test_non_manager_role_cannot_delete(self):
		doc = frappe.get_doc({
			"doctype": "Meeting",
			"title": "__test_meeting_perm__",
		})
		doc.insert(ignore_permissions=True)
		self._names.append(doc.name)

		self.assertFalse(
			frappe.has_permission("Meeting", ptype="delete", doc=doc.name, user="Guest")
		)
