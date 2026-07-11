# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AgentExecutionApproval(Document):
	def has_permission(self, permission_type=None, verbose=False):
		from huf.permissions import has_capability
		user = frappe.session.user

		# System Manager always has full access (safety net).
		if "System Manager" in frappe.get_roles(user):
			return True

		# Strict capability checks for mutating actions. Approval records are
		# normally created by the dispatcher (Phase 3) under ignore_permissions;
		# manual create/write/delete requires the execution.approve capability.
		if permission_type == "create":
			return has_capability(user, "execution.approve")

		if permission_type in ("write", "save"):
			return has_capability(user, "execution.approve")

		if permission_type == "delete":
			return has_capability(user, "execution.approve")

		# Read / access is broadly allowed so designated approvers can see
		# pending approvals; the approve/reject endpoints do their own scoping.
		return True


def _can_decide(doc: Document, user: str) -> bool:
	"""Return True if *user* may record an approve/reject decision on *doc*.

	The acting user must satisfy at least one of:
	  (a) holds the ``execution.approve`` capability (this also covers
	      System Manager / Administrator, who receive every capability);
	  (b) the approval's ``approver_role`` is set and the user has that role;
	  (c) the approval's ``approver_users`` child table (``Agent User`` rows)
	      contains the user.
	"""
	from huf.permissions import has_capability

	# (a) capability-based approver (System Manager / Administrator included).
	if has_capability(user, "execution.approve"):
		return True

	# (b) designated approver role.
	if doc.approver_role and doc.approver_role in frappe.get_roles(user):
		return True

	# (c) designated approver users (Table MultiSelect -> rows with .user).
	approver_users = [row.user for row in (doc.approver_users or [])]
	if user in approver_users:
		return True

	return False


def _transition(docname: str, new_status: str, comment: str | None = None) -> Document:
	"""Move an approval from Pending to a terminal decided state.

	Enforces (1) that the acting user is allowed to decide this approval
	(capability / approver scoping) and (2) the state-machine invariant that a
	decision can be recorded exactly once, while the record is still Pending.
	"""
	doc = frappe.get_doc("Agent Execution Approval", docname)

	user = frappe.session.user
	if not _can_decide(doc, user):
		frappe.throw(
			_("You are not permitted to decide this execution approval."),
			frappe.PermissionError,
		)

	if doc.status != "Pending":
		frappe.throw(
			_("Only Pending approvals can be decided (current status: {0}).").format(doc.status),
			frappe.ValidationError,
		)

	doc.status = new_status
	doc.decided_by = frappe.session.user
	doc.decided_at = now_datetime()
	if comment:
		doc.comment = comment
	doc.save()
	return doc


@frappe.whitelist()
def approve_execution(agent_execution_approval_name: str, comment: str | None = None) -> dict:
	doc = _transition(agent_execution_approval_name, "Approved", comment)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def reject_execution(agent_execution_approval_name: str, comment: str | None = None) -> dict:
	doc = _transition(agent_execution_approval_name, "Rejected", comment)
	return {"name": doc.name, "status": doc.status}
