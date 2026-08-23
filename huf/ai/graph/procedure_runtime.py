# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""ProcedureRuntime -- executes a Procedure-profile IR graph sequentially (T-23).

This module is the T-23 seam: it drives ``huf.ai.graph.executor.GraphExecutor`` (T-22)
over a pinned Procedure graph, delegating every atomic operation to the module that
already owns it:

	tool.call  -> huf.ai.tool_invocation.invoke_tool_sync (T-10) -- permission checks and
	              Agent Tool Call telemetry live there; this module never re-implements
	              either (I5).
	transform  -> huf.ai.graph.transforms.run_transform (T-12)
	condition  -> huf.ai.graph.expressions.evaluate_bool (T-13)
	validate   -> huf.ai.graph.expressions.evaluate_bool, fail closed on any false assertion
	output     -> huf.ai.output_budget.enforce_output_budget (T-11), fail closed (I7)
	foreach    -> bounded, its own max_iterations budget, never touches the run's hop budget
	parallel   -> PARSES AND VALIDATES here but EXECUTES SEQUENTIALLY. Real bounded
	              concurrency is task T-30; this module runs each branch one after another,
	              in declaration order, and says so at every call site below.

Two-layer split, deliberately:

* :func:`execute_procedure` is the frappe-free core. It takes an already-pinned
  :class:`~huf.ai.graph.executor.PinnedVersion`, an input payload, and a ``tool_invoker``
  callable injected by the caller. Nothing in this function imports ``frappe`` or touches
  a database -- it is unit-testable with a hand-written fake invoker, standalone, with no
  bench (mirrors ``huf.ai.graph.transforms`` / ``huf.ai.graph.expressions``).
* :func:`run_agent_procedure_run` is the frappe-facing entry point. It loads an
  ``Agent Procedure Run`` document, takes the run lock (``huf.ai.procedure_lock``, GT-08),
  builds the real ``tool_invoker`` (I1 authorization via ``huf.ai.graph.permissions`` +
  T-10 telemetry), records one ``Agent Procedure Step`` row per node visited, and updates
  the run's status/output. It is the only place in this module that touches Frappe.

NO LLM ANYWHERE IN THIS PATH (I4). There is no call to ``agent.run``, no ``router.llm``,
no dynamic dispatch of any kind -- every node type this module executes is drawn from the
Procedure profile's closed node set (spec/graph-ir.md section 1), which does not include
``agent.run`` / ``router.llm`` / ``human.approval`` / any ``trigger.*`` node. A Procedure
graph is structurally incapable of containing one (I4 is enforced by the schema, T-24's
validator, and this module simply has no handler registered for any Flow-only type -- an
``Unknown node type`` failure, not a silent skip, if one ever reached here).

Synchronous fast path (GOAL.md section 10): this module never routes a run through RQ or
Flow Run persistence. ``execute_procedure`` runs to completion (or a fail-closed error) in
one call, in memory, using ``InMemoryStateStore`` -- the default T-22 gives any caller that
doesn't opt into a persisting store.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from huf.ai.graph.executor import (
	ExecutionListener,
	ExecutionPolicy,
	ExecutionResult,
	ExecutionState,
	GraphContext,
	GraphExecutor,
	GraphProgram,
	NodeSpec,
	Outcome,
	PinnedVersion,
	Router,
	RoutingError,
	RoutingMode,
)
from huf.ai.graph.expressions import evaluate_bool, parse_expression
from huf.ai.graph.scheduler import (
	DEFAULT_MAX_GRAPH_CONCURRENCY,
	DEFAULT_MAX_TOOL_CONCURRENCY,
	BranchResult,
	ParallelLimitExceeded,
	run_parallel_branches,
)
from huf.ai.graph.transforms import Limits as TransformLimits
from huf.ai.graph.transforms import run_transform
from huf.ai.output_budget import OutputBudget, OutputBudgetExceeded, enforce_output_budget

__all__ = [
	"PROCEDURE_NODE_TYPES",
	"ProcedureExecutionError",
	"ProcedureLimitExceeded",
	"ProcedureOutcome",
	"ToolInvoker",
	"ToolInvocation",
	"build_program",
	"build_subprogram",
	"execute_procedure",
	"run_agent_procedure_run",
]

# The complete Procedure-profile node set (spec/graph-ir.md section 1). Deliberately does
# NOT include agent.run / router.llm / human.approval / trigger.* -- those are Flow-only
# (I4). A graph containing one of them fails T-24's static validator before it ever reaches
# this module; there is also no handler registered for any of them here, so even a graph
# that slipped past validation would fail with "Unknown node type", never silently execute.
PROCEDURE_NODE_TYPES = ("tool.call", "transform", "condition", "foreach", "parallel", "validate", "output")


class ProcedureExecutionError(Exception):
	"""A Procedure run failed. Carries the reason; never raised for an ordinary
	node failure (those become a failed :class:`ExecutionResult` instead) -- only for
	conditions the executor itself cannot recover from: applies_when short-circuit is not
	one of these (that is a normal, non-error outcome), but a resource-limit breach with no
	safe partial result is.
	"""


class ProcedureLimitExceeded(ProcedureExecutionError):
	"""A contract.limits ceiling was breached. Always fail closed (I7) -- never silently
	truncate or continue past the limit that triggered this.
	"""


@dataclass
class ToolInvocation:
	"""What a tool.call node asks its invoker to do, and what it got back.

	Kept as a plain dataclass (not an ad hoc dict) so ``tool_invoker`` implementations --
	the real one in :func:`run_agent_procedure_run` and hand-written fakes in tests -- share
	one explicit contract.
	"""

	tool_id: str
	args: dict
	success: bool = False
	result: Any = None
	error: str | None = None


