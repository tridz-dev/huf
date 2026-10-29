"""Run-as identity and audit stamp for inbound-triggered runs.

A Gateway's ``run_as_user`` (when set) is the user the agent run executes as. Documents created
during the run carry ``huf_channel_conversation`` (a Custom Field) naming the Channel Conversation.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe import _

AUDIT_FIELD = "huf_channel_conversation"
AUDIT_DOCTYPES = ("HD Ticket", "CRM Lead", "Sales Order", "Contact", "ToDo")

_current_conversation: ContextVar[str | None] = ContextVar("huf_channel_conversation", default=None)


def validate_run_as(gateway) -> None:
	"""run_as_user must be an enabled System User, never Administrator/Guest.

	run_as_role_profile is validated only (not applied): it must equal the user's role_profile_name.
	"""
	user = (gateway.get("run_as_user") or "").strip()
	profile = (gateway.get("run_as_role_profile") or "").strip()
	if not user:
		if profile:
			frappe.throw(_("Choose a Run as user before setting a Run as role profile."))
		return
	if user in ("Administrator", "Guest"):
		frappe.throw(_("Run as user cannot be Administrator or Guest. Use a least-privileged service user."))
	row = frappe.db.get_value("User", user, ["enabled", "user_type", "role_profile_name"], as_dict=True)
	if not row:
		frappe.throw(_("Run as user {0} does not exist.").format(user))
	if not row.enabled:
		frappe.throw(_("Run as user {0} is disabled.").format(user))
	if row.user_type != "System User":
		frappe.throw(_("Run as user {0} must be a System User.").format(user))
	if profile and (row.role_profile_name or "") != profile:
		frappe.throw(_("Run as role profile must match the role profile of {0}.").format(user))
	_reject_privileged(user)


def _reject_privileged(user: str) -> None:
	"""Reject admin-grade run-as users and privilege escalation by the saving user."""
	from huf.permissions import has_capability

	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		frappe.throw(_("Run as user {0} has the System Manager role. Use a least-privileged service user.").format(user))
	if has_capability(user, "system.integrations.manage"):
		frappe.throw(
			_("Run as user {0} can manage integrations (system.integrations.manage). Use a least-privileged service user.").format(user)
		)
	saver = frappe.session.user
	if saver != "Administrator":
		extra = sorted(roles - set(frappe.get_roles(saver)))
		if extra:
			frappe.throw(
				_("Run as user {0} holds roles you do not have ({1}). You can only choose a user whose roles are a subset of yours.").format(
					user, ", ".join(extra)
				)
			)


@contextmanager
def channel_inbound():
	"""Mark records written while relaying a customer's inbound message into a linked doc."""
	prev = getattr(frappe.flags, "huf_channel_inbound", False)
	frappe.flags.huf_channel_inbound = True
	try:
		yield
	finally:
		frappe.flags.huf_channel_inbound = prev


def current_conversation() -> str | None:
	return _current_conversation.get()


def set_current_conversation(name: str | None):
	"""Set the conversation for the current run; returns a token for reset_current_conversation."""
	return _current_conversation.set(name or None)


def reset_current_conversation(token) -> None:
	_current_conversation.reset(token)


def stamp_audit(doc, method=None) -> None:
	"""doc_events '*' before_insert: stamp the field when a run is active and the doctype has it."""
	name = _current_conversation.get()
	if not name or doc.doctype == "Channel Conversation":
		return
	if doc.meta.has_field(AUDIT_FIELD):
		doc.set(AUDIT_FIELD, name)


def ensure_channel_audit_field(doctype: str) -> bool:
	"""Add the audit Custom Field to doctype if the doctype exists and lacks it."""
	if not frappe.db.exists("DocType", doctype):
		return False
	if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": AUDIT_FIELD}):
		return False
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": doctype,
			"fieldname": AUDIT_FIELD,
			"label": "Channel Conversation",
			"fieldtype": "Link",
			"options": "Channel Conversation",
			"read_only": 1,
			"in_list_view": 0,
			"hidden": 0,
			"no_copy": 1,
			"print_hide": 1,
		}
	).insert(ignore_permissions=True)
	return True


def ensure_all_audit_fields() -> None:
	"""after_migrate hook."""
	for doctype in AUDIT_DOCTYPES:
		ensure_channel_audit_field(doctype)
