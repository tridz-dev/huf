from __future__ import annotations

import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from huf.ai.agent.access import assert_agent_access
from huf.ai.external import mailbox
from huf.ai.external.core.states import (
	ACTIVE,
	CANCELLED,
	COMPLETED,
	FAILED,
	RUNTIME_OFFLINE,
	WAITING_APPROVAL,
	WAITING_INPUT,
	assert_transition,
	is_terminal,
)

SESSION_DOCTYPE = "External Agent Session"
CONNECTION_DOCTYPE = "External Agent Connection"
CONVERSATION_DOCTYPE = "Agent Conversation"
RUN_DOCTYPE = "Agent Run"

CONNECTION_MODE_MANAGED = "Managed"
VISIBILITY_MANAGED = "Huf-managed"
VISIBILITY_CONNECTED = "Connected"

LEASE_SCANNED_STATES = (ACTIVE, WAITING_INPUT, WAITING_APPROVAL)
LAST_SEEN_THROTTLE_SECONDS = 60

_CLOSED_MESSAGE = "Unknown or closed session"


def _check_connection(connection_name: str):
	"""Return the connection doc if it exists, is enabled and belongs to the current user."""
	connection = frappe.db.get_value(
		CONNECTION_DOCTYPE,
		connection_name,
		["name", "user", "agent", "enabled", "mode"],
		as_dict=True,
	)
	if not connection or not connection.enabled:
		frappe.throw(_("External agent connection is not available."), frappe.PermissionError)
	if connection.user != frappe.session.user:
		frappe.throw(_("External agent connection is not available."), frappe.PermissionError)
	return connection


def create_session(connection_name: str, native_session_id: str | None = None) -> dict:
	connection = _check_connection(connection_name)
	agent_doc = frappe.get_doc("Agent", connection.agent)
	assert_agent_access(agent_doc, frappe.session.user)

	conversation = frappe.get_doc(
		{
			"doctype": CONVERSATION_DOCTYPE,
			"title": "External session",
			"agent": connection.agent,
			"session_id": frappe.generate_hash(length=20),
			"is_active": 1,
			"channel": "external_agent",
			"external_id": connection_name,
		}
	).insert(ignore_permissions=True)

	agent_run = frappe.get_doc(
		{
			"doctype": RUN_DOCTYPE,
			"conversation": conversation.name,
			"agent": connection.agent,
			"status": "Started",
			"start_time": now_datetime(),
		}
	).insert(ignore_permissions=True)

	token = secrets.token_urlsafe(32)
	session = frappe.get_doc(
		{
			"doctype": SESSION_DOCTYPE,
			"connection": connection_name,
			"user": frappe.session.user,
			"agent": connection.agent,
			"conversation": conversation.name,
			"agent_run": agent_run.name,
			"state": ACTIVE,
			"visibility_mode": (
				VISIBILITY_MANAGED if connection.mode == CONNECTION_MODE_MANAGED else VISIBILITY_CONNECTED
			),
			"session_token": token,
			"native_session_id": native_session_id,
		}
	).insert(ignore_permissions=True)

	return {
		"session": session.name,
		"token": token,
		"conversation": conversation.name,
		"agent_run": agent_run.name,
	}


def get_session_for_token(token: str):
	"""Resolve a session by its token for the current user.

	Every failure (unknown token, another user, closed session, disabled connection,
	lost agent access) raises the same generic PermissionError so callers cannot tell
	which condition failed.
	"""
	denied = (_CLOSED_MESSAGE, frappe.PermissionError)
	if not token:
		frappe.throw(*denied)

	name = frappe.db.get_value(
		SESSION_DOCTYPE,
		{"session_token": token, "user": frappe.session.user},
		"name",
	)
	if not name:
		frappe.throw(*denied)

	session = frappe.get_doc(SESSION_DOCTYPE, name)
	if is_terminal(session.state):
		frappe.throw(*denied)

	connection = frappe.db.get_value(
		CONNECTION_DOCTYPE, session.connection, ["enabled", "user"], as_dict=True
	)
	if not connection or not connection.enabled or connection.user != frappe.session.user:
		frappe.throw(*denied)

	try:
		agent_doc = frappe.get_doc("Agent", session.agent)
		assert_agent_access(agent_doc, frappe.session.user)
	except (frappe.DoesNotExistError, frappe.PermissionError):
		frappe.throw(*denied)

	return session


