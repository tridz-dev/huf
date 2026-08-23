# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Fallback protocol: a failing Procedure degrades to normal agentic execution (T-32, I9).

This module is the ONLY place that turns a :class:`~huf.ai.graph.procedure_runtime.
ProcedureOutcome` into what the Agent actually sees. It never re-runs anything, never
retries, and never touches ``frappe`` -- it is a pure function of the outcome the runtime
already produced (mirrors the frappe-light pattern of ``huf.ai.output_budget`` and the
frappe-free core of ``huf.ai.graph.procedure_runtime.execute_procedure``).

Two failure classes, kept sharply, structurally distinct (T-32's whole point):

  NOT APPLICABLE -- ``contract.applies_when`` evaluated false BEFORE any node ran.
  :func:`execute_procedure` returns ``ProcedureOutcome.NOT_APPLICABLE`` in that case with
  an empty ``node_visits`` list and no tool invocations -- by construction, nothing ran.
  :func:`build_not_applicable_fallback` reflects that: its payload has NO
  ``completed_steps`` / ``failed_step`` / ``committed_writes`` / ``pending_writes`` /
  ``intermediate_outputs`` / ``safe_recovery_actions`` keys at all -- their mere presence
  would suggest partial execution happened. The Agent is meant to see "this didn't apply,
  proceed as if the Procedure were never bound" and nothing else.

  FAILED MID-RUN -- one or more nodes ran, and the run may have committed writes.
  :func:`build_mid_run_fallback` produces the full GOAL.md ss2.4 shape: procedure, version,
  run, completed_steps, failed_step, committed_writes, pending_writes,
  intermediate_outputs, error, safe_recovery_actions, available_atomic_tools.

Conflating the two is exactly how a retry duplicates a write (T-32 warning): a caller
that always assumes "there might be partial writes" would tell the Agent to go re-verify
state for a Procedure that in fact never touched anything, wasting a turn; a caller that
always assumes "nothing happened" would let the Agent retry a Procedure that already
committed a write, duplicating it. The two builders below are not interchangeable and
:func:`build_fallback` picks between them based on ``outcome.status`` alone -- never on a
heuristic guess.

Budgets (I7): :func:`build_mid_run_fallback` always routes ``intermediate_outputs``
through ``huf.ai.output_budget.enforce_output_budget`` with a ``spill`` callback that
never raises (this module must never fail the Agent, I9) and never returns the raw
payload unbounded -- a breach is dropped to a small marker, not persisted anywhere (no
``Agent Context Artifact`` integration is in scope for this task; that is a real spill
sink for a future task, not this one).
"""

from __future__ import annotations

from dataclasses import dataclass

from huf.ai.graph.permissions import (
	ToolClassifier,
	default_tool_classifier,
	iter_reachable_nodes,
	static_tool_closure,
)
from huf.ai.graph.procedure_runtime import ProcedureOutcome
from huf.ai.output_budget import OutputBudget, enforce_output_budget

__all__ = [
	"PROCEDURE_NOT_APPLICABLE",
	"PROCEDURE_FAILED_MID_RUN",
	"FallbackClass",
	"build_fallback",
	"build_not_applicable_fallback",
	"build_mid_run_fallback",
	"classify_write_tool",
]

PROCEDURE_NOT_APPLICABLE = "PROCEDURE_NOT_APPLICABLE"
PROCEDURE_FAILED_MID_RUN = "PROCEDURE_FAILED_MID_RUN"

# Matches huf.ai.graph.permissions._WRITE_PTYPES (not imported directly -- that name is
# private to that module; this is the same mutating-ptype set, kept here so this module's
# write/read classification does not depend on a private symbol).
_WRITE_PTYPES = {"write", "create", "delete", "submit", "cancel"}


class FallbackClass:
	"""The two failure classes this module ever produces. Never a third."""

	NOT_APPLICABLE = PROCEDURE_NOT_APPLICABLE
	FAILED_MID_RUN = PROCEDURE_FAILED_MID_RUN


def classify_write_tool(tool_id: str, classify_tool: ToolClassifier = default_tool_classifier) -> bool:
	"""True when ``tool_id`` is a mutating tool, per ``classify_tool``.

	Fails closed on an unclassifiable tool (classifier raises, or returns a ``ptype`` this
	module doesn't recognise): treated as a write, never assumed safe to retry blindly.
	Callers in tests inject a hand-written ``classify_tool`` fake; ``run_agent_procedure_run``
	callers should pass ``huf.ai.graph.permissions.default_tool_classifier`` (the real,
	frappe-backed one), never re-implement the read/write split here.
	"""
	try:
		perm = classify_tool(tool_id)
	except Exception:  # noqa: BLE001 -- an unclassifiable tool is a write, fail closed
		return True
	return bool(perm.ptype in _WRITE_PTYPES)


def build_not_applicable_fallback(*, procedure_id: str, version: str, run: str | None = None) -> dict:
	"""The NOT-APPLICABLE payload: clean, pre-execution, provably zero side effects.

	Deliberately does NOT carry ``completed_steps`` / ``failed_step`` / ``committed_writes``
	/ ``pending_writes`` / ``intermediate_outputs`` / ``error`` / ``safe_recovery_actions`` /
	``available_atomic_tools`` keys -- their absence IS the proof this is the clean-rejection
	shape, not the partial-failure one. A caller that reads this dict and treats it as if it
	were a mid-run failure will find nothing pointing at partial state, because there is
	none: :func:`~huf.ai.graph.procedure_runtime.execute_procedure` returns
	``NOT_APPLICABLE`` strictly before entering the node loop (see its own docstring/code),
	so no node ever ran, no tool was ever invoked, no ``Agent Tool Call`` record and no
	document write can exist for this run.
	"""
	return {
		"status": PROCEDURE_NOT_APPLICABLE,
		"procedure": procedure_id,
		"version": version,
		"run": run,
		"note": (
			"applies_when evaluated false before any node executed: zero side effects occurred. "
			"The Agent should proceed with normal agentic execution as if this Procedure had "
			"never been bound for this request -- do not retry it, nothing needs undoing."
		),
	}


def _completed_and_failed(outcome: ProcedureOutcome) -> tuple[list[dict], str | None]:
	"""Split ``outcome.node_visits`` into completed steps and the failed step id.

	``node_visits`` records every node visited in order, including the one that failed
	(``_VisitRecorder.node_end`` runs for both success and failure outcomes -- see
	``procedure_runtime.py``). ``outcome.node_id`` names the node the terminal result is
	attached to; when it matches the *last* visit, that visit is the failure and is
	excluded from ``completed_steps``. If ``outcome.node_id`` is unset (a resource-limit
	breach can fire before any per-node outcome is recorded) all visits are completed and
	there is no known failed step id beyond "resource limit, no single node".
	"""
	visits = list(outcome.node_visits)
	failed_step = outcome.node_id
	if visits and failed_step is not None and visits[-1][0] == failed_step:
		completed = visits[:-1]
	else:
		completed = visits
	completed_steps = [{"node_id": nid, "node_type": ntype} for nid, ntype in completed]
	return completed_steps, failed_step


def _failed_node_type(outcome: ProcedureOutcome) -> str | None:
	"""``outcome.node_type`` is authoritative -- see its field docstring in
	procedure_runtime.py: it is set even when the failing node never reached ``node_end``
	(a raised ``ProcedureLimitExceeded``), which ``node_visits`` alone cannot answer.
	"""
	return outcome.node_type


def _committed_and_pending_writes(
	*, outcome: ProcedureOutcome, graph: dict, classify_tool: ToolClassifier
) -> tuple[list[dict], list[dict]]:
	"""Split write-classified activity into what already happened vs. what didn't.

	``committed_writes`` -- every *attempted* write tool.call in
	``outcome.tool_invocations``, whether it reported success or not: a write tool that
	raised or returned ``success=False`` may still have partially committed (the runtime
	has no transactional guarantee across a tool boundary), so this module never assumes
	a failed write is a no-op -- that is exactly the retry-duplicates-a-write trap T-32
	warns about. Each entry keeps ``success`` so the Agent can tell "definitely
	committed" from "attempted, outcome unknown" without this module guessing for it.

	``pending_writes`` -- write-classified ``tool.call`` nodes declared anywhere in the
	graph (via ``huf.ai.graph.permissions.iter_reachable_nodes``, so foreach/parallel
	nested nodes are included) that were never attempted at all. These are safe to skip
	entirely (never attempted, nothing to undo) or to run explicitly via an atomic tool
	call -- never to reach by blindly re-running the Procedure from the top.
	"""
	attempted_node_ids = {inv["node_id"] for inv in outcome.tool_invocations}

	committed_writes = [
		{
			"node_id": inv["node_id"],
			"tool_id": inv["tool_id"],
			"args": inv["args"],
			"success": inv["success"],
		}
		for inv in outcome.tool_invocations
		if classify_write_tool(inv["tool_id"], classify_tool)
	]

	pending_writes: list[dict] = []
	for node in iter_reachable_nodes(graph):
		if node.get("type") != "tool.call":
			continue
		if node.get("id") in attempted_node_ids:
			continue
		tool_id = (node.get("config") or {}).get("tool_id")
		if not tool_id or not classify_write_tool(tool_id, classify_tool):
			continue
		pending_writes.append({"node_id": node["id"], "tool_id": tool_id})

	return committed_writes, pending_writes


_NEVER_RAISE_SPILL_NOTE = (
	"intermediate outputs exceeded the output budget and were omitted from this fallback "
	"payload (I7) -- no dataset_handle is available; the run's own Agent Procedure Step "
	"records carry the full per-node output_json if it is genuinely needed."
)


def _never_raise_spill(_rows: list, _meta: dict) -> dict:
	"""``spill`` callback for the fallback payload's own budget check.

	This module must never raise on a breach (I9: a failing Procedure -- including one
	whose OWN fallback payload is too big -- never fails the Agent). Unlike
	``ProcedureRuntime``'s ``output`` node handler (which legitimately fails closed with
	an exception because a graph author is expected to keep output nodes bounded by
	construction), a fallback payload is diagnostic, not a Procedure's declared result: if
	it doesn't fit, the answer is "drop it and say so," never "propagate an exception out
	of the very code path whose job is to keep the Agent running."
	"""
	return {"spilled": True, "note": _NEVER_RAISE_SPILL_NOTE}


def _bounded_intermediate_outputs(outcome: ProcedureOutcome, *, budget: OutputBudget) -> dict:
	"""Bound ``outcome.node_outputs`` through the shared output-budget serialiser (I7).

	``enforce_output_budget`` is built for row-shaped lists; a node's output is often a
	single dict or scalar, not a list, so each node output is wrapped as one "row"
	``{"node_id": ..., "node_type": ..., "output": ...}`` -- this is exactly the row shape
	the budget module already knows how to bound/preview/spill, reused rather than
	re-implemented (module docstring: "Use huf.ai.output_budget.py").
	"""
	node_types = dict(outcome.node_visits)
	rows = [
		{"node_id": node_id, "node_type": node_types.get(node_id), "output": output}
		for node_id, output in outcome.node_outputs.items()
	]
	bounded = enforce_output_budget(
		rows,
		budget=budget,
		summary=f"{len(rows)} node output(s) produced before the run stopped.",
		spill=_never_raise_spill,
	)
	return bounded.to_dict()


def build_mid_run_fallback(
	*,
	procedure_id: str,
	version: str,
	run: str | None,
	graph: dict,
	outcome: ProcedureOutcome,
	classify_tool: ToolClassifier = default_tool_classifier,
	budget: OutputBudget | None = None,
) -> dict:
	"""The FAILED-MID-RUN payload: GOAL.md ss2.4's structured partial state, bounded (I7).

	``outcome`` must be a ``ProcedureOutcome`` with ``status == ProcedureOutcome.FAILED`` --
	call :func:`build_not_applicable_fallback` instead for ``NOT_APPLICABLE``, and this
	function never handles ``SUCCESS`` at all (there is no fallback for a run that didn't
	fail). ``graph`` is the pinned graph the run executed (``run.pinned_definition_json``
	on a real ``Agent Procedure Run``, or the same dict a caller built for
	:func:`~huf.ai.graph.procedure_runtime.execute_procedure`) -- needed to compute
	``pending_writes`` and ``available_atomic_tools`` via static analysis
	(``huf.ai.graph.permissions``), which ``outcome`` alone does not carry.
	"""
	if outcome.status != ProcedureOutcome.FAILED:
		raise ValueError(
			f"build_mid_run_fallback requires a FAILED outcome, got {outcome.status!r} -- "
			"use build_not_applicable_fallback for NOT_APPLICABLE, there is no fallback for SUCCESS"
		)

	budget = budget or OutputBudget()

	completed_steps, failed_step = _completed_and_failed(outcome)
	failed_node_type = _failed_node_type(outcome)
	committed_writes, pending_writes = _committed_and_pending_writes(
		outcome=outcome, graph=graph, classify_tool=classify_tool
	)
	# Note: a write tool.call that failed still counts as a committed_writes entry (see
	# _committed_and_pending_writes), so this is exactly "did the node that failed happen
	# to be a write-classified tool.call".
	failed_tool_is_write = any(w["node_id"] == failed_step for w in committed_writes)

	return {
		"status": PROCEDURE_FAILED_MID_RUN,
		"procedure": procedure_id,
		"version": version,
		"run": run,
		"completed_steps": completed_steps,
		"failed_step": failed_step,
		"committed_writes": committed_writes,
		"pending_writes": pending_writes,
		"intermediate_outputs": _bounded_intermediate_outputs(outcome, budget=budget),
		"error": outcome.error,
		"safe_recovery_actions": _safe_recovery_actions(failed_node_type, failed_tool_is_write),
		"available_atomic_tools": sorted(static_tool_closure(graph)),
	}


def _safe_recovery_actions(failed_node_type: str | None, failed_tool_is_write: bool) -> list[str]:
	"""Actionable, node-type-specific guidance -- never a generic "an error occurred".

	Kept short and declarative (I7 applies here too: this is model context, not a log
	dump) -- a handful of imperative sentences, not the failure's stack trace.
	"""
	if failed_node_type == "tool.call" and failed_tool_is_write:
		return [
			"Do not blindly retry: the failed tool.call may have partially committed its write.",
			"Verify the target record's current state with a read before retrying or choosing a "
			"different atomic action.",
			"If the write did not commit, prefer an atomic tool call over restarting the Procedure.",
		]
	if failed_node_type == "tool.call":
		return [
			"Safe to retry: the failed node was a read-only tool call with no side effects.",
			"Re-run the same lookup via an atomic tool call, or proceed using completed_steps.",
		]
	if failed_node_type == "validate":
		return [
			"A validate node's assertion failed before further writes -- treat this as a hard stop "
			"on the plan that led here, not a transient error.",
			"Re-check the inputs that fed the failed assertion before choosing a different approach.",
		]
	if failed_node_type == "condition":
		return [
			"A condition node could not evaluate -- inspect the referenced fields for missing or "
			"malformed data rather than retrying the same expression unchanged.",
		]
	if failed_node_type == "foreach":
		return [
			"A foreach batch failed partway; some items may already be processed -- consult "
			"completed_steps and intermediate_outputs before re-processing anything.",
			"Prefer processing remaining items individually via atomic tool calls over re-running "
			"the whole batch.",
		]
	if failed_node_type == "transform":
		return [
			"A transform step failed on already-fetched, in-memory data -- no write could have "
			"happened here; safe to retry once the upstream data or expression is fixed.",
		]
	if failed_node_type == "output":
		return [
			"The Procedure's own output failed to assemble (e.g. an output budget breach) -- any "
			"prior writes already committed; do not re-run those steps, re-derive the summary via "
			"atomic tool calls instead.",
		]
	return [
		"Procedure failed mid-run; review completed_steps and committed_writes before retrying "
		"any part of it.",
	]


@dataclass(frozen=True)
class BoundResult:
	"""Convenience wrapper distinguishing which builder ran, for callers that want to
	branch on failure class without re-inspecting the payload's own ``status`` string.
	"""

	fallback_class: str
	payload: dict


def build_fallback(
	*,
	procedure_id: str,
	version: str,
	run: str | None,
	graph: dict,
	outcome: ProcedureOutcome,
	classify_tool: ToolClassifier = default_tool_classifier,
	budget: OutputBudget | None = None,
) -> BoundResult:
	"""The single entry point: dispatch on ``outcome.status`` alone (I9).

	This is the function ``huf.ai.graph.procedure_binding`` (T-31, ``fallback_enabled``)
	and ``huf.ai.graph.procedure_runtime.run_agent_procedure_run`` should call instead of
	inlining a status check -- keeping the not-applicable/mid-run branch in exactly one
	place is what keeps the two classes from drifting back together over time.

	Never called for ``ProcedureOutcome.SUCCESS`` -- a successful run has no fallback, it
	has an output; callers must not route a success through here.
	"""
	if outcome.status == ProcedureOutcome.NOT_APPLICABLE:
		payload = build_not_applicable_fallback(procedure_id=procedure_id, version=version, run=run)
		return BoundResult(fallback_class=PROCEDURE_NOT_APPLICABLE, payload=payload)

	if outcome.status == ProcedureOutcome.FAILED:
		payload = build_mid_run_fallback(
			procedure_id=procedure_id,
			version=version,
			run=run,
			graph=graph,
			outcome=outcome,
			classify_tool=classify_tool,
			budget=budget,
		)
		return BoundResult(fallback_class=PROCEDURE_FAILED_MID_RUN, payload=payload)

	raise ValueError(
		f"build_fallback called with status={outcome.status!r} -- only NOT_APPLICABLE and FAILED "
		"have a fallback; a SUCCESS outcome should never reach this function"
	)
