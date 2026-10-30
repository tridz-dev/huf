# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run actions for the run page: cancel a run that is still waiting for a worker."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist(methods=["POST"])
def cancel_flow_run(flow_run_id: str) -> dict:
	"""Stop a run that is still queued (it never started). Needs permission to edit flows.

	The run is recorded as stopped by the person who cancelled it. A run that a worker already picked up, or
	that finished meanwhile, is left alone with a plain message.
	"""
	if not frappe.has_permission("Flow Definition", "write"):
		frappe.throw(_("Only people who can edit flows can cancel a run."), frappe.PermissionError)
	if not frappe.db.exists("Flow Run", flow_run_id):
		frappe.throw(_("Run not found"), frappe.DoesNotExistError)

	from huf.ai.flow import engine

	if not engine._acquire_run_lock(flow_run_id):
		frappe.throw(_("A worker has just picked this run up, so it cannot be cancelled."))
	try:
		doc = frappe.get_doc("Flow Run", flow_run_id)
		if doc.status != "Queued":
			frappe.throw(_("This run is {0}, so it cannot be cancelled. Only a run that is waiting for a worker can.").format(doc.status))
		if not engine._fail_flow_run(doc, _("Cancelled by {0} before it started.").format(frappe.session.user)):
			frappe.throw(_("This run has already finished, so it was left as it is."))
		frappe.db.commit()  # nosemgrep -- the change must be durable before the lock is released
	finally:
		engine._release_run_lock(flow_run_id)
	doc.reload()
	return {"flow_run_id": doc.name, "status": doc.status}
