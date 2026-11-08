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
		# Decisions are made through huf.ai.external.approvals.decide_approval, which checks
		# authority. The agent has no capability that reaches it, so the connected user
		# approving from Huf is the intended flow.
		if self.status in _DECIDED_STATUSES and not self.decided_by:
			self.decided_by = frappe.session.user

	def _session_user(self) -> str | None:
		if not self.session:
			return None
		return frappe.db.get_value("External Agent Session", self.session, "user")
