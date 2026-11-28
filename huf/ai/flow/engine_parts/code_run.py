"""``code.run`` node execution: run Python in the sandbox, park the run until it finishes.

Moved out of ``huf.ai.flow.engine`` unchanged; ``engine`` re-exports these names. Engine internals are reached
through a function-level ``from huf.ai.flow import engine`` to avoid an import cycle.
"""

import json

import frappe
from frappe.utils import now_datetime

from huf.ai.graph.error_copy import plain_error
from huf.ai.graph.executor import Outcome, PauseRequest
from huf.ai.transaction import commit_if_background


def _exec_code_run(flow_run, node: dict, config: dict, settings: dict):
	"""``code.run``: config ``code``, ``profile``, ``inputs`` (name -> value / ``$from``), ``timeout_s``.

	The code and profile are read from ``config`` of the node in the run's PINNED definition (the
	published flow); ``inputs`` are resolved to plain data and reach the code as the ``inputs`` variable.
	The code runs in an RQ worker (or waits behind an approval), so this node PAUSES the run in
	``Waiting Code``; :func:`resume_code_node` moves it on, and the step is entered once more to turn
	the finished audit row into its output (``stdout``, ``result``, ``exit_status``, ``truncated``) or a
	readable failure that ``on_error`` routes. Output: see :func:`huf.ai.flow.code_node.output_from_call`.
	"""
	from huf.ai.flow import code_node, engine
	from huf.ai.tools import code_execution

	node_id = node.get("id")
	ctx = engine._context_of(flow_run, settings)
	waiting = engine._load_waiting(flow_run)

	if waiting.get("type") == "code" and waiting.get("node_id") == node_id:
		if flow_run.status == "Waiting Code":
			return Outcome.paused(PauseRequest(kind="code", status_label="Waiting Code"))
		return _finish_code_step(flow_run, waiting)

	problem = code_node.run_problem(flow_run, config)
	if problem:
		return {"status": "failed", "error": problem}
	done = code_node.runs_so_far(flow_run.name)
	if done >= code_node.MAX_CODE_RUNS_PER_FLOW_RUN:
		return {
			"status": "failed",
			"error": f"This run already ran {code_node.MAX_CODE_RUNS_PER_FLOW_RUN} code steps, which is the most one run may start. Use fewer code steps or a smaller loop.",
		}
	try:
		inputs = json.loads(json.dumps(ctx.resolve(config.get("inputs") or {}), default=str))
	except (TypeError, ValueError) as exc:
		return {"status": "failed", "error": "The data given to this code step could not be read. Check the values you pass in."}

	try:
		dispatched = code_execution.run_flow_code(
			flow_run, node, config.get("code"), config.get("profile"), inputs, timeout_s=config.get("timeout_s")
		)
	except (frappe.PermissionError, frappe.ValidationError) as exc:
		return {"status": "failed", "error": plain_error(str(exc)) or "This code step was not allowed to run."}

	call_name = dispatched["agent_tool_call"]
	approval = dispatched.get("approval")
	snapshot = _json_dict(frappe.db.get_value("Agent Tool Call", call_name, "execution_profile_snapshot"))
	wall = int((snapshot.get("limits") or {}).get("max_wall_time_s") or code_node.DEFAULT_TIMEOUT_S)
	waiting_data = {
		"type": "code",
		"node_id": node_id,
		"agent_tool_call": call_name,
		"agent_run": dispatched.get("agent_run"),
		"approval": approval,
		"timeout_at": code_node.deadline_iso(wall, dispatched.get("expires_on") if approval else None),
		"message": "Waiting for an approval" if approval else "Running in the sandbox",
	}

	status = frappe.db.get_value("Agent Tool Call", call_name, "status")
	if status in ("Completed", "Failed"):
		# It already ran (in-process execution, as in tests): no need to park.
		return _finish_code_step(flow_run, waiting_data)

	engine._persist_context(flow_run, ctx, settings)
	if not engine._transition_run(
		flow_run,
		{"status": "Waiting Code", "waiting": json.dumps(waiting_data)},
		not_from_statuses=engine.TERMINAL_STATUSES,
	):
		return {"status": "failed", "error": "The run had already ended before this code step could start."}
	commit_if_background()
	return Outcome.paused(PauseRequest(kind="code", status_label="Waiting Code"))


def _json_dict(value) -> dict:
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (TypeError, ValueError):
			return {}
	return value if isinstance(value, dict) else {}


def _finish_code_step(flow_run, waiting: dict):
	"""Turn the finished audit row of a code step into the node's outcome, and close its Agent Run."""
	from huf.ai.flow import code_node

	call = frappe.get_doc("Agent Tool Call", waiting.get("agent_tool_call"))
	ok, output, error = code_node.output_from_call(call)
	if getattr(flow_run, "waiting", None):
		flow_run.db_set("waiting", None)
		flow_run.waiting = None
	run_name = waiting.get("agent_run")
	if run_name and frappe.db.exists("Agent Run", run_name):
		frappe.db.set_value(
			"Agent Run",
			run_name,
			{
				"status": "Success" if ok else "Failed",
				"response": json.dumps(output, default=str),
				"error_message": error if not ok else None,
				"end_time": now_datetime(),
			},
		)
		flow_run.db_set("last_agent_run", run_name)
	commit_if_background()
	if ok:
		return {"status": "success", "result": output, "output": output}
	return {"status": "failed", "error": error, "output": output}


def resume_code_node(flow_run_name: str) -> bool:
	"""Move a run out of ``Waiting Code`` once its step's audit row is final (completed, failed, rejected, expired).

	Takes the run lock (briefly retried: the worker may finish while the run that parked is still
	releasing it) and leaves the waiting state with one conditional UPDATE, so a worker nudge and the
	sweeper cannot both advance the run. The step itself is entered again by :func:`run_flow` and
	reads the outcome from the audit row (:func:`_finish_code_step`). Returns True when it resumed.
	"""
	import time

	from huf.ai.flow import engine

	if frappe.db.get_value("Agent Flow Run", flow_run_name, "status") != "Waiting Code":
		return False  # nothing to continue (already moved on, or the step ran in-process)
	for _attempt in range(50):
		if engine._acquire_run_lock(flow_run_name):
			break
		time.sleep(0.2)
	else:
		return False
	try:
		flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
		if flow_run.status != "Waiting Code":
			return False
		waiting = engine._load_waiting(flow_run)
		status = frappe.db.get_value("Agent Tool Call", waiting.get("agent_tool_call"), "status")
		if status not in ("Completed", "Failed"):
			return False
		if not engine._transition_run(flow_run, {"status": "Running"}, from_statuses=("Waiting Code",)):
			return False
		frappe.db.commit()  # nosemgrep
	finally:
		engine._release_run_lock(flow_run_name)
	engine.run_flow(flow_run_name)
	return True


def fail_waiting_code_run(flow_run_name: str, reason: str) -> bool:
	"""Fail a run parked on a code step whose record is gone (operator / sweeper path)."""
	from huf.ai.flow import engine

	flow_run = frappe.get_doc("Agent Flow Run", flow_run_name)
	if flow_run.status != "Waiting Code":
		return False
	return engine._fail_flow_run(flow_run, reason)
