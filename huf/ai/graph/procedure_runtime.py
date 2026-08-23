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
		self._on_visit = on_visit
		self._starts: dict[str, float] = {}

	def node_start(self, node: NodeSpec) -> None:
		self._starts[node.id] = time.monotonic()

	def node_end(self, node: NodeSpec, outcome: Outcome) -> None:
		self.visits.append((node.id, node.type))
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

	# -- shared budgets, fail closed (I7) ---------------------------------

	def _check_wall_time(self) -> None:
		max_ms = self.limits.get("max_wall_time_ms")
		if not max_ms:
			return
		elapsed_ms = (time.monotonic() - self.wall_clock_start) * 1000
		if elapsed_ms > max_ms:
			raise ProcedureLimitExceeded(f"max_wall_time_ms exceeded ({elapsed_ms:.0f} > {max_ms})")

	def _charge_external_call(self) -> None:
		self.external_call_count += 1
		cap = self.limits.get("max_external_calls")
		if cap is not None and self.external_call_count > cap:
			raise ProcedureLimitExceeded(f"max_external_calls exceeded ({self.external_call_count} > {cap})")

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

	def _sub_executor(self, node_ids: list[str]) -> tuple[GraphProgram, GraphExecutor]:
		program = build_subprogram(self.version, node_ids)
		# +2 headroom over the chain length: the chain itself is the hop budget for a
		# nested sub-program, distinct from and never charged against the run's own
		# max_hops (mirrors the executor's foreach/main-chain budget separation, F-3).
		policy = ExecutionPolicy(max_hops=len(node_ids) + 2)
		executor = GraphExecutor(
			program, self.handlers(), router=_router_for(program), policy=policy, listener=self.recorder
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
		self.tool_call_count += 1

		try:
			invocation = self.tool_invoker(tool_id, args)
		except ProcedureLimitExceeded:
			raise
		except Exception as exc:  # noqa: BLE001 -- a denied/raising invoker fails this node, not the process
			return Outcome.failed(f"tool.call '{tool_id}' raised: {exc}")

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

	def _handle_parallel(self, node: NodeSpec, context: GraphContext, state: ExecutionState) -> Outcome:
		"""``parallel`` is parsed and validated here but EXECUTES SEQUENTIALLY.

		Real bounded concurrency (a thread/async pool honouring ``max_parallel_calls``) is
		task T-30. This handler runs each branch's chain to completion, one branch after
		another, in declaration order -- there is no concurrency in this implementation at
		all, deliberately: doing anything less explicit here (e.g. a thread pool that
		"happens to" work) would misrepresent what T-23 delivers. See
		``test_parallel_node_executes_sequentially`` for the executable proof.
		"""
		cfg = node.config
		branches = cfg.get("branches", [])
		completed = 0
		for branch_ids in branches:
			_, sub_executor = self._sub_executor(branch_ids)
			sub_state = ExecutionState(cursor=branch_ids[0] if branch_ids else None)
			sub_result = sub_executor.execute(context, sub_state)
			if sub_result.status != ExecutionResult.SUCCESS:
				return Outcome.failed(f"parallel '{node.id}' branch {completed} failed: {sub_result.error}")
			completed += 1
		return Outcome.succeeded({"branches_completed": completed, "join": cfg.get("join", "all")})


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
		return ProcedureOutcome(
			status=ProcedureOutcome.FAILED,
			error=str(exc),
			node_visits=recorder.visits,
			tool_call_count=runner.tool_call_count,
		)

	if result.status == ExecutionResult.SUCCESS:
		output = context.node_outputs.get(result.node_id)
		return ProcedureOutcome(
			status=ProcedureOutcome.SUCCESS,
			output=output,
			node_id=result.node_id,
			hop_count=result.hop_count,
			node_visits=recorder.visits,
			tool_call_count=runner.tool_call_count,
		)

	return ProcedureOutcome(
		status=ProcedureOutcome.FAILED,
		error=result.error,
		node_id=result.node_id,
		hop_count=result.hop_count,
		node_visits=recorder.visits,
		tool_call_count=runner.tool_call_count,
	)


# ---------------------------------------------------------------------------
# Frappe-facing entry point.
# ---------------------------------------------------------------------------


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

	run = frappe.get_doc("Agent Procedure Run", run_name)

	graph = run.pinned_definition_json
	if isinstance(graph, str):
		graph = json.loads(graph)
	if not isinstance(graph, dict):
		frappe.throw(f"Agent Procedure Run {run_name} has no pinned definition to execute")

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
		elif outcome.status == ProcedureOutcome.NOT_APPLICABLE:
			run.status = "Completed"
			run.output_payload = json.dumps({"status": "not_applicable"})
		else:
			run.status = "Failed"
			run.error = json.dumps({"error": outcome.error, "node_id": outcome.node_id})

		run.save(ignore_permissions=True)
		return outcome