ToolInvoker = Callable[[str, dict], ToolInvocation]
"""``(tool_id, args) -> ToolInvocation``. The only way a tool.call node reaches outside
this module. Authorization (I1) and telemetry (I5) are the invoker's responsibility --
:func:`execute_procedure` itself never calls ``frappe`` and never decides permission.
"""


@dataclass
class ProcedureOutcome:
	"""Terminal result of :func:`execute_procedure`."""

	status: str  # "success" | "failed" | "not_applicable"
	output: Any = None
	error: str | None = None
	node_id: str | None = None
	hop_count: int = 0
	node_visits: list[tuple[str, str]] = field(default_factory=list)
	"""``(node_id, node_type)`` pairs, in visit order -- including repeats from foreach
	iterations and parallel branches, so a caller can count "one atomic operation per
	Agent Tool Call" against this list.
	"""

	tool_call_count: int = 0

	tool_invocations: list[dict] = field(default_factory=list)
	"""One entry per ``tool.call`` node actually invoked (attempted), in order:
	``{"node_id", "tool_id", "args", "success", "result", "error"}``. This is the raw
	material :mod:`huf.ai.graph.fallback` (T-32) uses to tell a committed write from a
	pending one on a mid-run failure -- ``node_visits`` alone only has ``(id, type)`` and
	cannot answer "did this write actually go through". Never used to reconstruct
	authorization or telemetry (I1/I5 remain the tool_invoker's job); this is purely a
	record of what was asked and what came back.
	"""

	node_type: str | None = None
	"""Type of the node named by ``node_id``. Filled in even when that node never reached
	``node_end`` (a raised ``ProcedureLimitExceeded``/``RoutingError``) -- ``node_visits``
	alone cannot answer "what kind of node was this" in that case, so
	:mod:`huf.ai.graph.fallback` reads this field rather than re-deriving it.
	"""

	node_outputs: dict = field(default_factory=dict)
	"""``{node_id: output}`` for every node visited so far, success or fail -- a direct
	copy of ``GraphContext.node_outputs`` at the point the run stopped. Populated on every
	terminal status (including a raised ``ProcedureLimitExceeded``/``RoutingError``), so
	:mod:`huf.ai.graph.fallback` has the same partial state a mid-run failure leaves behind
	without re-deriving it from ``node_visits`` (which only has ids/types, not values).
	"""

	fallback: dict | None = None
	"""The :mod:`huf.ai.graph.fallback` payload for a non-SUCCESS terminal status, attached
	by :func:`run_agent_procedure_run` (never by the frappe-free
	:func:`execute_procedure`, which has no procedure/version identity to put in it).

	Deliberately a returned field rather than a new DocType column: the persisted halves
	of this payload already live in the ``Agent Procedure Run`` recovery fields
	(``completed_steps`` / ``failed_step`` / ``committed_writes`` / ``pending_writes`` /
	``intermediate_outputs`` / ``error`` / ``safe_recovery_actions``), and T-32 forbids a
	second, parallel set of state fields. ``None`` on SUCCESS, and on any failure whose
	payload could not be built -- a caller must branch on presence, never assume it.
	"""

	SUCCESS = "success"
	FAILED = "failed"
	NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# Program construction -- indexes a pinned graph (and any foreach/parallel
# nested body) into the executor's NodeSpec vocabulary.
# ---------------------------------------------------------------------------


def _routing_for(node_type: str) -> str:
	if node_type == "output":
		return RoutingMode.TERMINAL
	if node_type == "condition":
		return RoutingMode.SELF_ROUTED
	return RoutingMode.DEFAULT


def _default_route(node: NodeSpec, outcome: Outcome, context: GraphContext) -> str | None:
	"""The DEFAULT-routing resolver every :class:`GraphExecutor` in this module uses.

	``GraphExecutor.run`` does not itself inspect ``outcome.status`` -- with no
	``default_resolver`` it would follow a failed ``tool.call``/``transform``/``validate``
	node's ``next`` pointer exactly as if it had succeeded (the router's job is purely
	successor selection, not failure semantics). This resolver is what makes a failed node
	actually fail the run: on failure it routes to ``on_error`` if the node declares one,
	otherwise it raises :class:`RoutingError` -- which ``GraphExecutor.run`` already catches
	and turns into a proper ``FAILED`` :class:`ExecutionResult` (I7: fail closed, not a
	silently-continued run).
	"""
	if outcome.status == "failed":
		on_error = node.raw.get("on_error")
		if on_error:
			return on_error
		raise RoutingError(outcome.error or f"node '{node.id}' failed")
	return node.raw.get("next")


def _router_for(program: GraphProgram) -> Router:
	return Router(program, default_resolver=_default_route)


def _index_nodes(graph: Mapping[str, Any]) -> dict[str, dict]:
	return {n["id"]: n for n in graph.get("nodes", []) if isinstance(n, dict) and "id" in n}


def build_program(version: PinnedVersion) -> GraphProgram:
	"""Index the whole graph (main chain plus every foreach/parallel nested node) into a
	:class:`GraphProgram`, entry = the graph's own declared entry.
	"""
	raw_nodes = _index_nodes(version.graph)
	entry = version.graph.get("entry")
	if isinstance(entry, list):
		entry = entry[0] if entry else None
	return _build_program_for(version, raw_nodes, list(raw_nodes.keys()), entry)


