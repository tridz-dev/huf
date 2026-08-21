# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_pending_agent_execution_approvals(limit: int = 50) -> list[dict]:
	"""List pending code/SSH execution approvals the current user may decide.

	Mirrors ``huf.ai.flow_api.get_pending_approvals``: a whitelisted list
	endpoint for a frontend approval inbox, scoped to what the *current
	session user* is allowed to act on rather than every pending row.

	Scoping reuses ``AgentExecutionApproval._can_decide`` (capability holder
	for the approval's execution kind, the assigned ``approver_role``, an
	entry in ``approver_users``, or System Manager) instead of duplicating
	that logic — each candidate row is loaded as a full ``Document`` via
	``frappe.get_doc`` and passed straight into it, since ``_can_decide``
	reads ``doc.approver_role``/``doc.approver_users`` off the document.

	Ordered oldest-``expires_on``-first: every row here is racing a 24h TTL
	before it lapses to Expired, so the ones closest to expiring are the
	most urgent for an approver to see first (as opposed to ``creation``
	order, which says nothing about remaining time).

	Only ``code_ref`` (the SHA-256 hash) is ever exposed — never the raw
	code — matching the doctype's own design; this is a notification/list
	view, not a code-preview endpoint.

	Args:
	    limit: Maximum number of results (default 50).

	Returns:
	    list of pending approvals the current user can approve or reject.
	"""
	from huf.huf.doctype.agent_execution_approval.agent_execution_approval import _can_decide

	if not frappe.has_permission("Agent Execution Approval", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	user = frappe.session.user

	pending_names = frappe.get_all(
		"Agent Execution Approval",
		filters={"status": "Pending"},
		pluck="name",
		order_by="expires_on asc",
		limit_page_length=limit * 4 if limit else 0,
	)

	results = []

	for name in pending_names:
		doc = frappe.get_doc("Agent Execution Approval", name)

		if not _can_decide(doc, user):
			continue

		requested_by = None
		agent_name = None
		if doc.agent_tool_call:
			call_info = frappe.db.get_value(
				"Agent Tool Call", doc.agent_tool_call, ["owner", "agent_run"], as_dict=True
			)
			if call_info:
				requested_by = call_info.owner
				if call_info.agent_run:
					agent_name = frappe.db.get_value("Agent Run", call_info.agent_run, "agent")

		results.append(
			{
				"name": doc.name,
				"agent_tool_call": doc.agent_tool_call,
				"execution_kind": doc.execution_kind,
				"requested_capability": doc.requested_capability,
				"code_ref": doc.code_ref,
				"expires_on": doc.expires_on,
				"approver_role": doc.approver_role,
				"requested_by": requested_by,
				"agent_name": agent_name,
				"can_decide": True,
			}
		)

		if limit and len(results) >= limit:
			break

	return results
