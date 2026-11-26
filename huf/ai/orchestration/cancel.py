"""Stop for Started runs that the stream loop does not drive (multi-step plans, queued/sync runs)."""

import frappe
from frappe.utils import now_datetime

from huf.ai.run_control import CANCELLED_BY_USER, is_run_cancelled, mark_cancelled_tool_calls
from huf.ai.transaction import safe_commit

ACTIVE_STATUSES = ("Planned", "Running", "Paused")


def _active_orchestration(run_id):
	"""The unfinished orchestration this run is the parent or a step of, else None. Never raises."""
	try:
		fields = ["name", "parent_run"]
		rows = frappe.get_all(
			"Agent Orchestration",
			filters={"parent_run": run_id, "status": ["in", ACTIVE_STATUSES]},
			fields=fields,
		)
		if rows:
			return rows[0]
		step = frappe.get_all("Agent Run", filters={"name": run_id}, fields=["agent_orchestration"])
		if step and step[0].agent_orchestration:
			rows = frappe.get_all(
				"Agent Orchestration",
				filters={"name": step[0].agent_orchestration, "status": ["in", ACTIVE_STATUSES]},
				fields=fields,
			)
			return rows[0] if rows else None
	except Exception as exc:  # noqa: BLE001 - Stop must not fail on a lookup error
		frappe.logger("huf").warning(f"orchestration lookup for cancel failed for {run_id}: {exc!r}")
	return None


def _fail_started(run_id) -> None:
	from huf.ai.agent.integration import _guarded_fail_started_run

	if _guarded_fail_started_run(run_id, CANCELLED_BY_USER):
		mark_cancelled_tool_calls(run_id)


def _stop(orchestration) -> None:
	"""No further steps are scheduled and the parent run becomes terminal."""
	frappe.db.set_value("Agent Orchestration", orchestration.name, "status", "Cancelled")
	if orchestration.parent_run:
		_fail_started(orchestration.parent_run)


def cancel_orchestration_for_run(run_id) -> bool:
	"""Cancel the plan behind ``run_id``. True only when ``run_id`` itself is now finalized.

	A step run keeps the regular cooperative path (False), after its plan has been cancelled.
	"""
	orchestration = _active_orchestration(run_id)
	if not orchestration:
		return False
	_stop(orchestration)
	return orchestration.parent_run == run_id


def honour_cancel(orch) -> bool:
	"""Checked by the step job: True when the plan must not go on."""
	if frappe.db.get_value("Agent Orchestration", orch.name, "status") == "Cancelled":
		return True
	if not is_run_cancelled(orch.parent_run):
		return False
	_stop(orch)
	safe_commit()
	return True


def finish_if_cancelled(run_doc, conversation):
	"""After a non-streaming provider call: finalize a stopped run instead of saving a Success.

	Returns the run result to hand back, or None when the run was not stopped.
	"""
	if not is_run_cancelled(run_doc.name):
		return None
	from huf.ai.agent.integration import _emit_run_lifecycle_event

	_fail_started(run_doc.name)
	frappe.db.set_value("Agent Run", run_doc.name, "end_time", now_datetime(), update_modified=False)
	_emit_run_lifecycle_event(run_doc, conversation, "failed", {"error": CANCELLED_BY_USER})
	safe_commit()
	return {
		"success": False,
		"cancelled": True,
		"error": CANCELLED_BY_USER,
		"agent_run_id": run_doc.name,
		"conversation_id": conversation.name,
	}