def build_subprogram(version: PinnedVersion, node_ids: list[str]) -> GraphProgram:
	"""Index one self-contained chain -- a foreach ``body`` or a parallel branch -- as its
	own :class:`GraphProgram`, entry = ``node_ids[0]``. Per spec/graph-ir.md section 2, these
	nodes are chained by their own ``next`` among themselves and are not reachable from the
	main chain by any other path, so a sub-program built purely from ``node_ids`` (looked up
	in the same top-level ``nodes`` array) is a complete, correct chain.
	"""
	raw_nodes = _index_nodes(version.graph)
	entry = node_ids[0] if node_ids else None
	return _build_program_for(version, raw_nodes, node_ids, entry)


def _build_program_for(
	version: PinnedVersion, raw_nodes: dict[str, dict], node_ids: list[str], entry: str | None
) -> GraphProgram:
	specs: dict[str, NodeSpec] = {}
	for node_id in node_ids:
		raw = raw_nodes[node_id]
		node_type = raw.get("type")
		loop_body = None
		if node_type == "foreach":
			body = (raw.get("config") or {}).get("body") or []
			loop_body = body[0] if body else None
		specs[node_id] = NodeSpec(
			id=node_id,
			type=node_type,
			config=raw.get("config") or {},
			routing=_routing_for(node_type),
			raw=raw,
			loop_body=loop_body,
		)
	return GraphProgram(version=version, nodes=specs, entry=entry)


# ---------------------------------------------------------------------------
# Node visit recording -- an ExecutionListener that both the top-level run and
# every nested foreach/parallel sub-executor share, so "one visit per atomic
# operation" is counted across the whole run, not just its main chain.
# ---------------------------------------------------------------------------


class _VisitRecorder:
	"""Records every node visited, in order, plus an optional per-node-visit callback
	(used by :func:`run_agent_procedure_run` to write one ``Agent Procedure Step`` row per
	visit). Frappe-free -- ``on_visit`` is injected, never assumed.
	"""

	def __init__(self, on_visit: Callable[[NodeSpec, Outcome], None] | None = None):
		self.visits: list[tuple[str, str]] = []
		self.pairs: list[tuple[NodeSpec, Outcome]] = []
		"""``(NodeSpec, Outcome)`` per visit -- used by T-30 to replay a branch worker's
		visits, in canonical order, into the run's real recorder (see
		``huf.ai.graph.scheduler`` module docstring, "Threading model").
		"""
		self._on_visit = on_visit
		self._starts: dict[str, float] = {}
		self.last_started: tuple[str, str] | None = None
		"""``(node_id, node_type)`` of the most recent ``node_start`` -- distinct from
		``visits[-1]``: a handler that raises ``ProcedureLimitExceeded`` (e.g. an
		``output`` node's budget check) never reaches ``node_end``, so it never lands in
		``visits`` at all. :func:`execute_procedure`'s outer except clause uses this to
		attribute the failure to the node that was actually executing, not the previous
		one that already completed successfully.
		"""

	def node_start(self, node: NodeSpec) -> None:
		self._starts[node.id] = time.monotonic()
		self.last_started = (node.id, node.type)

	def node_end(self, node: NodeSpec, outcome: Outcome) -> None:
		self.visits.append((node.id, node.type))
		self.pairs.append((node, outcome))
		if self._on_visit is not None:
			self._on_visit(node, outcome)


# ---------------------------------------------------------------------------
# The core: frappe-free, synchronous, fail-closed.
# ---------------------------------------------------------------------------


