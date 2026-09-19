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
		self._cleanup_huf_roles = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for user in self._cleanup_huf_user_roles:
			frappe.db.delete("Huf User Role", {"user": user})
		for user in self._cleanup_users:
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)
		for huf_role in self._cleanup_huf_roles:
			if frappe.db.exists("Huf Role", huf_role):
				frappe.delete_doc("Huf Role", huf_role, ignore_permissions=True, force=True)
		frappe.db.commit()

	# ------------------------------------------------------------------
	# Helpers
	# ------------------------------------------------------------------

	def _make_huf_user_role(self, user, huf_role, invited_by="Administrator"):
		"""Create (or update) the Huf User Role for `user`.

		`make_user()` creates the Frappe User with its Huf-mapped role
		already in `roles`, and HufUserRole.sync_from_frappe_user (hooked
		to User.on_update, which insert() also fires) auto-provisions a
		Huf User Role for that mapping before this helper ever runs. So a
		blind insert here collides with the row the production hook just
		created — this must be idempotent, matching how real callers
		(update_user_role/invite_user) reuse an existing record instead of
		assuming a fresh one.
		"""
		existing_name = frappe.db.get_value("Huf User Role", {"user": user}, "name")
		if existing_name:
			doc = frappe.get_doc("Huf User Role", existing_name)
			doc.huf_role = huf_role
			doc.enabled = 1
			doc.invited_by = invited_by
			doc.save(ignore_permissions=True)
		else:
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

	def _make_huf_role(self, capabilities, role_name=None, frappe_role="Huf User"):
		"""Create a custom Huf Role with an arbitrary capability set.

		Mirrors the pattern in
		huf/huf/doctype/agent_execution_approval/test_agent_execution_approval.py
		(`_make_huf_role`) — the built-in roles don't give us a caller who
		holds users.manage/users.invite while still lacking some of Huf
		Admin's capabilities (Huf Manager, in the real seed data, has
		neither users.manage nor users.invite at all: `_require()` would
		throw before the capability-mismatch/self-targeting checks under
		test ever run), so tests that need "has users.manage but not every
		capability" build a bespoke role instead of assuming one exists.
		"""
		role = frappe.get_doc(
			{
				"doctype": "Huf Role",
				"role_name": role_name or f"Test Capability Role {frappe.generate_hash(length=8)}",
				"frappe_role": frappe_role,
				"permissions": [{"capability": capability} for capability in capabilities],
			}
		)
		role.insert(ignore_permissions=True)
		self._cleanup_huf_roles.append(role.name)
		return role.name

	# Deliberately a proper subset of "Huf Admin"'s capabilities (omits
	# roles.manage, data.records.view_own/edit_own, and every system.*
	# capability) while still including users.manage/users.invite, so a
	# caller holding it can call update_user_role/invite_user at all but
	# still fails _require_all_capabilities("Huf Admin").
	_LIMITED_MANAGER_CAPABILITIES = [
		"users.manage",
		"users.invite",
		"agent.use",
		"agent.create",
		"agent.edit",
		"agent.delete",
		"agent.view_all",
		"chat.use",
		"chat.view_own",
		"chat.view_all",
		"knowledge.use",
		"knowledge.create",
		"knowledge.manage",
		"tools.use",
		"tools.create",
		"tools.manage",
		"flows.use",
		"flows.create",
		"flows.manage",
		"data.tables.manage",
		"data.records.create",
		"data.records.view_all",
		"data.records.edit_all",
		"execution_profile.manage",
		"network_access_policy.manage",
		"execution.approve",
		"code_execution.run",
		"ssh_connection.manage",
		"ssh.run",
		"ssh.approve",
		"docker.run",
		"developer.access",
		"developer.keys.manage",
	]

	def _make_capability_limited_manager(self, extra_frappe_roles=()):
		"""A Frappe user holding users.manage/users.invite plus most of
		Huf Manager's capabilities, but missing several that Huf Admin
		grants (e.g. roles.manage) — used to prove that holding
		users.manage does not imply holding every capability a target
		role grants.
		"""
		user_doc = make_user(roles=tuple(extra_frappe_roles))
		self._cleanup_users.append(user_doc.name)

		if "System Manager" in extra_frappe_roles:
			# get_user_capabilities() short-circuits System Manager to every
			# capability, and HufUserRole._sync_frappe_role() would strip the
			# "System Manager" Frappe role right back off as "stale" if we
			# pointed this user's Huf User Role at a Huf Role whose
			# frappe_role isn't "System Manager" (it treats any other
			# Huf-managed Frappe role as no-longer-current and removes it).
			# So the caller here is already maximally capable via the
			# System Manager shortcut and doesn't need the limited role.
			self._make_huf_user_role(user_doc.name, "Huf Admin")
			return user_doc.name

		limited_role = self._make_huf_role(self._LIMITED_MANAGER_CAPABILITIES)
		self._make_huf_user_role(user_doc.name, limited_role)
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
		# "System Manager" makes get_user_capabilities short-circuit to every
		# capability (huf/permissions.py: `_is_system_manager(user)` grants
		# the full CAPABILITIES set) — the simplest genuine "holds
		# everything" caller, matching how Huf Admin itself maps to the
		# System Manager Frappe role in the real seed data.
		admin_user = make_user(roles=("System Manager",))
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
		# See test_update_user_role_succeeds_with_sufficient_capabilities:
		# "System Manager" is the genuine "holds every capability" caller.
		admin_user = make_user(roles=("System Manager",))
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
