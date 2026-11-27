# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Who may do what to ONE run, checked on the record and on its flow (security round 2, DECISIONS 13).

``frappe.has_permission("Agent Flow Run", "write")`` without a document only asks "does any of your roles allow it": it
ignores User Permissions and shares, and says nothing about the flow the run belongs to. Every whitelisted action on
a single run goes through :func:`require_run_access` instead, which checks

* the Flow Run itself, for that run (``doc=``), and
* the run's Flow Definition, for that flow (``doc=``): reading a run's data needs read on its flow, and an action that
  changes a run (cancel, mark as failed) needs write on its flow.

Deciding an approval is different on purpose: the approver rules of the step decide (``engine.verify_approval_permission``).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.core.doctype.user_permission.user_permission import get_user_permissions
from frappe.permissions import has_user_permission

from huf.ai.flow.app_scope.access import apps_for, flow_access, is_privileged
from huf.ai.flow.app_scope.ownership import owner_app_of


def can_access_run(flow_run_id: str, ptype: str = "read", flow_ptype: str | None = None) -> bool:
	"""True when the caller may ``ptype`` the run and ``flow_ptype`` (default: read) its flow. A missing run answers False."""
	if not flow_run_id or not frappe.db.exists("Agent Flow Run", flow_run_id):
		return False
	app_flow = delegated_flow_of_run(flow_run_id)
	if app_flow:
		# App roles hold no run DocPerm: reading goes through the flow grant, and they never write a run.
		# User Permissions still apply, on the flow and on every link field of the run.
		return bool(
			ptype == "read"
			and flow_ptype in (None, "read")
			and flow_access(None, app_flow, "view")
			and frappe.has_permission("Flow Definition", "read", doc=app_flow)
			and has_user_permission(frappe.get_doc("Agent Flow Run", flow_run_id), ptype="read")
		)
	if not frappe.has_permission("Agent Flow Run", ptype, doc=flow_run_id):
		return False
	flow_id = frappe.db.get_value("Agent Flow Run", flow_run_id, "flow_id")
	if flow_id and frappe.db.exists("Flow Definition", flow_id):
		return bool(frappe.has_permission("Flow Definition", flow_ptype or "read", doc=flow_id))
	return True  # the flow was deleted: only the run's own permission is left to check


def delegated_flow_of_run(flow_run_id: str) -> str | None:
	"""The run's flow when it is app-owned and the caller is not privileged, else None."""
	row = frappe.db.get_value("Agent Flow Run", flow_run_id, ["flow_definition", "flow_id"], as_dict=True)
	flow = row and (row.flow_definition or row.flow_id)
	return flow if flow and is_delegated_flow(flow) else None


def is_delegated_flow(flow_id: str | None) -> bool:
	return bool(flow_id and not is_privileged() and owner_app_of(flow_id))


def can_list_runs() -> bool:
	"""Whether the caller may see any run list at all; each list still scopes what it returns."""
	return bool(frappe.has_permission("Agent Flow Run", "read") or apps_for(None, "view"))


def run_reader(flow_id: str | None):
	"""The query function for a run list already guarded on ``flow_id``.

	``get_all`` (narrowed by User Permissions) only for one app-owned flow the guard has checked; otherwise
	``get_list`` (DocPerm and scope).
	"""
	if is_delegated_flow(flow_id) and flow_access(None, flow_id, "view"):
		return _get_user_permitted_runs
	return frappe.get_list


def _get_user_permitted_runs(doctype: str, filters=None, or_filters=None, **kwargs) -> list:
	"""``get_all`` on runs, leaving out those the caller's User Permissions hide (``get_all`` ignores them).

	Narrowed before ordering and paging, so pages and totals stay correct.
	"""
	if not get_user_permissions(frappe.session.user):
		return frappe.get_all(doctype, filters=filters, or_filters=or_filters, **kwargs)
	links = [field.fieldname for field in frappe.get_meta(doctype).get_link_fields()]
	rows = frappe.get_all(
		doctype, filters=filters, or_filters=or_filters, fields=["name", *links], limit_page_length=0
	)
	allowed = [
		row.name
		for row in rows
		if has_user_permission(frappe.get_doc({"doctype": doctype, **row}), ptype="read")
	]
	if not allowed:
		return []
	return frappe.get_all(doctype, filters={"name": ("in", allowed)}, **kwargs)


def require_run_access(
	flow_run_id: str, ptype: str = "read", flow_ptype: str | None = None, message: str | None = None
) -> str | None:
	"""Raise unless :func:`can_access_run`. A run that does not exist is a plain "not found". Returns the run's flow id."""
	if not flow_run_id or not frappe.db.exists("Agent Flow Run", flow_run_id):
		frappe.throw(_("Run not found"), frappe.DoesNotExistError)
	if not can_access_run(flow_run_id, ptype, flow_ptype):
		frappe.throw(message or _("Not permitted"), frappe.PermissionError)
	return frappe.db.get_value("Agent Flow Run", flow_run_id, "flow_id")


def require_flow_read(flow_id: str | None) -> None:
	"""Raise unless the caller may read that flow (an unknown or empty id is left to the caller's own not-found handling)."""
	if (
		flow_id
		and frappe.db.exists("Flow Definition", flow_id)
		and not frappe.has_permission("Flow Definition", "read", doc=flow_id)
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
