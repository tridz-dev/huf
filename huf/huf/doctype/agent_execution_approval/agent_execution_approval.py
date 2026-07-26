# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime


class AgentExecutionApproval(Document):
	def has_permission(self, permission_type=None, verbose=False):
		user = frappe.session.user

		# System Manager always has full access (safety net).
		if "System Manager" in frappe.get_roles(user):
			return True

		# Strict capability checks for mutating actions. Approval records are
		# normally created by the dispatcher under ignore_permissions; manual
		# create/write/delete requires the execution-kind-specific approval capability.
		if permission_type == "create":
			return _has_approval_capability(self, user)

		if permission_type in ("write", "save"):
			return _has_approval_capability(self, user)

		if permission_type == "delete":
			return _has_approval_capability(self, user)

		# Read / access is broadly allowed so designated approvers can see
		# pending approvals; the approve/reject endpoints do their own scoping.
		return True


def _approval_capability(doc: Document | None) -> str:
	kind = (getattr(doc, "execution_kind", None) or "code_execution").strip().lower()
	if kind == "ssh_exec":
		return "ssh.approve"
	return "execution.approve"


def _has_approval_capability(doc: Document | None, user: str) -> bool:
	from huf.permissions import has_capability

	return has_capability(user, _approval_capability(doc))


def _execution_module(execution_kind: str | None):
	"""Resolve the backing execution module for an approval kind."""
	kind = (execution_kind or "code_execution").strip().lower()
	if kind == "code_execution":
		from huf.ai.tools import code_execution as module

		return module
	if kind == "ssh_exec":
		from huf.ai.tools import ssh_execution as module

		return module
	frappe.throw(
		_("Unsupported execution kind: {0}").format(execution_kind or "(blank)"),
		frappe.ValidationError,
	)


def _can_decide(doc: Document, user: str) -> bool:
	"""Return True if *user* may record an approve/reject decision on *doc*.

	The acting user must satisfy at least one of:
	  (a) holds the execution-kind-specific approval capability (this also covers
	      System Manager / Administrator, who receive every capability);
	  (b) the approval's ``approver_role`` is set and the user has that role;
	  (c) the approval's ``approver_users`` child table (``Agent User`` rows)
	      contains the user.
	"""
	# (a) capability-based approver (System Manager / Administrator included).
	if _has_approval_capability(doc, user):
		return True

	# (b) designated approver role.
	if doc.approver_role and doc.approver_role in frappe.get_roles(user):
		return True

	# (c) designated approver users (Table MultiSelect -> rows with .user).
	approver_users = [row.user for row in (doc.approver_users or [])]
	if user in approver_users:
		return True

	return False


def _finalize_tool_call(doc: Document, error_message: str) -> None:
	"""Close the linked ``Agent Tool Call`` as a terminal failure.

	Used when a parked execution is rejected or lapses: no RQ job is ever
	enqueued for it, so the audit row must not sit parked at "Queued" forever.
	The ``exit_status`` Select has no dedicated Rejected value (its options are
	Ok/Timeout/OOM/Error/Killed), so "Error" — the closest existing terminal
	value — marks the call. ``ignore_permissions`` mirrors the dispatcher,
	which writes audit rows on behalf of users who hold no write perm on
	``Agent Tool Call``.
	"""
	if not doc.agent_tool_call:
		return
	call = frappe.get_doc("Agent Tool Call", doc.agent_tool_call)
	call.status = "Failed"
	call.exit_status = "Error"
	call.error_message = error_message
	call.save(ignore_permissions=True)


def _mark_expired(doc: Document) -> None:
	"""Lapse an undecided approval: Expired + finalize the parked tool call.

	Terminal rejected-equivalent (no enqueue). ``decided_by``/``decided_at``
	stay empty — this is a system transition, not a user decision, so it uses
	``ignore_permissions`` (a designated approver without DocType write perm
	must still be able to lapse an expired record; the decide-path save stays
	permission-checked). The explicit commit is deliberate: the caller reports
	the lapse by throwing, and Frappe rolls the request's writes back on an
	exception, so without a commit here the Expired transition itself would be
	undone.
	"""
	doc.status = "Expired"
	doc.save(ignore_permissions=True)
	_finalize_tool_call(doc, _("Execution approval expired before a decision was recorded."))

	_execution_module(doc.execution_kind).clear_pending_execution(doc.name)
	frappe.db.commit()


