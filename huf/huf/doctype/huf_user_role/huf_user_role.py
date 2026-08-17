# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from huf.permissions import HUF_ROLE_FRAPPE_ROLE_MAP, _bust_cache


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
		target_frappe_role = frappe.db.get_value("Huf Role", self.huf_role, "frappe_role")
		if not target_frappe_role:
			return

		user_doc = frappe.get_doc("User", self.user)
		current_roles = {r.role for r in user_doc.roles}

		# Remove any *other* Huf-managed Frappe roles the user currently holds.
		all_huf_frappe_roles = set(HUF_ROLE_FRAPPE_ROLE_MAP.values())
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
			# Disabled Huf User Role → remove the Frappe role too.
			if target_frappe_role not in {"System Manager"}:  # never strip System Manager
				user_doc.remove_roles(target_frappe_role)

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