def transition(session_name: str, new_state: str) -> None:
	row = frappe.db.get_value(
		SESSION_DOCTYPE,
		session_name,
		["state", "agent_run"],
		as_dict=True,
		for_update=True,
	)
	if not row:
		frappe.throw(_("External agent session not found."), frappe.DoesNotExistError)

	try:
		assert_transition(row.state, new_state)
	except ValueError:
		frappe.throw(
			_("Cannot change session from {0} to {1}.").format(row.state, new_state),
			frappe.ValidationError,
		)

	values = {"state": new_state}
	terminal = is_terminal(new_state)
	if terminal:
		values["ended_at"] = now_datetime()
	frappe.db.set_value(SESSION_DOCTYPE, session_name, values, update_modified=True)

	if terminal and row.agent_run:
		run_values = {"end_time": now_datetime()}
		if new_state == COMPLETED:
			run_values["status"] = "Success"
		elif new_state == FAILED:
			run_values["status"] = "Failed"
		elif new_state == CANCELLED:
			run_values["status"] = "Failed"
			run_values["error_message"] = "Cancelled"
		frappe.db.set_value(RUN_DOCTYPE, row.agent_run, run_values)


def cancel_session(session_name: str) -> None:
	owner = frappe.db.get_value(SESSION_DOCTYPE, session_name, "user")
	if not owner:
		frappe.throw(_("External agent session not found."), frappe.DoesNotExistError)

	user = frappe.session.user
	if owner != user and "System Manager" not in frappe.get_roles(user):
		frappe.throw(_("You do not have permission to cancel this session."), frappe.PermissionError)

	state = frappe.db.get_value(SESSION_DOCTYPE, session_name, "state")
	if is_terminal(state):
		return
	transition(session_name, CANCELLED)
	# Posted after the transition, not before: the event is only announced once the cancel has
	# actually happened, and post_event does not check session state, so the terminal state does not
	# block it. The row lock it takes is already held by this transaction via transition(), so
	# there is no extra lock wait.
	mailbox.post_event(
		session_name,
		"to_agent",
		"session_cancelled",
		{"reason": "cancelled"},
		idempotency_key=f"cancel-{session_name}",
	)


def renew_lease(session_name: str, owner: str, ttl_seconds: int = 60) -> None:
	row = frappe.db.get_value(
		SESSION_DOCTYPE,
		session_name,
		["state", "lease_owner", "lease_expires"],
		as_dict=True,
		for_update=True,
	)
	if not row:
		frappe.throw(_("External agent session not found."), frappe.DoesNotExistError)
	if is_terminal(row.state):
		frappe.throw(_("Unknown or closed session"), frappe.PermissionError)

	now = now_datetime()
	if (
		row.lease_owner
		and row.lease_owner != owner
		and row.lease_expires
		and get_datetime(row.lease_expires) > now
	):
		frappe.throw(_("Session is owned by another runtime"), frappe.PermissionError)

	frappe.db.set_value(
		SESSION_DOCTYPE,
		session_name,
		{
			"lease_owner": owner,
			"lease_expires": add_to_date(now, seconds=ttl_seconds),
		},
	)

	if row.state == RUNTIME_OFFLINE:
		transition(session_name, ACTIVE)


def expire_stale_leases() -> None:
	now = now_datetime()
	names = frappe.get_all(
		SESSION_DOCTYPE,
		filters=[
			["state", "in", list(LEASE_SCANNED_STATES)],
			["lease_expires", "is", "set"],
			["lease_expires", "<", now],
		],
		pluck="name",
	)
	for name in names:
		try:
			transition(name, RUNTIME_OFFLINE)
		except Exception:  # noqa: BLE001 - one bad session must not stop the scheduler sweep
			frappe.log_error(title="External session lease expiry failed", message=f"session={name}")


def touch_connection(connection_name: str) -> None:
	last_seen = frappe.db.get_value(CONNECTION_DOCTYPE, connection_name, "last_seen")
	cutoff = add_to_date(now_datetime(), seconds=-LAST_SEEN_THROTTLE_SECONDS)
	if last_seen and get_datetime(last_seen) >= cutoff:
		return
	frappe.db.set_value(
		CONNECTION_DOCTYPE, connection_name, "last_seen", now_datetime(), update_modified=False
	)
