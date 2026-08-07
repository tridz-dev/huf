# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


def get_permission_query_conditions(user=None):
	"""List-query filter: users only see approvals they are designated to act on."""
	if not user:
		user = frappe.session.user

	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""

	escaped_user = frappe.db.escape(user)
	return f"""
		(
			`tabPending Approval`.`approver_user` = {escaped_user}
			OR FIND_IN_SET({escaped_user}, `tabPending Approval`.`approver_users`) > 0
			OR `tabPending Approval`.`approver_role` IN (
				SELECT `role` FROM `tabHas Role`
				WHERE `parenttype` = 'User' AND `parent` = {escaped_user}
			)
		)
	"""


class PendingApproval(Document):
	"""
	Generic pending approval record.

	Used by the Approval Inbox to surface items a user is allowed to act on,
	regardless of the source feature (Flow, Agent, MCP, etc.). The DocType
	permissions allow broad read access so approvers can see their items;
	actual scoping is enforced by the API methods and by this controller.
	"""

	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		# System-level users have full access.
		if user == "Administrator" or "System Manager" in frappe.get_roles(user):
			return True

		# Read-level access is allowed only for items the user can approve.
		if permission_type in ("read", "print", "email", "report", "access"):
			return self._user_can_see(user)

		# Create / write / delete are restricted to system processes that use
		# ignore_permissions (e.g. the flow engine creating a record).
		return False

	def _user_can_see(self, user: str) -> bool:
		"""Return True if *user* is a designated approver for this record."""
		approval_type = self.approval_type or "role"

		if approval_type == "role":
			role = self.approver_role
			if role and role in frappe.get_roles(user):
				return True
		elif approval_type == "user":
			if self.approver_user and self.approver_user == user:
				return True
		elif approval_type == "users":
			users = self.approver_users or ""
			if isinstance(users, str):
				users = [u.strip() for u in users.split(",") if u.strip()]
			if user in users:
				return True

		return False

	def before_insert(self):
		# Ensure actioned_* fields are blank on creation.
		if self.status == "Pending":
			self.actioned_by = None
			self.actioned_at = None

	def validate(self):
		# Basic coherence checks.
		if self.status in ("Approved", "Rejected") and not self.actioned_by:
			frappe.throw(_("Actioned By is required for Approved/Rejected approvals"))

		if self.actioned_at and isinstance(self.actioned_at, str):
			self.actioned_at = get_datetime(self.actioned_at)

	@frappe.whitelist()
	def approve(self, comment: str | None = None):
		"""Mark this approval as approved. Caller must already be authorized."""
		self._record_decision("Approved", comment)

	@frappe.whitelist()
	def reject(self, comment: str | None = None):
		"""Mark this approval as rejected. Caller must already be authorized."""
		self._record_decision("Rejected", comment)

	def _record_decision(self, status: str, comment: str | None):
		if self.status != "Pending":
			frappe.throw(_("Approval is not pending (status: {0})").format(self.status))

		self.status = status
		self.actioned_by = frappe.session.user
		self.actioned_at = now_datetime()
		if comment is not None:
			self.comment = comment

		self.save(ignore_permissions=True)
