# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
huf/ai/tests/test_permissions_api.py

Regression coverage for ST-R2.6: update_user_role and invite_user must both
refuse capability mismatch (a caller cannot grant a role whose capabilities
they do not themselves hold) and self-targeting (a non-admin caller cannot
change/grant their own role), with a bootstrap escape hatch for
Administrator / System Manager callers so a single-admin site is never
locked out.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.permissions_api import invite_user, update_user_role
from huf.ai.tests.factories import make_user


class TestPermissionsAPISelfTargetingAndCapabilities(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup_users = []
		self._cleanup_huf_user_roles = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in self._cleanup_huf_user_roles:
			frappe.db.delete("Huf User Role", {"user": user})
		for user in self._cleanup_users:
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		frappe.db.commit()

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

	def _make_huf_user_role(self, user, huf_role, invited_by="Administrator"):
		doc = frappe.get_doc(
			{
				"doctype": "Huf User Role",
				"user": user,
				"huf_role": huf_role,
				"enabled": 1,
				"invited_by": invited_by,
			}
		)
		doc.insert(ignore_permissions=True)
		self._cleanup_huf_user_roles.append(user)
		return doc

	def _make_capability_limited_manager(self, extra_frappe_roles=()):
		"""A Frappe user with a Huf Manager role (which is missing several
		capabilities that Huf Admin grants, e.g. roles.manage, users.manage
		itself is present on Huf Manager but capabilities like
		execution_profile.manage differ) — used to prove that having
		users.manage does not imply holding every capability a target role
		grants.
		"""
		user_doc = make_user(roles=("Huf Manager", *extra_frappe_roles))
		self._cleanup_users.append(user_doc.name)
		self._make_huf_user_role(user_doc.name, "Huf Manager")
		return user_doc.name

	# ------------------------------------------------------------------
	# update_user_role
	# ------------------------------------------------------------------

	def test_update_user_role_refuses_capability_mismatch(self):
		"""Caller must hold all capabilities in the target role."""
		caller = self._make_capability_limited_manager()
		target_user = self._make_capability_limited_manager()

		frappe.set_user(caller)
		try:
			with self.assertRaises(frappe.PermissionError) as ctx:
				update_user_role(target_user, "Huf Admin")
			self.assertIn("You lack capabilities to assign this role", str(ctx.exception))
		finally:
			frappe.set_user("Administrator")

	def test_update_user_role_refuses_self_targeting_for_non_admin(self):
		"""A non-admin user cannot change their own role."""
		caller = self._make_capability_limited_manager()

		frappe.set_user(caller)
		try:
			with self.assertRaises(frappe.PermissionError) as ctx:
				update_user_role(caller, "Huf Manager")
			self.assertIn("You cannot change your own role", str(ctx.exception))
		finally:
			frappe.set_user("Administrator")

	def test_update_user_role_allows_self_targeting_for_system_manager(self):
		"""Bootstrap escape hatch: System Manager can correct their own Huf role."""
		caller = self._make_capability_limited_manager(extra_frappe_roles=("System Manager",))

		frappe.set_user(caller)
		try:
			result = update_user_role(caller, "Huf Manager")
			self.assertEqual(result["huf_role"], "Huf Manager")
		finally:
			frappe.set_user("Administrator")

	def test_update_user_role_succeeds_with_sufficient_capabilities(self):
		"""User with users.manage and all target capabilities can assign roles to others."""
		admin_user = make_user(roles=("Huf Manager",))
		self._cleanup_users.append(admin_user.name)
		self._make_huf_user_role(admin_user.name, "Huf Admin")

		target_user = self._make_capability_limited_manager()

		frappe.set_user(admin_user.name)
		try:
			result = update_user_role(target_user, "Huf Manager")
			self.assertEqual(result["huf_role"], "Huf Manager")
		finally:
			frappe.set_user("Administrator")

	# ------------------------------------------------------------------
	# invite_user
	# ------------------------------------------------------------------

	def test_invite_user_refuses_capability_mismatch(self):
		"""invite_user must not be usable to escalate via a role the inviter cannot hold."""
		caller = self._make_capability_limited_manager()
		new_email = f"huf-invite-test-{frappe.generate_hash(length=8)}@example.com"

		frappe.set_user(caller)
		try:
			with self.assertRaises(frappe.PermissionError) as ctx:
				invite_user(new_email, "New User", "Huf Admin")
			self.assertIn("You lack capabilities to assign this role", str(ctx.exception))
		finally:
			frappe.set_user("Administrator")

		self.assertFalse(frappe.db.exists("User", new_email))

	def test_invite_user_refuses_self_targeting_for_non_admin(self):
		"""A non-admin caller cannot invite/re-grant a role to their own email."""
		caller = self._make_capability_limited_manager()

		frappe.set_user(caller)
		try:
			with self.assertRaises(frappe.PermissionError) as ctx:
				invite_user(caller, "Self Invite", "Huf Manager")
			self.assertIn("You cannot change your own role", str(ctx.exception))
		finally:
			frappe.set_user("Administrator")

	def test_invite_user_succeeds_with_sufficient_capabilities(self):
		"""User with users.invite and all target capabilities can invite others."""
		admin_user = make_user(roles=("Huf Manager",))
		self._cleanup_users.append(admin_user.name)
		self._make_huf_user_role(admin_user.name, "Huf Admin")

		new_email = f"huf-invite-test-{frappe.generate_hash(length=8)}@example.com"
		self._cleanup_users.append(new_email)

		frappe.set_user(admin_user.name)
		try:
			result = invite_user(new_email, "New User", "Huf Manager")
			self.assertEqual(result["huf_role"], "Huf Manager")
		finally:
			frappe.set_user("Administrator")

		self.assertTrue(frappe.db.exists("User", new_email))
		self._cleanup_huf_user_roles.append(new_email)
