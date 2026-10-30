# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Who may do what to ONE run, checked on the record and on its flow (security round 2, DECISIONS 13).

``frappe.has_permission("Flow Run", "write")`` without a document only asks "does any of your roles allow it": it
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


def can_access_run(flow_run_id: str, ptype: str = "read", flow_ptype: str | None = None) -> bool:
	"""True when the caller may ``ptype`` the run and ``flow_ptype`` (default: read) its flow. A missing run answers False."""
	if not flow_run_id or not frappe.db.exists("Flow Run", flow_run_id):
		return False
	if not frappe.has_permission("Flow Run", ptype, doc=flow_run_id):
		return False
	flow_id = frappe.db.get_value("Flow Run", flow_run_id, "flow_id")
	if flow_id and frappe.db.exists("Flow Definition", flow_id):
		return bool(frappe.has_permission("Flow Definition", flow_ptype or "read", doc=flow_id))
	return True  # the flow was deleted: only the run's own permission is left to check


def require_run_access(flow_run_id: str, ptype: str = "read", flow_ptype: str | None = None, message: str | None = None) -> str | None:
	"""Raise unless :func:`can_access_run`. A run that does not exist is a plain "not found". Returns the run's flow id."""
	if not flow_run_id or not frappe.db.exists("Flow Run", flow_run_id):
		frappe.throw(_("Run not found"), frappe.DoesNotExistError)
	if not can_access_run(flow_run_id, ptype, flow_ptype):
		frappe.throw(message or _("Not permitted"), frappe.PermissionError)
	return frappe.db.get_value("Flow Run", flow_run_id, "flow_id")
