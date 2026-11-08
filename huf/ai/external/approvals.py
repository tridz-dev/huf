"""Generic approval workflow for external agent tool calls.

An External Action Approval authorises exactly one execution of one tool call, identified by
(session, tool_name, args_hash). Approvals expire after APPROVAL_TTL_MINUTES; expiry is enforced
at consume time as well as by the scheduled ``expire_pending_approvals`` job.

Authority: only the session's user or a System Manager can decide an approval. The agent has no
MCP capability that reaches ``decide_approval``; it is only exposed to the Huf UI API.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from huf.ai.external import states
from huf.ai.external.idempotency import args_hash, canonical_json

APPROVAL_TTL_MINUTES = 30

APPROVAL_DOCTYPE = "External Action Approval"
SESSION_DOCTYPE = "External Agent Session"

STATUS_PENDING = "Pending"
STATUS_APPROVED = "Approved"
STATUS_REJECTED = "Rejected"
STATUS_EXPIRED = "Expired"
STATUS_CONSUMED = "Consumed"

REALTIME_REQUESTED = "huf_external_approval_requested"


def _transition_session(session: str, to_state: str) -> None:
	# Imported lazily: the sessions module owns the transition rules and persistence.
	from huf.ai.external import sessions

	sessions.transition(session, to_state)


def _session_user(session: str) -> str | None:
	return frappe.db.get_value(SESSION_DOCTYPE, session, "user")


def request_approval(session: str, tool_name: str, action_class: str, args: dict | None) -> dict:
	"""Create (or reuse) a Pending approval for this exact tool call.

	Returns ``{"approval": <name>, "status": "Pending"}``. If a Pending, unexpired approval already
	exists for the same session, tool and args hash, that approval is returned instead of a new one.
	The session row is locked first so concurrent first calls cannot both create an approval.
	"""
	frappe.db.get_value(SESSION_DOCTYPE, session, "state", for_update=True)

	session_user = _session_user(session)
	if not session_user:
		frappe.throw(_("Unknown external agent session"), frappe.ValidationError)

	now = now_datetime()
	digest = args_hash(args)

	existing = frappe.db.get_value(
		APPROVAL_DOCTYPE,
		{
			"session": session,
			"tool_name": tool_name,
			"args_hash": digest,
			"status": STATUS_PENDING,
			"expires_on": (">", now),
		},
		"name",
	)
	if existing:
		return {"approval": existing, "status": STATUS_PENDING}

	approval = frappe.get_doc(
		{
			"doctype": APPROVAL_DOCTYPE,
			"session": session,
			"tool_name": tool_name,
			"action_class": action_class,
			"args_hash": digest,
			"args": canonical_json(args or {}),
			"status": STATUS_PENDING,
			"requested_by": session_user,
			"expires_on": add_to_date(now, minutes=APPROVAL_TTL_MINUTES),
		}
	)
	approval.insert(ignore_permissions=True)

	if frappe.db.get_value(SESSION_DOCTYPE, session, "state") == states.ACTIVE:
		_transition_session(session, states.WAITING_APPROVAL)

	frappe.publish_realtime(
		REALTIME_REQUESTED,
		{"approval": approval.name, "session": session, "tool_name": tool_name},
		user=session_user,
	)

	return {"approval": approval.name, "status": STATUS_PENDING}


def decide_approval(approval_name: str, approve: bool, comment: str | None = None) -> dict:
	"""Approve or reject a Pending approval. Only the session's user or a System Manager may decide.

	If the approval has already expired it is marked Expired (committed) and an error is raised.
	When the session has no Pending approvals left and is WAITING_APPROVAL, it returns to ACTIVE.
	"""
	row = frappe.db.get_value(
		APPROVAL_DOCTYPE,
		approval_name,
		["session", "status", "expires_on"],
		as_dict=True,
		for_update=True,
	)
	if not row:
		frappe.throw(_("Approval not found"), frappe.DoesNotExistError)

	session = row.session
	session_user = _session_user(session)
	if frappe.session.user != session_user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("You are not allowed to decide this approval"), exc=frappe.PermissionError)

	if row.status != STATUS_PENDING:
		frappe.throw(_("Approval has already been decided"), frappe.ValidationError)

	now = now_datetime()
	if row.expires_on and row.expires_on < now:
		frappe.db.set_value(APPROVAL_DOCTYPE, approval_name, "status", STATUS_EXPIRED)
		# Commit so the expiry survives the error raised below.
		frappe.db.commit()
		frappe.throw(_("Approval has expired"), frappe.ValidationError)

	approval = frappe.get_doc(APPROVAL_DOCTYPE, approval_name)
	approval.status = STATUS_APPROVED if approve else STATUS_REJECTED
	approval.decided_by = frappe.session.user
	approval.decided_at = now
	if comment is not None:
		approval.comment = comment
	approval.save(ignore_permissions=True)

	# Stale Pending approvals for this session must not keep it waiting.
	frappe.db.sql(
		"""
		UPDATE `tabExternal Action Approval`
		SET status = %s, modified = %s
		WHERE session = %s AND status = %s AND expires_on < %s
		""",
		(STATUS_EXPIRED, now, session, STATUS_PENDING, now),
	)
	still_pending = frappe.db.count(APPROVAL_DOCTYPE, {"session": session, "status": STATUS_PENDING})
	if (
		still_pending == 0
		and frappe.db.get_value(SESSION_DOCTYPE, session, "state") == states.WAITING_APPROVAL
	):
		_transition_session(session, states.ACTIVE)

	return {"approval": approval_name, "status": approval.status, "session": session}


def consume_approval(session: str, tool_name: str, args: dict | None) -> bool:
	"""Atomically consume one Approved, unexpired approval for this exact call.

	Returns True and marks the approval Consumed, or False if no usable approval exists.
	"""
	digest = args_hash(args)
	rows = frappe.db.sql(
		"""
		SELECT name FROM `tabExternal Action Approval`
		WHERE session = %s AND tool_name = %s AND args_hash = %s
			AND status = %s AND expires_on > %s
		ORDER BY modified ASC
		LIMIT 1
		FOR UPDATE
		""",
		(session, tool_name, digest, STATUS_APPROVED, now_datetime()),
	)
	if not rows:
		return False

	frappe.db.set_value(APPROVAL_DOCTYPE, rows[0][0], "status", STATUS_CONSUMED)
	return True


def expire_pending_approvals() -> None:
	"""Scheduler entry: mark Pending approvals whose expiry has passed as Expired."""
	now = now_datetime()
	frappe.db.sql(
		"""
		UPDATE `tabExternal Action Approval`
		SET status = %s, modified = %s
		WHERE status = %s AND expires_on < %s
		""",
		(STATUS_EXPIRED, now, STATUS_PENDING, now),
	)


def get_approval_state(session: str, tool_name: str, args: dict | None) -> str | None:
	"""Return the status of the newest approval for this exact call, or None if there is none."""
	return frappe.db.get_value(
		APPROVAL_DOCTYPE,
		{"session": session, "tool_name": tool_name, "args_hash": args_hash(args)},
		"status",
		order_by="creation desc",
	)
