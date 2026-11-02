"""Whether the signed-in user may approve or reject a run that waits for approval (the same check the decision itself runs)."""

from __future__ import annotations

import frappe


def approval_decision_rights(status: str | None, waiting: dict) -> tuple[bool, str | None]:
	"""(may the user approve or reject this run, why not). Fail closed, so the Approve / Reject buttons are only offered
	to people the server will let through."""
	if status != "Waiting Approval":
		return False, None
	from huf.ai.flow import engine

	user = frappe.session.user
	reason = engine.check_approver(waiting, user, set(frappe.get_roles(user)))
	return reason is None, reason
