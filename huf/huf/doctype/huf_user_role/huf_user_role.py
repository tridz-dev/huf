# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from huf.permissions import (
	DEFAULT_SYSTEM_USER_HUF_ROLE,
	GATEWAY_FRAPPE_ROLE,
	HUF_ROLE_FRAPPE_ROLE_MAP,
	_bust_cache,
)


class HufUserRole(Document):
	"""
	Bridges a Frappe User to a Huf Role.

	On every save/delete the corresponding Frappe 'Has Role' record is
	kept in sync automatically so Frappe's own permission system (DocType
	read/write matrix) stays consistent with the Huf role assignment.
	"""

	# ------------------------------------------------------------------
	# Lifecycle hooks
	# ------------------------------------------------------------------

	def before_insert(self):
		if not self.invited_on:
			self.invited_on = now_datetime()
		if not self.invited_by:
			self.invited_by = frappe.session.user

	def after_insert(self):
		self._sync_frappe_role()

	def on_update(self):
		self._sync_frappe_role()
		_bust_cache(self.user)

	def on_trash(self):
		self._remove_all_huf_frappe_roles()
		_bust_cache(self.user)

	# ------------------------------------------------------------------
	# Frappe role synchronisation
	# ------------------------------------------------------------------

	def _sync_frappe_role(self):
		"""
		Ensure the user has exactly the Frappe role that backs their
		current Huf role, and remove any stale Huf Frappe roles they
		may have had before.
		"""
		if self.flags.skip_frappe_role_sync:
			return  # the caller already wrote the Has Role rows
		target_frappe_role = frappe.db.get_value("Huf Role", self.huf_role, "frappe_role")
		if not target_frappe_role:
			return

		user_doc = frappe.get_doc("User", self.user)
		current_roles = {r.role for r in user_doc.roles}

		# Remove any *other* Huf-managed Frappe roles the user currently holds. The gateway role is
		# held alongside the user's Huf role (it lets them be a channel's Run as user), so it stays.
		all_huf_frappe_roles = set(HUF_ROLE_FRAPPE_ROLE_MAP.values()) - {GATEWAY_FRAPPE_ROLE}
		stale = all_huf_frappe_roles & current_roles - {target_frappe_role}
		for role in stale:
			user_doc.remove_roles(role)

		# Grant the target Frappe role if not already present.
		if self.enabled and target_frappe_role not in current_roles:
			user_doc.append("roles", {"role": target_frappe_role})
			# Synchronizing Frappe role membership on behalf of the system; the controller validates the operation.
			frappe.flags.syncing_huf_roles = True
			try:
				user_doc.save(ignore_permissions=True)
			finally:
				frappe.flags.syncing_huf_roles = False
		elif not self.enabled:
			# Disabled Huf User Role → remove the Frappe role too, and the gateway role, which would
			# otherwise keep giving the user agent access.
			removable = {target_frappe_role, GATEWAY_FRAPPE_ROLE} - {"System Manager"}  # never strip System Manager
			if removable & current_roles:
				user_doc.remove_roles(*(removable & current_roles))

	def _remove_all_huf_frappe_roles(self):
		"""Remove every Huf-managed Frappe role from the user on deletion."""
		user_doc = frappe.get_doc("User", self.user)
		current_roles = {r.role for r in user_doc.roles}
		all_huf_frappe_roles = set(HUF_ROLE_FRAPPE_ROLE_MAP.values()) - {"System Manager"}

		for role in all_huf_frappe_roles & current_roles:
			user_doc.remove_roles(role)


def sync_from_frappe_user(doc, method=None):
	"""
	Hooked to User on_update.
	If an admin manually modifies Frappe roles on a User form, we sync
	it back to Huf User Role so they don't diverge.
	"""
	if getattr(frappe.flags, "syncing_huf_roles", False):
		return

	user_roles = {r.role for r in doc.roles}
	
	highest_huf_role = None
	if user_roles:
		huf_roles = frappe.get_all(
			"Huf Role", 
			filters={"frappe_role": ("in", list(user_roles))},
			fields=["name", "role_name", "role_weight"],
			order_by="role_weight desc"
		)
		
		if huf_roles:
			highest_huf_role = huf_roles[0].role_name

	if not highest_huf_role:
		huf_role_name = frappe.db.get_value("Huf User Role", {"user": doc.name}, "name")
		if huf_role_name:
			huf_user_role = frappe.get_doc("Huf User Role", huf_role_name)
			if huf_user_role.enabled:
				frappe.flags.syncing_huf_roles = True
				try:
					huf_user_role.db_set("enabled", 0)
					_bust_cache(doc.name)
				finally:
					frappe.flags.syncing_huf_roles = False
		return

	huf_role_name = frappe.db.get_value("Huf User Role", {"user": doc.name}, "name")
	if huf_role_name:
		huf_user_role = frappe.get_doc("Huf User Role", huf_role_name)
		if huf_user_role.huf_role != highest_huf_role or not huf_user_role.enabled:
			frappe.flags.syncing_huf_roles = True
			try:
				huf_user_role.db_set("huf_role", highest_huf_role)
				huf_user_role.db_set("enabled", 1)
				_bust_cache(doc.name)
			finally:
				frappe.flags.syncing_huf_roles = False
	else:
		frappe.flags.syncing_huf_roles = True
		try:
			new_huf_user_role = frappe.get_doc({
				"doctype": "Huf User Role",
				"user": doc.name,
				"huf_role": highest_huf_role,
				"enabled": 1,
				"invited_by": frappe.session.user if frappe.session and frappe.session.user else "Administrator",
				"invited_on": now_datetime(),
			})
			new_huf_user_role.insert(ignore_permissions=True)
			_bust_cache(doc.name)
		finally:
			frappe.flags.syncing_huf_roles = False


