"""``flow.call`` node: start another published flow, and optionally wait for it.

Config: ``flow_id`` (the flow to start), ``input`` (the child's trigger payload; ``$from`` / ``$template`` values are
resolved), ``mode`` (``fire_and_forget`` by default, or ``wait``).

The child is an ordinary Flow Run linked to this run by ``parent_run`` / ``parent_node``. In ``wait`` mode the parent
parks (``park.park_run``, reason ``child``) *before* the child is enqueued, and the engine's terminal functions
(``_complete_flow_run`` / ``_fail_flow_run`` / ``park.cancel_run``) call :func:`on_child_finished`, which wakes the
parent with ``{status, error, output}``. A child that did not succeed makes this step fail, so ``on_error`` applies.
Cancelling a parent that waits for a child cancels that child too.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import frappe

from huf.ai.flow.runs import park
from huf.ai.flow.runs.park import ParkRequest

MAX_DEPTH = 5
KEYS = frozenset({"flow_id", "input", "mode"})
MODES = ("fire_and_forget", "wait")


def _failed(message: str) -> dict:
	return {"status": "failed", "error": message}


def _depth(flow_run) -> int:
	"""How many runs are above ``flow_run`` in the chain of parents."""
	depth, seen, parent = 0, {flow_run.name}, getattr(flow_run, "parent_run", None)
	while parent and parent not in seen:
		seen.add(parent)
		depth += 1
		parent = frappe.db.get_value("Agent Flow Run", parent, "parent_run")
	return depth


def _check_child(flow_run, flow_id) -> str | None:
	"""Why this run may not start ``flow_id``, or None when it may."""
	if not isinstance(flow_id, str) or not flow_id:
		return "Choose the flow this step should run."
	if flow_id == flow_run.flow_id:
		return "A flow cannot run itself. Choose a different flow."
	if _depth(flow_run) + 1 > MAX_DEPTH:
		return f"Flows can run other flows only {MAX_DEPTH} levels deep. Remove a step that runs another flow."
	status = frappe.db.get_value("Flow Definition", flow_id, "status") if frappe.db.exists("Flow Definition", flow_id) else None
	if status is None:
		return "The flow this step runs no longer exists. Choose another flow."
	if status != "Active":
		return "The flow this step runs is not published. Publish it first, or choose another flow."
	if not frappe.has_permission("Flow Definition", "read", doc=flow_id):
		return "You do not have permission to run that flow. Ask an admin for access."
	return None


def exec_flow_call(flow_run, node: dict, config: dict, settings: dict, context) -> dict:
	from huf.ai.flow import engine
	from huf.ai.flow.testrun import gate

	waiting = park.is_reentry(flow_run, node)
	if waiting:
		engine._transition_run(flow_run, {"waiting": None}, from_statuses=("Running",))
		woke = waiting.get("woke") or {}
		# woken by anything but the child itself (the sweeper fallback, "Continue now"): read the child's own row
		woke = woke.get("payload") if woke.get("reason") == "child_done" else _child_result((waiting.get("extra") or {}).get("child"))
		woke = woke or {}
		if woke.get("status") != "Success":
			return _failed(woke.get("error") or f"The flow this step ran did not finish ({woke.get('status') or 'unknown'}).")
		return {"status": "success", "output": woke.get("output")}

	if sorted(set(config) - KEYS):
		return _failed("Remove the settings this step does not use.")
	flow_id, mode = config.get("flow_id"), config.get("mode") or "fire_and_forget"
	if mode not in MODES:
		return _failed("Choose whether to start the flow and carry on, or wait for it to finish.")
	if error := _check_child(flow_run, flow_id):
		return _failed(error)
	payload = context.resolve(config.get("input") if config.get("input") is not None else {})
	if not isinstance(payload, dict):
		return _failed("The input for the other flow must be a set of named values.")

	if gate.is_test_run(flow_run):  # a test never starts another run
		return {"status": "success", "output": {"flow_id": flow_id, "run": None, "note": "Test run: the other flow was not started."}}

	child = engine.create_flow_run(flow_id=flow_id, payload=payload, trigger_type="Manual", ignore_permissions=True)
	child.db_set({"parent_run": flow_run.name, "parent_node": node.get("id")})

	if mode == "fire_and_forget":
		frappe.enqueue("huf.ai.flow.engine.run_flow", queue="default", flow_run_name=child.name)
		return {"status": "success", "output": {"flow_id": flow_id, "run": child.name}}

	engine._persist_context(flow_run, context, settings)
	outcome = park.park_run(flow_run, node, ParkRequest(reason="child", resume_at=None, extra={"child": child.name}))
	# only now may the child run: it can finish (and wake this run) at any moment
	frappe.enqueue("huf.ai.flow.engine.run_flow", queue="default", flow_run_name=child.name)
	return outcome


def _child_output(child_run):
	"""What the child produced: the value of its first ``output`` step that ran."""
	from huf.ai.flow.engine import PinnedVersion, load_context

	try:
		ctx = load_context(frappe.db.get_value("Agent Flow Run", child_run.name, "context_json"))
		graph = PinnedVersion.from_json(frappe.db.get_value("Agent Flow Run", child_run.name, "pinned_definition")).graph
		for n in graph.get("nodes", []):
			if n.get("type") == "output" and n.get("id") in ctx.node_outputs:
				return ctx.node_outputs[n["id"]]
	except Exception:
		pass
	return None


def _child_result(child_name: str | None) -> dict:
	row = frappe.db.get_value("Agent Flow Run", child_name, ["name", "status", "last_error"], as_dict=True) if child_name else None
	if not row:
		return {"status": None}
	return {"status": row.status, "error": row.last_error, "output": _child_output(row) if row.status == "Success" else None}


def on_child_finished(child_run, status: str, error: str | None = None) -> None:
	"""Called by the engine when a run reaches Success / Failed / Cancelled: wake the parent that waits for it."""
	parent = getattr(child_run, "parent_run", None) or frappe.db.get_value("Agent Flow Run", child_run.name, "parent_run")
	if not parent:
		return
	try:
		row = frappe.db.get_value("Agent Flow Run", parent, ["status", "waiting"], as_dict=True)
		if not row or row.status != park.WAIT_STATUS:
			return
		w = park._waiting(frappe._dict(waiting=row.waiting))
		if w.get("reason") != "child" or (w.get("extra") or {}).get("child") != child_run.name:
			return  # fire-and-forget, or the parent has moved on
		payload = {"status": status, "error": error, "output": _child_output(child_run) if status == "Success" else None}
		try:
			woken = park.wake_run(parent, "child_done", payload)
		except frappe.ValidationError:  # output too large to carry
			payload["output"] = None
			payload["error"] = payload["error"] or "The other flow's result is too large to pass back."
			woken = park.wake_run(parent, "child_done", payload)
		if not woken:
			# the parent's worker still holds its run lock (a quick child can finish before the parent's worker lets
			# go): leave the wake to the minute sweeper, which re-reads the child's result on re-entry
			from huf.ai.flow.engine import _transition_run

			_transition_run(SimpleNamespace(name=parent), {"resume_at": datetime.now(timezone.utc).replace(tzinfo=None)}, from_statuses=(park.WAIT_STATUS,))
	except Exception:
		frappe.log_error(title="Flow sub-flow completion hook")


def cancel_waited_child(flow_run, by: str) -> None:
	"""When a parent is cancelled while it waits for its child, cancel that child."""
	child = (park._waiting(flow_run).get("extra") or {}).get("child") if park._waiting(flow_run).get("reason") == "child" else None
	if not child or not frappe.db.exists("Agent Flow Run", child):
		return
	try:
		park.cancel_run(child, by)
	except Exception:
		frappe.log_error(title="Flow sub-flow cancel cascade")
