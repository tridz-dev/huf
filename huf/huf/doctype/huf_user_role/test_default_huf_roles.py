# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Every Frappe System User gets Huf Manager + Huf Gateway User by default, without ever escalating."""

import unittest

import frappe

from huf.huf.doctype.huf_user_role.huf_user_role import (
	ensure_default_huf_roles,
	grant_default_roles_to_system_users,
)
from huf.permissions import get_user_huf_role, has_capability

DESK_ROLE = "Huf Test Desk Role"


class TestDefaultHufRoles(unittest.TestCase):
	def setUp(self):
		if not frappe.db.exists("Role", DESK_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": DESK_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		frappe.flags.huf_default_roles_in_test = True
		self.addCleanup(setattr, frappe.flags, "huf_default_roles_in_test", False)
		self.users: list[str] = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in self.users:
			frappe.db.delete("Huf User Role", {"user": user})
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)

	def _user(self, *roles, user_type=None):
		email = f"huf-default-{frappe.generate_hash(length=8)}@example.com"
		doc = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Default", "send_welcome_email": 0})
		for role in roles:
			doc.append("roles", {"role": role})
		if user_type:
			doc.user_type = user_type
		doc.insert(ignore_permissions=True)
		self.users.append(email)
		return doc

	def _roles(self, user):
		return set(frappe.get_all("Has Role", {"parent": user, "parenttype": "User"}, pluck="role"))

	def test_new_system_user_gets_manager_and_gateway_roles(self):
		user = self._user(DESK_ROLE)
		self.assertEqual(user.user_type, "System User")
		self.assertTrue({"Huf Manager", "Huf Gateway User"} <= self._roles(user.name))
		self.assertEqual(get_user_huf_role(user.name), "Huf Manager")
		self.assertTrue(has_capability(user.name, "agent.create"))
		self.assertNotIn("System Manager", self._roles(user.name))
		# the in-memory doc carries them too, so saving the same form again keeps them
		self.assertTrue({"Huf Manager", "Huf Gateway User"} <= {r.role for r in user.roles})
		user.save(ignore_permissions=True)
		self.assertTrue({"Huf Manager", "Huf Gateway User"} <= self._roles(user.name))
		self.assertTrue(frappe.db.get_value("Huf User Role", {"user": user.name}, "enabled"))

	def test_website_user_gets_nothing(self):
		user = self._user()
		self.assertEqual(user.user_type, "Website User")
		self.assertFalse(self._roles(user.name) & {"Huf Manager", "Huf Gateway User"})
		self.assertFalse(frappe.db.exists("Huf User Role", {"user": user.name}))

	def test_assigned_huf_role_is_kept_and_only_the_gateway_role_added(self):
		frappe.flags.huf_skip_default_roles = True
		try:
			user = self._user(DESK_ROLE, "Huf Viewer")
		finally:
			frappe.flags.huf_skip_default_roles = False
		self.assertTrue(ensure_default_huf_roles(user.name))
		self.assertEqual(get_user_huf_role(user.name), "Huf Viewer")
		roles = self._roles(user.name)
		self.assertIn("Huf Gateway User", roles)
		self.assertNotIn("Huf Manager", roles)

	def test_switched_off_access_is_not_restored(self):
		user = self._user(DESK_ROLE)
		record = frappe.get_doc("Huf User Role", {"user": user.name})
		record.enabled = 0
		record.save(ignore_permissions=True)
		self.assertFalse(self._roles(user.name) & {"Huf Manager", "Huf Gateway User"})

		frappe.get_doc("User", user.name).save(ignore_permissions=True)
		self.assertFalse(ensure_default_huf_roles(user.name))
		self.assertFalse(self._roles(user.name) & {"Huf Manager", "Huf Gateway User"})
		self.assertFalse(frappe.db.get_value("Huf User Role", {"user": user.name}, "enabled"))

	def test_changing_the_huf_role_keeps_the_gateway_role(self):
		user = self._user(DESK_ROLE)
		record = frappe.get_doc("Huf User Role", {"user": user.name})
		record.huf_role = "Huf User"
		record.save(ignore_permissions=True)
		roles = self._roles(user.name)
		self.assertIn("Huf User", roles)
		self.assertIn("Huf Gateway User", roles)
		self.assertNotIn("Huf Manager", roles)

	def test_backfill_covers_existing_system_users_once(self):
		frappe.flags.huf_skip_default_roles = True
		try:
			user = self._user(DESK_ROLE)
		finally:
			frappe.flags.huf_skip_default_roles = False
		self.assertFalse(self._roles(user.name) & {"Huf Manager", "Huf Gateway User"})
		grant_default_roles_to_system_users()
		self.assertTrue({"Huf Manager", "Huf Gateway User"} <= self._roles(user.name))
		self.assertFalse(ensure_default_huf_roles(user.name))  # nothing left to grant

	def test_administrator_gets_the_gateway_role_only(self):
		had = "Huf Gateway User" in self._roles("Administrator")
		ensure_default_huf_roles("Administrator")
		roles = self._roles("Administrator")
		self.assertIn("Huf Gateway User", roles)
		self.assertNotIn("Huf Manager", roles)
		self.assertEqual(get_user_huf_role("Administrator"), "Huf Admin")
		if not had:
			frappe.db.delete("Has Role", {"parent": "Administrator", "role": "Huf Gateway User"})
