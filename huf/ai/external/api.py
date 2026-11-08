"""Whitelisted API for the Huf UI: the signed-in user managing their own external agent connections.

These endpoints are for the Huf UI only and are not reachable through the MCP gateway.

Every function requires a logged-in user and only operates on records owned by that user. The one
exception is the list functions, which a System Manager may widen to every user with ``all_users=1``.
Session tokens are never returned.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from huf.ai.external import approvals, mailbox, sessions
from huf.ai.external.states import is_terminal

CONNECTION_DOCTYPE = "External Agent Connection"
SESSION_DOCTYPE = "External Agent Session"
EVENT_DOCTYPE = "External Agent Event"
APPROVAL_DOCTYPE = approvals.APPROVAL_DOCTYPE

RUNTIME_KINDS = ("claude_code", "codex", "other")
MODES = ("Connected", "Managed")
POLICY_VALUES = ("Allow", "Requires Approval", "Deny")

MAX_TEXT_LENGTH = 8000
MAX_LIST_LIMIT = 100
MAX_EVENT_LIMIT = 200

CONNECTION_FIELDS = [
	"name",
	"agent",
	"runtime_kind",
	"mode",
	"enabled",
	"read_policy",
	"write_policy",
	"communicate_policy",
	"last_seen",
]
SESSION_FIELDS = [
	"name",
	"connection",
	"agent",
	"state",
	"visibility_mode",
	"conversation",
	"agent_run",
	"creation",
	"ended_at",
]
EVENT_FIELDS = ["seq", "direction", "event_type", "payload", "status"]

_UNAVAILABLE_CONNECTION = "External agent connection is not available."
_UNAVAILABLE_SESSION = "External agent session is not available."
_UNAVAILABLE_APPROVAL = "External action approval is not available."

_PENDING_APPROVALS_SQL = """
	SELECT a.`name`, a.`session`, a.`tool_name`, a.`action_class`, a.`args`, a.`expires_on`
	FROM `tabExternal Action Approval` a
	INNER JOIN `tabExternal Agent Session` s ON s.`name` = a.`session`
	WHERE a.`status` = %(status)s AND a.`expires_on` > %(now)s
	ORDER BY a.`creation` DESC
	LIMIT %(limit)s
"""
_PENDING_APPROVALS_OWN_SQL = """
	SELECT a.`name`, a.`session`, a.`tool_name`, a.`action_class`, a.`args`, a.`expires_on`
	FROM `tabExternal Action Approval` a
	INNER JOIN `tabExternal Agent Session` s ON s.`name` = a.`session`
	WHERE a.`status` = %(status)s AND a.`expires_on` > %(now)s AND s.`user` = %(user)s
	ORDER BY a.`creation` DESC
	LIMIT %(limit)s
