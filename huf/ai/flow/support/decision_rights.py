"""Whether the signed-in user may approve or reject a run that waits for approval (the same check the decision itself runs)."""

from __future__ import annotations

import frappe


def approval_decision_rights(status: str | None, waiting: dict, flow: str | None) -> tuple[bool, str | None]:
	"""(may the user approve or reject this run, why not). Fail closed, so the Approve / Reject buttons are only offered
	to people the server will let through: the app approve grant (and the app's narrowing) that guards the decision,
	then the step's approvers."""
	if status != "Waiting Approval":
		return False, None
	from huf.ai.flow import engine
	from huf.ai.flow.app_scope.access import flow_access, is_privileged
	from huf.ai.flow.app_scope.api_guards import is_app_flow, is_app_only

	user = frappe.session.user
	# The same refusals as ``guard_run(run, "approve")``, without raising.
	if not is_privileged(user):
		if not flow_access(user, flow, "approve") if is_app_flow(flow) else is_app_only(user):
			return False, "You are not allowed to approve runs of this flow"
	reason = engine.check_approver(waiting, user, set(frappe.get_roles(user)))
	return reason is None, reason
