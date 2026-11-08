# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

_DECIDED_STATUSES = ("Approved", "Rejected")


class ExternalActionApproval(Document):
	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		# System Manager always has full access.
		if "System Manager" in frappe.get_roles(user):
			return True

		# Read is allowed to the user who owns the linked external session.
		# Decisions go through server API code that checks approver authority,
		# so every write path is closed to everyone else here.
		if permission_type == "read":
			return self._session_user() == user

		return False

	def validate(self):
		if self.status not in _DECIDED_STATUSES or not self.decided_by:
			return

		if self.decided_by != frappe.session.user:
			return

		if "System Manager" in frappe.get_roles(self.decided_by):
			return

		frappe.throw(_("You cannot decide your own request."), frappe.PermissionError)

	def _session_user(self) -> str | None:
		if not self.session:
			return None
		return frappe.db.get_value("External Agent Session", self.session, "user")