"""


def _require_user() -> None:
	if frappe.session.user in (None, "", "Guest"):
		frappe.throw(_("Please log in to continue."), frappe.PermissionError)


def _scope_user(all_users) -> str | None:
	"""Return the user to filter by, or None when a System Manager asked for every user."""
	if cint(all_users) and "System Manager" in frappe.get_roles():
		return None
	return frappe.session.user


def _clamp(value, default: int, maximum: int) -> int:
	return max(1, min(cint(value) or default, maximum))


def _validate_choice(label: str, value: str, allowed: tuple[str, ...]) -> None:
	if value not in allowed:
		frappe.throw(_("Invalid {0}: {1}").format(label, value), frappe.ValidationError)


def _parse_json(raw, fallback):
	if not raw:
		return fallback
	try:
		return json.loads(raw)
	except (TypeError, ValueError):
		return fallback


def _owned_connection(name: str) -> None:
	owner = frappe.db.get_value(CONNECTION_DOCTYPE, name, "user") if name else None
	if not owner or owner != frappe.session.user:
		frappe.throw(_UNAVAILABLE_CONNECTION, frappe.PermissionError)


def _owned_session(name: str):
	row = (
		frappe.db.get_value(SESSION_DOCTYPE, name, ["name", "user", "state"], as_dict=True) if name else None
	)
	if not row or row.user != frappe.session.user:
		frappe.throw(_UNAVAILABLE_SESSION, frappe.PermissionError)
	return row


@frappe.whitelist()
def list_connections(all_users=0) -> list[dict]:
	_require_user()
	user = _scope_user(all_users)
	filters = {"user": user} if user else {}
	return frappe.get_all(
		CONNECTION_DOCTYPE,
		filters=filters,
		fields=CONNECTION_FIELDS,
		order_by="modified desc",
	)


@frappe.whitelist(methods=["POST"])
def create_connection(
	agent: str,
	runtime_kind: str = "claude_code",
	mode: str = "Connected",
	read_policy: str = "Allow",
	write_policy: str = "Requires Approval",
	communicate_policy: str = "Requires Approval",
) -> str:
	_require_user()
	if not agent:
		frappe.throw(_("Agent is required."), frappe.ValidationError)
	_validate_choice("runtime kind", runtime_kind, RUNTIME_KINDS)
	_validate_choice("mode", mode, MODES)
	_validate_choice("read policy", read_policy, POLICY_VALUES)
	_validate_choice("write policy", write_policy, POLICY_VALUES)
	_validate_choice("communicate policy", communicate_policy, POLICY_VALUES)

	# The connection is always owned by the signed-in user. validate() enforces agent access.
	doc = frappe.get_doc(
		{
			"doctype": CONNECTION_DOCTYPE,
			"user": frappe.session.user,
			"agent": agent,
			"runtime_kind": runtime_kind,
			"mode": mode,
			"enabled": 1,
			"read_policy": read_policy,
			"write_policy": write_policy,
			"communicate_policy": communicate_policy,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist(methods=["POST"])
def update_connection(
	name: str,
	enabled=None,
	read_policy: str | None = None,
	write_policy: str | None = None,
	communicate_policy: str | None = None,
) -> dict:
	_require_user()
	_owned_connection(name)

	changes: dict = {}
	if enabled is not None:
		changes["enabled"] = 1 if cint(enabled) else 0
	for label, field, value in (
		("read policy", "read_policy", read_policy),
		("write policy", "write_policy", write_policy),
		("communicate policy", "communicate_policy", communicate_policy),
	):
		if value is not None:
			_validate_choice(label, value, POLICY_VALUES)
			changes[field] = value

	doc = frappe.get_doc(CONNECTION_DOCTYPE, name)
	doc.update(changes)
	# Owner check above; the doctype grants write permission to no one but System Manager.
	doc.save(ignore_permissions=True)
	return frappe.db.get_value(CONNECTION_DOCTYPE, name, CONNECTION_FIELDS, as_dict=True)


@frappe.whitelist()
def list_sessions(limit=20, all_users=0) -> list[dict]:
	_require_user()
	user = _scope_user(all_users)
	filters = {"user": user} if user else {}
	return frappe.get_all(
		SESSION_DOCTYPE,
		filters=filters,
		fields=SESSION_FIELDS,
		order_by="creation desc",
		limit_page_length=_clamp(limit, 20, MAX_LIST_LIMIT),
	)


@frappe.whitelist()
def get_session_events(session: str, limit=50) -> list[dict]:
	_require_user()
	_owned_session(session)

	rows = frappe.get_all(
		EVENT_DOCTYPE,
		filters={"session": session},
		fields=EVENT_FIELDS,
		order_by="seq desc",
		limit_page_length=_clamp(limit, 50, MAX_EVENT_LIMIT),
	)
	rows.reverse()
	return [
		{
			"seq": row.seq,
			"direction": row.direction,
			"event_type": row.event_type,
			"payload": _parse_json(row.payload, {}),
			"status": row.status,
		}
		for row in rows
	]


@frappe.whitelist(methods=["POST"])
def post_user_message(session: str, text: str) -> dict:
	_require_user()
	row = _owned_session(session)
	if is_terminal(row.state):
		frappe.throw(_("This session has already ended."), frappe.ValidationError)

	text = (text or "").strip()
	if not 1 <= len(text) <= MAX_TEXT_LENGTH:
		frappe.throw(
			_("Message must be between 1 and {0} characters.").format(MAX_TEXT_LENGTH),
			frappe.ValidationError,
		)
	return mailbox.post_event(session, "to_agent", "user_message", {"text": text})


@frappe.whitelist()
def list_pending_approvals(all_users=0) -> list[dict]:
	_require_user()
	user = _scope_user(all_users)
	params = {
		"status": approvals.STATUS_PENDING,
		"now": now_datetime(),
		"limit": MAX_LIST_LIMIT,
	}
	if user:
		params["user"] = user
		rows = frappe.db.sql(_PENDING_APPROVALS_OWN_SQL, params, as_dict=True)
	else:
		rows = frappe.db.sql(_PENDING_APPROVALS_SQL, params, as_dict=True)

	return [
		{
			"name": row.name,
			"session": row.session,
			"tool_name": row.tool_name,
			"action_class": row.action_class,
			"args": _parse_json(row.args, {}),
			"expires_on": row.expires_on,
		}
		for row in rows
	]


@frappe.whitelist(methods=["POST"])
def decide(approval: str, approve=0, comment: str | None = None) -> dict:
	_require_user()
	session = frappe.db.get_value(APPROVAL_DOCTYPE, approval, "session") if approval else None
	if not session:
		frappe.throw(_UNAVAILABLE_APPROVAL, frappe.PermissionError)
	_owned_session(session)
	return approvals.decide_approval(approval, bool(cint(approve)), comment)


@frappe.whitelist(methods=["POST"])
def cancel(session: str) -> str:
	_require_user()
	_owned_session(session)
	sessions.cancel_session(session)
	return frappe.db.get_value(SESSION_DOCTYPE, session, "state")
