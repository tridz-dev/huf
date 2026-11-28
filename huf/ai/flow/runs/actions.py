# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Run actions for the run page: cancel a run that is still waiting for a worker."""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.flow.runs.access import require_run_access


@frappe.whitelist(methods=["POST"])
def cancel_flow_run(flow_run_id: str) -> dict:
	"""Stop a run that has not started or is waiting (timer, approval, user input, code). Needs permission to edit THE FLOW this run belongs to.

	The run is recorded as cancelled by the person who did it. A run a worker is advancing right now, or one
	that finished meanwhile, is left alone with a plain message.
	"""
	# Edit rights on this run's own flow (not "can edit some flow"), and write on the run itself.
	from huf.ai.flow.app_scope.api_guards import guard_run
	guard_run(flow_run_id, "edit")
	require_run_access(flow_run_id, "write", "write", _("Only people who can edit this flow can cancel its runs."))

	from huf.ai.flow.runs import park

	if not park.cancel_run(flow_run_id, frappe.session.user):
		status = frappe.db.get_value("Agent Flow Run", flow_run_id, "status")
		if status == "Running":
			frappe.throw(_("This run is working right now, so it cannot be cancelled."))
		frappe.throw(_("This run is {0}, so it cannot be cancelled.").format(status))
	return {"flow_run_id": flow_run_id, "status": frappe.db.get_value("Agent Flow Run", flow_run_id, "status")}


@frappe.whitelist(methods=["POST"])
def continue_waiting_run(flow_run_id: str) -> dict:
	"""Skip the rest of a timed wait and carry on now. Needs permission to edit THE FLOW this run belongs to."""
	from huf.ai.flow.app_scope.api_guards import guard_run
	guard_run(flow_run_id, "edit")
	require_run_access(flow_run_id, "write", "write", _("Only people who can edit this flow can continue its runs."))

	from huf.ai.flow.runs import park

	if not park.wake_run(flow_run_id, "continued"):
		status = frappe.db.get_value("Agent Flow Run", flow_run_id, "status")
		frappe.throw(_("This run is {0}, so it is not waiting on a timer.").format(status))
	return {"flow_run_id": flow_run_id, "status": frappe.db.get_value("Agent Flow Run", flow_run_id, "status")}


@frappe.whitelist(methods=["POST"])
def get_resume_link(flow_run_id: str) -> dict:
	"""The single-use link that continues a run parked on a resume-mode wait. Needs permission to edit THE FLOW."""
	from huf.ai.flow.app_scope.api_guards import guard_run
	guard_run(flow_run_id, "edit")
	require_run_access(flow_run_id, "write", "write", _("Only people who can edit this flow can see its resume link."))

	from urllib.parse import urlencode

	from frappe.utils import get_url

	from huf.ai.flow.runs import park

	run = frappe.get_doc("Agent Flow Run", flow_run_id)
	token = park.resume_token(run) if run.status == park.WAIT_STATUS else None
	if not token:
		frappe.throw(_("This run is not waiting for its resume link."))
	query = urlencode({"flow_run": run.name, "token": token})
	return {"url": get_url(f"/api/method/huf.ai.flow.runs.resume_api.resume_waiting_run?{query}")}