def _transition(
	docname: str, new_status: str, comment: str | None = None, before_decide=None
) -> Document:
	"""Move an approval from Pending to a terminal decided state.

	Enforces (1) that the acting user is allowed to decide this approval
	(capability / approver scoping), (2) the state-machine invariant that a
	decision can be recorded exactly once, while the record is still Pending,
	and (3) lazy TTL expiry: an undecided approval past ``expires_on`` lapses
	to Expired instead of being decided (no scheduler job sweeps approvals, so
	the TTL is enforced on the next access).

	``before_decide`` (optional callable receiving the doc) runs after all
	guards and before the status flip; raising from it aborts the decision
	(fail closed). ``approve_execution`` uses it to prove the parked execution
	payload is still resolvable before ``Approved`` is recorded.
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

	# Lazy TTL expiry — an undecided approval past ``expires_on`` lapses to
	# Expired (terminal) and the decide attempt is rejected.
	if doc.expires_on and get_datetime(doc.expires_on) < now_datetime():
		_mark_expired(doc)
		frappe.throw(
			_("This execution approval has expired and can no longer be decided."),
			frappe.ValidationError,
		)

	if before_decide:
		before_decide(doc)

	doc.status = new_status
	doc.decided_by = frappe.session.user
	doc.decided_at = now_datetime()
	if comment:
		doc.comment = comment
	doc.save()
	return doc


def _load_dispatch_payload(doc: Document) -> dict:
	"""``before_decide`` hook for approvals: resolve the parked execution payload.

	The approval may flip to ``Approved`` only while the Redis hold for the
	parked execution is still present and internally consistent. A lapsed hold
	marks the approval Expired (same treatment as TTL expiry) and aborts the
	decision; an integrity/acting-user problem aborts with the approval left
	Pending (see ``load_pending_execution``).
	"""
	module = _execution_module(doc.execution_kind)

	try:
		return module.load_pending_execution(doc)
	except module.PendingExecutionExpired:
		_mark_expired(doc)
		frappe.throw(
			_("The parked execution is no longer available; the approval was marked Expired."),
			frappe.ValidationError,
		)


@frappe.whitelist()
def approve_execution(agent_execution_approval_name: str, comment: str | None = None) -> dict:
	"""Approve a parked code execution and dispatch its RQ job.

	The payload check runs as a pre-decision guard (a lapsed/invalid hold
	aborts before ``Approved`` is recorded), and the job is enqueued only
	AFTER the approval is saved (the worker refuses to run a call whose
	approval is not yet Approved). The job impersonates the ORIGINAL
	requesting user captured at dispatch time — never the approver.
	"""
	payload: dict = {}

	def _preflight(doc):
		payload.update(_load_dispatch_payload(doc))

	doc = _transition(
		agent_execution_approval_name, "Approved", comment, before_decide=_preflight
	)

	_execution_module(doc.execution_kind).enqueue_approved_execution(doc, payload)
	return {"name": doc.name, "status": doc.status, "agent_tool_call": doc.agent_tool_call}


@frappe.whitelist()
def reject_execution(agent_execution_approval_name: str, comment: str | None = None) -> dict:
	"""Reject a parked code execution.

	Finalizes the linked ``Agent Tool Call`` as a terminal failure and drops
	the parked payload; no job is ever enqueued.
	"""
	doc = _transition(agent_execution_approval_name, "Rejected", comment)

	reason = _("Execution approval rejected by {0}.").format(frappe.session.user)
	if comment:
		reason = f"{reason} {comment}"[:600]
	_finalize_tool_call(doc, reason)

	_execution_module(doc.execution_kind).clear_pending_execution(doc.name)
	return {"name": doc.name, "status": doc.status, "agent_tool_call": doc.agent_tool_call}