class _Runner:
	"""Holds the per-run state a set of node handlers close over. Not part of the public
	API -- :func:`execute_procedure` is. Kept as a class only so the seven handlers can share
	counters/limits/the tool invoker without a dozen module-level globals.
	"""

	def __init__(
		self,
		version: PinnedVersion,
		*,
		tool_invoker: ToolInvoker,
		limits: Mapping[str, Any],
		recorder: _VisitRecorder,
		wall_clock_start: float,
	):
		self.version = version
		self.tool_invoker = tool_invoker
		self.limits = limits
		self.recorder = recorder
		self.wall_clock_start = wall_clock_start
		self.external_call_count = 0
		self.write_count = 0
		self.tool_call_count = 0
		self.tool_invocations: list[dict] = []

		# -- T-30 concurrency bounds -------------------------------------------------
		# One graph-wide semaphore for the whole run (shared by every parallel node,
		# including nested ones inside a branch running on a worker thread -- see
		# scheduler.py's module docstring, "Max graph concurrency").
		max_graph_concurrency = limits.get("max_graph_concurrency") or DEFAULT_MAX_GRAPH_CONCURRENCY
		self.graph_semaphore = threading.BoundedSemaphore(max_graph_concurrency)
		self.max_tool_concurrency = limits.get("max_tool_concurrency") or DEFAULT_MAX_TOOL_CONCURRENCY
		self._tool_semaphores: dict[str, threading.BoundedSemaphore] = {}
		self._tool_semaphores_lock = threading.Lock()
		# tool_call_count / external_call_count / write_count above are mutated from
		# whichever thread executes a tool.call node. A parallel branch's tool.call
		# handlers run one at a time within that branch's own worker thread, but two
		# branches can call _charge_external_call concurrently, so these counters need
		# their own lock -- a plain `+= 1` is not atomic in general.
		self._counters_lock = threading.Lock()

	def _tool_semaphore(self, tool_id: str) -> threading.BoundedSemaphore:
		"""Per-tool (and, absent a distinct connector concept in this codebase's tool
		metadata, per-connector -- see scheduler.py) concurrency cap. Lazily created,
		one semaphore per tool_id, shared by every thread that calls this tool.
		"""
		with self._tool_semaphores_lock:
			sem = self._tool_semaphores.get(tool_id)
			if sem is None:
				sem = threading.BoundedSemaphore(self.max_tool_concurrency)
				self._tool_semaphores[tool_id] = sem
			return sem

	# -- shared budgets, fail closed (I7) ---------------------------------

	def _check_wall_time(self) -> None:
		max_ms = self.limits.get("max_wall_time_ms")
		if not max_ms:
			return
		elapsed_ms = (time.monotonic() - self.wall_clock_start) * 1000
		if elapsed_ms > max_ms:
			raise ProcedureLimitExceeded(f"max_wall_time_ms exceeded ({elapsed_ms:.0f} > {max_ms})")

	def _charge_external_call(self) -> None:
		with self._counters_lock:
			self.external_call_count += 1
			count = self.external_call_count
		cap = self.limits.get("max_external_calls")
		if cap is not None and count > cap:
			raise ProcedureLimitExceeded(f"max_external_calls exceeded ({count} > {cap})")

	def _transform_limits(self) -> TransformLimits:
		kwargs: dict[str, int] = {}
		if self.limits.get("max_rows") is not None:
			kwargs["max_rows"] = self.limits["max_rows"]
		if self.limits.get("max_output_bytes") is not None:
			kwargs["max_output_bytes"] = self.limits["max_output_bytes"]
		return TransformLimits(**kwargs) if kwargs else TransformLimits()

	def _output_budget(self) -> OutputBudget:
		kwargs: dict[str, int] = {}
		if self.limits.get("max_rows") is not None:
			kwargs["max_rows"] = self.limits["max_rows"]
		if self.limits.get("max_output_bytes") is not None:
			kwargs["max_bytes"] = self.limits["max_output_bytes"]
		return OutputBudget(**kwargs) if kwargs else OutputBudget()

	def handlers(self) -> dict[str, Callable]:
		return {
			"tool.call": self._handle_tool_call,
			"transform": self._handle_transform,
			"condition": self._handle_condition,
			"foreach": self._handle_foreach,
			"parallel": self._handle_parallel,
			"validate": self._handle_validate,
			"output": self._handle_output,
		}

	def _sub_executor(
		self, node_ids: list[str], *, listener: ExecutionListener | None = None
	) -> tuple[GraphProgram, GraphExecutor]:
		program = build_subprogram(self.version, node_ids)
		# +2 headroom over the chain length: the chain itself is the hop budget for a
		# nested sub-program, distinct from and never charged against the run's own
		# max_hops (mirrors the executor's foreach/main-chain budget separation, F-3).
		policy = ExecutionPolicy(max_hops=len(node_ids) + 2)
		executor = GraphExecutor(
			program,
			self.handlers(),
			router=_router_for(program),
			policy=policy,
			listener=listener or self.recorder,
		)
		return program, executor

	# -- node handlers ------------------------------------------------------

	def _handle_tool_call(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		self._check_wall_time()
		resolved = context.resolve(node.config)
		tool_id = resolved.get("tool_id")
		args = resolved.get("input") or {}
		if not tool_id:
			return Outcome.failed(f"tool.call node '{node.id}' has no tool_id after resolution")

		self._charge_external_call()
		with self._counters_lock:
			self.tool_call_count += 1

		tool_sem = self._tool_semaphore(tool_id)
		tool_sem.acquire()
		try:
			invocation = self.tool_invoker(tool_id, args)
		except ProcedureLimitExceeded:
			raise
		except Exception as exc:  # noqa: BLE001 -- a denied/raising invoker fails this node, not the process
			self.tool_invocations.append(
				{
					"node_id": node.id,
					"tool_id": tool_id,
					"args": args,
					"success": False,
					"result": None,
					"error": f"tool.call '{tool_id}' raised: {exc}",
				}
			)
			return Outcome.failed(f"tool.call '{tool_id}' raised: {exc}")
		finally:
			tool_sem.release()

		self.tool_invocations.append(
			{
				"node_id": node.id,
				"tool_id": tool_id,
				"args": args,
				"success": invocation.success,
				"result": invocation.result,
				"error": invocation.error,
			}
		)

		if not invocation.success:
			return Outcome.failed(invocation.error or f"tool.call '{tool_id}' failed")
		return Outcome.succeeded(invocation.result)

	def _handle_transform(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		resolved_input = context.resolve(node.config.get("input") or {})
		result = run_transform(node.config.get("op"), resolved_input, self._transform_limits())
		if not result.ok:
			# Fail closed (I2/I7): a transform error becomes a failed node, never a
			# silently-successful empty/partial result standing in for real output.
			err = result.error
			return Outcome.failed(err.message if err else f"transform '{node.config.get('op')}' failed")
		return Outcome.succeeded(result.value)

	def _handle_condition(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		bindings = context.reference_roots()
		parsed = parse_expression(node.config["expression"])
		truth = evaluate_bool(parsed, bindings)
		next_id = node.config["on_true"] if truth else node.config["on_false"]
		return Outcome.succeeded(output=truth, next_node_id=next_id)

	def _handle_validate(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		bindings = context.reference_roots()
		failures = []
		for assertion in node.config.get("assertions", []):
			parsed = parse_expression(assertion["expression"])
			if not evaluate_bool(parsed, bindings):
				failures.append({"code": assertion["code"], "message": assertion["message"]})
		if failures:
			# Hard gate (I7): a failed assertion fails the whole run rather than emitting a
			# result that skipped an invariant it claimed to check.
			return Outcome.failed(json.dumps(failures))
		return Outcome.succeeded({"assertions_passed": len(node.config.get("assertions", []))})

	def _handle_output(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		value = context.resolve(node.config["value"])
		budget = self._output_budget()

		if isinstance(value, list):
			# A bare list at the output node IS the raw dataset the budget exists to
			# bound (I7). Under budget, it passes through untouched -- the budget check
			# must never reshape a value that was never in breach. Over budget, this
			# runtime has no spill sink wired (that is an ``Agent Context Artifact``
			# integration, out of this task's scope), so a breach fails closed rather
			# than emitting an unpersisted, silently-truncated "preview" standing in for
			# the real data -- never truncate silently (I7).
			size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
			if len(value) > budget.max_rows or size > budget.max_bytes:
				try:
					enforce_output_budget(value, budget=budget)
				except OutputBudgetExceeded as exc:
					raise ProcedureLimitExceeded(str(exc)) from exc
			return Outcome.succeeded(value)

		if isinstance(value, dict):
			size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
			if size > budget.max_bytes:
				# Fail closed: never truncate a summary object silently (I7). The
				# procedure author's job is to keep the output node's value bounded by
				# construction (aggregate, not raw rows); this is the backstop.
				raise ProcedureLimitExceeded(
					f"output node '{node.id}' value is {size} bytes, exceeds max_output_bytes "
					f"({budget.max_bytes}); refusing to truncate"
				)
			for key, field_value in value.items():
				if isinstance(field_value, list) and len(field_value) > budget.max_rows:
					raise ProcedureLimitExceeded(
						f"output node '{node.id}' field '{key}' has {len(field_value)} rows, "
						f"exceeds max_rows ({budget.max_rows}); refusing to truncate"
					)
			return Outcome.succeeded(value)

		return Outcome.succeeded(value)

	def _handle_foreach(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		cfg = node.config
		items = context.resolve(cfg["items"])
		if not isinstance(items, list):
			items = []

		node_cap = cfg.get("max_iterations")
		contract_cap = self.limits.get("max_foreach_iterations")
		caps = [c for c in (node_cap, contract_cap) if c is not None]
		effective_cap = min(caps) if caps else len(items)

		if len(items) > effective_cap:
			# Fail closed (I7): a foreach whose input exceeds either the node's own cap or
			# the contract's ceiling never silently processes a truncated prefix and calls
			# it complete -- that is exactly the kind of silent partial success this
			# invariant exists to prevent.
			raise ProcedureLimitExceeded(
				f"foreach '{node.id}' has {len(items)} items, exceeds max_iterations ({effective_cap})"
			)

		body_ids = cfg["body"]
		collect_ref = cfg.get("collect")
		on_item_error = cfg.get("on_item_error", "fail")

		_, sub_executor = self._sub_executor(body_ids)
		results = []
		for index, item in enumerate(items):
			context.push_foreach(item, index)
			try:
				sub_state = ExecutionState(cursor=body_ids[0] if body_ids else None)
				sub_result = sub_executor.execute(context, sub_state)
				if sub_result.status != ExecutionResult.SUCCESS:
					if on_item_error == "skip":
						continue
					return Outcome.failed(f"foreach '{node.id}' item {index} failed: {sub_result.error}")
				collected = context.resolve(collect_ref) if collect_ref is not None else None
				results.append(collected)
			finally:
				context.pop_foreach()

		return Outcome.succeeded(results)

	def _branch_context_copy(self, context: GraphContext) -> GraphContext:
		"""A private, independent :class:`GraphContext` for one branch's worker thread.

		Copies ``data`` / ``node_outputs`` / ``foreach_frames`` so a worker thread never
		mutates a dict a sibling worker (or the orchestrating thread) can see -- see
		scheduler.py's module docstring, "Determinism". A shallow copy is sufficient: node
		handlers replace values wholesale (``context.set``/``record_output``), they never
		mutate a nested container in place.
		"""
		branch_context = GraphContext(
			dict(context.data), run_id=context.run_id, mode=context.mode, metadata=dict(context.metadata)
		)
		branch_context.node_outputs = dict(context.node_outputs)
		branch_context.foreach_frames = list(context.foreach_frames)
		return branch_context

	def _run_branch(self, index: int, branch_ids: list[str], context: GraphContext) -> BranchResult:
		"""Runs entirely on whatever thread calls it (a worker thread, under T-30's
		bounded pool). Frappe-free -- see scheduler.py's module docstring. Records node
		visits into a private, local listener; never touches the run's real recorder.
		"""
		branch_context = self._branch_context_copy(context)
		original_output_keys = set(branch_context.node_outputs)
		original_data = dict(branch_context.data)

		local_recorder = _VisitRecorder(on_visit=None)
		_, sub_executor = self._sub_executor(branch_ids, listener=local_recorder)
		sub_state = ExecutionState(cursor=branch_ids[0] if branch_ids else None)

		try:
			sub_result = sub_executor.execute(branch_context, sub_state)
		except ProcedureLimitExceeded as exc:
			return BranchResult(index=index, ok=False, error=str(exc))

		pairs = local_recorder.pairs
		if sub_result.status != ExecutionResult.SUCCESS:
			return BranchResult(index=index, ok=False, visits=pairs, error=sub_result.error)

		node_outputs_diff = {
			k: v for k, v in branch_context.node_outputs.items() if k not in original_output_keys
		}
		data_diff = {
			k: v for k, v in branch_context.data.items() if k not in original_data or original_data[k] != v
		}
		return BranchResult(
			index=index, ok=True, visits=pairs, node_outputs=node_outputs_diff, data_diff=data_diff
		)

	def _handle_parallel(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		"""Bounded, deterministic concurrent fan-out over ``config.branches`` (T-30).

		Branches run on real OS threads, bounded by ``config.max_parallel_calls`` (falling
		back to ``contract.limits.max_parallel_calls``) and this run's graph-wide
		concurrency semaphore. Results are always reassembled and merged back into
		``context`` in ascending branch-index (declaration) order regardless of which
		thread finished first -- see ``huf.ai.graph.scheduler`` for the full threading
		model and determinism argument, and ``test_procedure_runtime.py`` for the
		jittered-completion-order determinism proof.
		"""
		cfg = node.config
		branches = cfg.get("branches", [])
		if not branches:
			return Outcome.succeeded({"branches_completed": 0, "join": cfg.get("join", "all")})

		max_parallel_calls = (
			cfg.get("max_parallel_calls") or self.limits.get("max_parallel_calls") or len(branches)
		)
		timeout_s = None
		timeout_ms = cfg.get("timeout_ms") or self.limits.get("max_wall_time_ms")
		if timeout_ms:
			timeout_s = timeout_ms / 1000.0

		branch_fns = [
			(lambda branch_ids=branch_ids, idx=idx: self._run_branch(idx, branch_ids, context))
			for idx, branch_ids in enumerate(branches)
		]

		try:
			kwargs = {"max_parallel_calls": max_parallel_calls, "graph_semaphore": self.graph_semaphore}
			if timeout_s is not None:
				kwargs["timeout_s"] = timeout_s
			results = run_parallel_branches(branch_fns, **kwargs)
		except ParallelLimitExceeded as exc:
			# Fail closed (I7 / T-30 "Done when"): a deliberate breach of max_parallel_calls
			# is rejected before any branch starts, never silently serialized or queued.
			raise ProcedureLimitExceeded(str(exc)) from exc

		# Replay every branch's locally-recorded visits, and merge its context diffs, in
		# ascending branch-index order -- the only order this method ever produces,
		# regardless of actual completion order (determinism).
		failure: BranchResult | None = None
		for result in results:
			for visit_node, visit_outcome in result.visits:
				self.recorder.node_end(visit_node, visit_outcome)
			if not result.ok:
				if failure is None:
					failure = result
				continue
			for key, value in result.node_outputs.items():
				context.node_outputs[key] = value
			for key, value in result.data_diff.items():
				if key in context.data and context.data[key] != value:
					# Two branches wrote different values under the same context key.
					# Picking either would make the run's output depend on completion
					# order -- fail closed instead (see scheduler.py docstring).
					raise ProcedureLimitExceeded(
						f"parallel '{node.id}' branches wrote conflicting values for context key '{key}'"
					)
				context.data[key] = value
				context.dirty = True

		if failure is not None:
			reason = "timed out" if failure.timed_out else failure.error
			return Outcome.failed(f"parallel '{node.id}' branch {failure.index} failed: {reason}")

		return Outcome.succeeded({"branches_completed": len(results), "join": cfg.get("join", "all")})


def execute_procedure(
	version: PinnedVersion,
	input_payload: Mapping[str, Any],
	*,
	tool_invoker: ToolInvoker,
	run_id: str | None = None,
	on_visit: Callable[[NodeSpec, Outcome], None] | None = None,
) -> ProcedureOutcome:
	"""Execute a pinned Procedure graph to completion, frappe-free.

	``tool_invoker`` is the only side-effecting seam: everything else in this function is
	pure computation over ``version.graph`` and ``input_payload``. Callers that need
	authorization (I1) and ``Agent Tool Call`` telemetry (I5) build a ``tool_invoker`` that
	provides them -- see :func:`run_agent_procedure_run` -- rather than this function
	reaching for Frappe itself.
	"""
	graph = version.graph
	contract = graph.get("contract") or {}
	limits = contract.get("limits") or {}

	# GraphContext's own "input" reference root is its whole ``data`` namespace (see
	# GraphContext.reference_roots), not a nested "input" key inside it -- so the payload
	# itself IS the context data, not wrapped under an "input" key.
	context = GraphContext(dict(input_payload), run_id=run_id)

	for expr in contract.get("applies_when") or []:
		parsed = parse_expression(expr)
		if not evaluate_bool(parsed, context.reference_roots()):
			return ProcedureOutcome(status=ProcedureOutcome.NOT_APPLICABLE)

	recorder = _VisitRecorder(on_visit=on_visit)
	runner = _Runner(
		version,
		tool_invoker=tool_invoker,
		limits=limits,
		recorder=recorder,
		wall_clock_start=time.monotonic(),
	)

	program = build_program(version)
	policy = ExecutionPolicy(max_hops=limits.get("max_nodes") or ExecutionPolicy().max_hops)
	executor = GraphExecutor(
		program, runner.handlers(), router=_router_for(program), policy=policy, listener=recorder
	)
	state = ExecutionState(cursor=program.entry)

	try:
		result = executor.execute(context, state)
	except (ProcedureLimitExceeded, RoutingError) as exc:
		failing_node_id = recorder.last_started[0] if recorder.last_started else None
		failing_node_type = recorder.last_started[1] if recorder.last_started else None
		if failing_node_id is None and recorder.visits:
			failing_node_id, failing_node_type = recorder.visits[-1]
		return ProcedureOutcome(
			status=ProcedureOutcome.FAILED,
			error=str(exc),
			node_id=failing_node_id,
			node_type=failing_node_type,
			node_visits=recorder.visits,
			tool_call_count=runner.tool_call_count,
			tool_invocations=runner.tool_invocations,
			node_outputs=dict(context.node_outputs),
		)

	terminal_node = program.node(result.node_id)
	terminal_node_type = terminal_node.type if terminal_node is not None else None

	if result.status == ExecutionResult.SUCCESS:
		output = context.node_outputs.get(result.node_id)
		return ProcedureOutcome(
			status=ProcedureOutcome.SUCCESS,
			output=output,
			node_id=result.node_id,
			node_type=terminal_node_type,
			hop_count=result.hop_count,
			node_visits=recorder.visits,
			tool_call_count=runner.tool_call_count,
			tool_invocations=runner.tool_invocations,
			node_outputs=dict(context.node_outputs),
		)

	return ProcedureOutcome(
		status=ProcedureOutcome.FAILED,
		error=result.error,
		node_id=result.node_id,
		node_type=terminal_node_type,
		hop_count=result.hop_count,
		node_visits=recorder.visits,
		tool_call_count=runner.tool_call_count,
		tool_invocations=runner.tool_invocations,
		node_outputs=dict(context.node_outputs),
	)


# ---------------------------------------------------------------------------
# Frappe-facing entry point.
# ---------------------------------------------------------------------------


def persist_fallback_state(run, result) -> dict:
	"""Write the fallback payload onto the run's EXISTING recovery fields, and return it.

	``run`` is an ``Agent Procedure Run`` document (or, in tests, any object with the same
	attributes -- this function is deliberately frappe-free and never saves: the caller
	owns the single ``run.save()``, and no explicit ``frappe.db.commit()`` is ever issued
	here). ``result`` is a :class:`huf.ai.graph.fallback.BoundResult`.

	The whole point of this function is the branch below. A ``PROCEDURE_NOT_APPLICABLE``
	result is clean, pre-execution and provably side-effect-free (``execute_procedure``
	returns it before the node loop is ever entered), so it writes NONE of the
	partial-state fields -- not even as empty lists. Writing ``completed_steps = "[]"`` /
	``committed_writes = "[]"`` would leave a retry path unable to distinguish "a run
	happened and touched nothing" from "no run happened at all", and that ambiguity is
	exactly how a retry duplicates a write (T-32). Absent stays absent.
	"""
	from huf.ai.graph.fallback import PROCEDURE_NOT_APPLICABLE

	payload = result.payload

	if result.fallback_class == PROCEDURE_NOT_APPLICABLE:
		# Clean rejection: the ONLY thing recorded is the outcome itself. No
		# completed_steps, no failed_step, no committed_writes, no pending_writes, no
		# intermediate_outputs, no safe_recovery_actions -- see docstring.
		run.output_payload = json.dumps(payload, default=str)
		return payload

	run.completed_steps = json.dumps(payload["completed_steps"], default=str)
	run.failed_step = payload["failed_step"]
	run.committed_writes = json.dumps(payload["committed_writes"], default=str)
	run.pending_writes = json.dumps(payload["pending_writes"], default=str)
	# Already budget-bounded by fallback.build_mid_run_fallback via
	# huf.ai.output_budget.enforce_output_budget -- persisted exactly as handed over. Never
	# re-read outcome.node_outputs directly here: that would put the raw, unbounded blob on
	# the DocType and defeat I7.
	run.intermediate_outputs = json.dumps(payload["intermediate_outputs"], default=str)
	run.error = json.dumps(
		{
			"error": payload["error"],
			"failed_step": payload["failed_step"],
			"status": payload["status"],
		},
		default=str,
	)
	run.safe_recovery_actions = json.dumps(payload["safe_recovery_actions"], default=str)
	return payload


def _build_fallback_for_run(run, graph: dict, outcome: "ProcedureOutcome"):
	"""Build the fallback payload for a non-SUCCESS ``outcome``, never raising (I9).

	Returns the ``BoundResult``, or ``None`` if the payload could not be built at all. A
	fallback that itself blew up must not become the thing that kills the Agent -- the run
	still gets its plain status/error written by the caller in that case.
	"""
	from huf.ai.graph import fallback as _fallback
	from huf.ai.graph import permissions as _permissions

	try:
		return _fallback.build_fallback(
			procedure_id=run.procedure_id or run.procedure,
			version=run.pinned_fingerprint,
			run=run.name,
			graph=graph,
			outcome=outcome,
			classify_tool=_permissions.default_tool_classifier,
		)
	except Exception:  # noqa: BLE001 -- I9: fallback construction never fails the Agent
		import frappe

		frappe.logger("huf").warning(
			f"Could not build fallback payload for Agent Procedure Run {run.name}; "
			f"persisting the plain failure only.\n{frappe.get_traceback()}"
		)
		return None


def run_agent_procedure_run(run_name: str, *, agent_doc=None) -> "ProcedureOutcome":
	"""Advance one ``Agent Procedure Run`` to completion.

	Loads the run, takes ``huf.ai.procedure_lock.ProcedureRunLock`` (GT-08) -- refusing to
	advance if another worker already holds it, never retrying inline -- validates the
	pinned graph (defence in depth; T-24's validator is expected to have already run at
	activation time), executes it via :func:`execute_procedure` with a real ``tool_invoker``
	that authorizes each call (I1, ``huf.ai.graph.permissions.authorize_tool_call``) and
	emits exactly one ``Agent Tool Call`` telemetry record per invocation
	(I5, ``huf.ai.tool_invocation.invoke_tool_sync(..., telemetry=True)``), records one
	``Agent Procedure Step`` child row per node visited, and writes the run's terminal
	status/output/error back once.

	Reads ``run.pinned_definition_json`` -- never ``run.procedure``'s current definition
	(I6): the run pins its graph at creation (``AgentProcedureRun._pin_definition``) and
	this function is the reader half of that contract.
	"""
	import frappe

	from huf.ai import tool_invocation as _tool_invocation
	from huf.ai.graph import permissions as _permissions
	from huf.ai.graph.executor import fingerprint as _fingerprint
	from huf.ai.graph.validator import validate_procedure_graph
	from huf.ai.procedure_lock import ProcedureRunLock

	from huf.ai.graph.cache import get_cached_result, set_cached_result
	from huf.ai.procedure_versioning import verify_fingerprint

	run = frappe.get_doc("Agent Procedure Run", run_name)

	graph = run.pinned_definition_json
	if isinstance(graph, str):
		graph = json.loads(graph)
	if not isinstance(graph, dict):
		frappe.throw(f"Agent Procedure Run {run_name} has no pinned definition to execute")

	# I6: the pinned definition is trusted from here on, so prove it was not rewritten under us.
	# Document guards do not run for frappe.db.set_value or raw SQL; recomputing the hash makes
	# that tampering detectable and fails the run closed rather than executing an altered graph.
	verify_fingerprint(graph, run.pinned_fingerprint, label=f"Agent Procedure Run {run_name}")

	is_read_only = bool(frappe.db.get_value("Agent Procedure", run.procedure, "is_read_only"))
	fingerprint_for_cache = run.pinned_fingerprint or _fingerprint(graph)
	try:
		cache_company = frappe.defaults.get_user_default("Company")
	except Exception:  # noqa: BLE001 - defaults lookup is best-effort scoping only
		cache_company = None

	if is_read_only:
		cached_input = run.input_payload
		if isinstance(cached_input, str):
			cached_input = json.loads(cached_input) if cached_input else {}
		cached_output = get_cached_result(
			procedure_version=fingerprint_for_cache,
			inputs=cached_input or {},
			user=frappe.session.user,
			company=cache_company,
		)
		if cached_output is not None:
			run.status = "Completed"
			run.output_payload = json.dumps(cached_output, default=str)
			run.save(ignore_permissions=True)
			return ProcedureOutcome(status=ProcedureOutcome.SUCCESS, output=cached_output)

	validation = validate_procedure_graph(graph, classify_tool=_permissions.default_tool_classifier)
	if not validation.ok:
		run.status = "Failed"
		run.error = json.dumps([str(e) for e in validation.errors])
		run.save(ignore_permissions=True)
		return ProcedureOutcome(status=ProcedureOutcome.FAILED, error=run.error)

	with ProcedureRunLock(run.name) as lock:
		if not lock.acquired:
			raise ProcedureExecutionError(
				f"Agent Procedure Run {run_name} is already being advanced by another worker"
			)

		version = PinnedVersion(graph=graph, fingerprint=run.pinned_fingerprint or _fingerprint(graph))
		contract = graph.get("contract") or {}
		envelope = validation.envelope or contract.get("permission_envelope") or {}
		user = frappe.session.user

		def tool_invoker(tool_id: str, args: dict) -> ToolInvocation:
			_permissions.authorize_tool_call(
				tool_id=tool_id,
				user=user,
				agent_doc=agent_doc,
				envelope=envelope,
				classify_tool=_permissions.default_tool_classifier,
			)
			ctx = _tool_invocation.RunContext(agent_run_id=run.agent_run, conversation_id=None)
			result = _tool_invocation.invoke_tool_sync(tool_id, args, ctx=ctx, telemetry=True)
			return ToolInvocation(
				tool_id=tool_id, args=args, success=result.success, result=result.result, error=result.error
			)

		def on_visit(node: NodeSpec, outcome: Outcome) -> None:
			row = run.append("steps", {})
			row.node_id = node.id
			row.node_type = node.type
			row.status = "Failed" if outcome.status == "failed" else "Completed"
			row.attempt = 1
			row.output_json = json.dumps(outcome.output, default=str) if outcome.output is not None else None
			row.error = outcome.error

		input_payload = run.input_payload
		if isinstance(input_payload, str):
			input_payload = json.loads(input_payload) if input_payload else {}

		run.status = "Running"
		run.save(ignore_permissions=True)

		outcome = execute_procedure(
			version, input_payload or {}, tool_invoker=tool_invoker, run_id=run.name, on_visit=on_visit
		)

		if outcome.status == ProcedureOutcome.SUCCESS:
			run.status = "Completed"
			run.output_payload = json.dumps(outcome.output, default=str)
			if is_read_only:
				# Structural guard lives in cache.py itself (set_cached_result raises
				# unless is_read_only is true) -- passing it explicitly here is
				# defence in depth, not the only thing standing between a mutating
				# procedure and the cache.
				set_cached_result(
					procedure_version=fingerprint_for_cache,
					inputs=input_payload or {},
					user=user,
					company=cache_company,
					is_read_only=is_read_only,
					result=outcome.output,
				)
		elif outcome.status == ProcedureOutcome.NOT_APPLICABLE:
			# Clean, pre-execution rejection: the run "completed" having done nothing.
			# persist_fallback_state writes only output_payload for this class -- the
			# partial-state recovery fields stay untouched (I9 / T-32).
			run.status = "Completed"
			run.output_payload = json.dumps({"status": "not_applicable"})
			result = _build_fallback_for_run(run, graph, outcome)
			if result is not None:
				outcome.fallback = persist_fallback_state(run, result)
		else:
			run.status = "Failed"
			run.error = json.dumps({"error": outcome.error, "node_id": outcome.node_id})
			result = _build_fallback_for_run(run, graph, outcome)
			if result is not None:
				# Overwrites run.error with the structured form and fills the
				# completed_steps / failed_step / committed_writes / pending_writes /
				# intermediate_outputs / safe_recovery_actions recovery fields.
				outcome.fallback = persist_fallback_state(run, result)

		run.save(ignore_permissions=True)
		return outcome
