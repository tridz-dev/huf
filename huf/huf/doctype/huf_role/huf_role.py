# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from huf.permissions import CAPABILITIES, _bust_cache


class HufRole(Document):
	# ------------------------------------------------------------------
	# Validation
	# ------------------------------------------------------------------

	def validate(self):
		self._validate_capabilities()

	def _validate_capabilities(self):
		"""Reject any capability not in the CAPABILITIES catalogue."""
		for row in self.permissions:
			if row.capability and row.capability not in CAPABILITIES:
				frappe.throw(
					_("Unknown capability '{0}'. Allowed values: {1}").format(
						row.capability, ", ".join(sorted(CAPABILITIES.keys()))
					)
				)

	# ------------------------------------------------------------------
	# Guard system roles
	# ------------------------------------------------------------------

	def on_trash(self):
		if self.is_system_role:
			frappe.throw(
				_("'{0}' is a system role and cannot be deleted.").format(self.role_name),
				frappe.PermissionError,
			)

	# ------------------------------------------------------------------
	# Cache invalidation
	# When a role's capability set changes every affected user's cache
	# must be busted so the next request picks up fresh capabilities.
	# ------------------------------------------------------------------

	def on_update(self):
		self._bust_users_cache()

	def _bust_users_cache(self):
		"""Bust the capability cache for every user assigned this role."""
		users = frappe.get_all(
			"Huf User Role",
			filters={"huf_role": self.name, "enabled": 1},
			fields=["user"],
			ignore_permissions=True,
		)
		for row in users:
			_bust_cache(row.user)
