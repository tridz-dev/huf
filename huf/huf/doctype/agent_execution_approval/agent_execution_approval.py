# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class AgentExecutionApproval(Document):
	pass


def _transition(docname: str, new_status: str, comment: str | None = None) -> Document:
	"""Move an approval from Pending to a terminal decided state.

	Permission / capability gating is intentionally deferred to Phase 2; this
	only enforces the state-machine invariant that a decision can be recorded
	exactly once, while the record is still Pending.
	"""
	doc = frappe.get_doc("Agent Execution Approval", docname)
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
