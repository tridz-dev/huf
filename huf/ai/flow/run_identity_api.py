# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""Who started a Flow Run and which run of its flow it is, for the friendly run title.

The Run details page reads "Run #12 . started by you . 2 min ago" instead of the internal run id. The number
is the run's place in its own flow's history (oldest run is #1), so it is stable and means something to a
person. Kept out of ``api.get_flow_run`` so the run payload stays unchanged.
"""

import frappe
from frappe import _


@frappe.whitelist(methods=["GET"])
def get_flow_run_identity(flow_run_id: str) -> dict:
	"""``{run_number, started_by, started_by_name}`` for one Flow Run the caller may read."""
	if not frappe.has_permission("Flow Run", "read", flow_run_id):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	run = frappe.db.get_value("Flow Run", flow_run_id, ["flow_id", "creation", "owner"], as_dict=True)
	if not run:
		frappe.throw(_("Run not found"), frappe.DoesNotExistError)
	return {
		"run_number": run_number(run.flow_id, run.creation),
		"started_by": run.owner,
		"started_by_name": _full_name(run.owner),
	}


def run_number(flow_id: str, creation) -> int:
	"""1-based place of a run among all runs of its flow, oldest first."""
	return frappe.db.count("Flow Run", {"flow_id": flow_id, "creation": ["<=", creation]})


def _full_name(user: str | None) -> str | None:
	if not user:
		return None
	return frappe.db.get_value("User", user, "full_name") or user