def grant_default_huf_roles(doc, method=None):
	"""Hooked to User on_update: give a System User Huf's default roles (see ensure_default_huf_roles)."""
	if getattr(frappe.flags, "syncing_huf_roles", False) or getattr(frappe.flags, "huf_skip_default_roles", False):
		return
	ensure_default_huf_roles(doc.name, doc.user_type, doc.enabled, user_doc=doc)


def ensure_default_huf_roles(
	user: str, user_type: str | None = None, enabled: int | None = None, user_doc=None
) -> bool:
	"""Give a Frappe System User the default Huf roles. Returns True when anything was granted.

	- No Huf role yet: they become ``Huf Manager`` (DEFAULT_SYSTEM_USER_HUF_ROLE).
	- Everyone gets the ``Huf Gateway User`` role on top, so they can be a channel's Run as user.

	Never downgrades or replaces a Huf role an admin assigned, never touches a user whose Huf access
	was switched off (disabled Huf User Role), and never grants Huf Admin / System Manager (Administrator
	already is Huf Admin, so it only gains the gateway role). The Has Role
	rows are written directly so this can run from the User's own on_update without re-saving it; with
	``user_doc`` they are also added to that doc, so a later save of the same form keeps them.
	"""
	if user == "Guest":
		return False
	# Test fixtures build users with exact roles (often deliberately without Huf access); tests that cover
	# the default grant opt in.
	if getattr(frappe.flags, "in_test", False) and not getattr(frappe.flags, "huf_default_roles_in_test", False):
		return False
	if user_type is None or enabled is None:
		row = frappe.db.get_value("User", user, ["user_type", "enabled"], as_dict=True)
		if not row:
			return False
		user_type, enabled = row.user_type, row.enabled
	if user_type != "System User" or not enabled:
		return False
	existing = frappe.db.get_value("Huf User Role", {"user": user}, ["name", "enabled"], as_dict=True)
	if existing and not existing.enabled:
		return False

	roles = set(frappe.get_all("Has Role", {"parent": user, "parenttype": "User"}, pluck="role"))
	granted = []
	if not existing and not roles & set(HUF_ROLE_FRAPPE_ROLE_MAP.values()):
		record = frappe.get_doc(
			{
				"doctype": "Huf User Role",
				"user": user,
				"huf_role": DEFAULT_SYSTEM_USER_HUF_ROLE,
				"enabled": 1,
				"invited_by": "Administrator",
			}
		)
		record.flags.skip_frappe_role_sync = True
		record.insert(ignore_permissions=True)
		granted.append(HUF_ROLE_FRAPPE_ROLE_MAP[DEFAULT_SYSTEM_USER_HUF_ROLE])
	if GATEWAY_FRAPPE_ROLE not in roles:
		granted.append(GATEWAY_FRAPPE_ROLE)
	granted = [role for role in granted if role not in roles]
	if not granted:
		return False

	idx = max(frappe.get_all("Has Role", {"parent": user, "parenttype": "User"}, pluck="idx") or [0])
	for role in granted:
		idx += 1
		values = {"role": role, "idx": idx}
		if user_doc is not None:
			user_doc.append("roles", values).db_insert()
		else:
			frappe.get_doc(
				{"doctype": "Has Role", "parent": user, "parenttype": "User", "parentfield": "roles", **values}
			).db_insert()
	frappe.clear_cache(user=user)
	_bust_cache(user)
	return True


def grant_default_roles_to_system_users() -> int:
	"""Backfill: run ensure_default_huf_roles for every enabled System User. Returns how many changed."""
	users = frappe.get_all("User", {"user_type": "System User", "enabled": 1}, pluck="name")
	return sum(1 for user in users if ensure_default_huf_roles(user, "System User", 1))
