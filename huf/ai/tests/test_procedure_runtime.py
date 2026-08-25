# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for huf.ai.graph.procedure_runtime (T-23).

Frappe-free by design where possible: :func:`execute_procedure` is the pure core and is
exercised directly here with a hand-written fake ``tool_invoker`` -- no ``frappe``, no
bench, runnable under plain pytest. This mirrors the pattern already used by
``test_graph_validator.py`` / ``test_graph_permissions.py`` in this directory.

Benchmark 1 (customer financial context) is executed end-to-end against the exact seed
data in ``$TRACK/benchmarks/benchmark-1-customer-context/seed-data.md``, and its
``invariants.py`` is run against the produced output. The tool layer is SIMULATED here
(a fake invoker returning the seed-data rows keyed by tool_id/args) rather than backed by
a live ERPNext bench -- this file says so explicitly at the point where the fake is built,
and the frappe-facing wiring (``run_agent_procedure_run``, real ``invoke_tool_sync``/
``authorize_tool_call``) is exercised separately in
``test_procedure_runtime_bench.py`` where a bench is available. This test proves the
*runtime's* correctness (routing, budgets, telemetry counting, sequential parallel), not
whether a specific Agent Tool Function/ERPNext installation exists.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import random
import sys
import threading
import time
import unittest
from pathlib import Path

from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.procedure_runtime import (
	ProcedureOutcome,
	ToolInvocation,
	execute_procedure,
)

# ---------------------------------------------------------------------------
# Load benchmark 1's frappe-free invariants module directly off disk -- it is
# not part of the huf package (it lives under $TRACK/benchmarks/), so import
# it by path the same way a bare `python invariants.py` would run it.
# ---------------------------------------------------------------------------

def _find_benchmark_1_dir() -> Path | None:
	"""Walk ancestor directories looking for benchmarks/benchmark-1-customer-context.

	Deliberately not a fixed ``parents[N]`` index: the app checkout sits at a different
	nesting depth relative to ``$TRACK/benchmarks`` depending on where it's checked out
	(``$TRACK/wt/T-23`` in this worktree vs. ``.../apps/huf`` on the bench, where the
	benchmark tree is mirrored as a sibling of ``apps/huf``) -- searching upward is what
	makes this test locate the fixture in both places without hardcoding either layout.
	"""
	here = Path(__file__).resolve()
	for parent in here.parents:
		candidate = parent / "benchmarks" / "benchmark-1-customer-context"
		if (candidate / "invariants.py").exists():
			return candidate
	return None


_BENCHMARK_1_DIR = _find_benchmark_1_dir()


def _load_invariants():
	if _BENCHMARK_1_DIR is None:
		raise unittest.SkipTest(
			"benchmarks/benchmark-1-customer-context/invariants.py not found relative to this "
			"file -- expected as a sibling of the app checkout (see _find_benchmark_1_dir)"
		)
	spec = importlib.util.spec_from_file_location(
		"benchmark1_invariants", _BENCHMARK_1_DIR / "invariants.py"
	)
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


# ---------------------------------------------------------------------------
# Minimal graph builder helpers -- keep test graphs close to the IR shape
# (spec/graph-ir.md) without pulling in the full JSON Schema validator, which
# is T-24's job, not this module's.
# ---------------------------------------------------------------------------


def _contract(**limits) -> dict:
	defaults = dict(
		max_nodes=50,
		max_rows=1000,
		max_output_bytes=1_000_000,
		max_parallel_calls=4,
		max_foreach_iterations=100,
		max_external_calls=20,
		max_writes=0,
		max_wall_time_ms=30_000,
		fail_closed=True,
	)
	defaults.update(limits)
	return {
		"input_schema": {},
		"output_schema": {},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": defaults,
	}


def _pin(graph: dict) -> PinnedVersion:
	return PinnedVersion.pin(graph)


class FakeInvoker:
	"""Hand-written double standing in for the real tool layer (T-10's
	``invoke_tool_sync``). Per the TEST HARNESS RULES this task was briefed on: no
	MagicMock-only affordances (``.side_effect`` etc.) -- this is a plain callable class
	with an explicit call log, matching ``_ensure_saving_flag``-style hand doubles used
	elsewhere in this track.
	"""

	def __init__(self, table: dict[str, object]):
		self.table = table
		self.calls: list[tuple[str, dict]] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append((tool_id, copy.deepcopy(args)))
		if tool_id not in self.table:
			return ToolInvocation(tool_id, args, success=False, error=f"no such tool {tool_id!r}")
		value = self.table[tool_id]
		result = value(args) if callable(value) else value
		return ToolInvocation(tool_id, args, success=True, result=result)


# ---------------------------------------------------------------------------
# Basic node-type coverage
# ---------------------------------------------------------------------------


class TestToolCallAndTransform(unittest.TestCase):
	def test_tool_call_then_transform_then_output(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "fetch",
			"contract": _contract(),
			"nodes": [
				{
					"id": "fetch",
					"type": "tool.call",
					"config": {"tool_id": "get_rows", "input": {}},
					"next": "select",
				},
				{
					"id": "select",
					"type": "transform",
					"config": {
						"op": "select",
						"input": {"rows": {"$from": "fetch"}, "fields": ["name", "amount"]},
					},
					"next": "out",
				},
				{
					"id": "out",
					"type": "output",
					"config": {"value": {"$from": "select"}},
				},
			],
		}
		invoker = FakeInvoker({"get_rows": [{"name": "A", "amount": 1, "extra": "x"}]})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(outcome.output, [{"name": "A", "amount": 1}])
		self.assertEqual(invoker.calls, [("get_rows", {})])
		self.assertEqual(outcome.tool_call_count, 1)


class TestCondition(unittest.TestCase):
	def _graph(self):
		return {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "check",
			"contract": _contract(),
			"nodes": [
				{
					"id": "check",
					"type": "condition",
					"config": {"expression": 'input["n"] > 0', "on_true": "yes", "on_false": "no"},
				},
				{"id": "yes", "type": "output", "config": {"value": "positive"}},
				{"id": "no", "type": "output", "config": {"value": "non-positive"}},
			],
		}

	def test_true_branch(self):
		outcome = execute_procedure(_pin(self._graph()), {"n": 5}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.output, "positive")

	def test_false_branch(self):
		outcome = execute_procedure(_pin(self._graph()), {"n": -1}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.output, "non-positive")


class TestValidateFailsClosed(unittest.TestCase):
	def test_failed_assertion_fails_the_run(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "chk",
			"contract": _contract(),
			"nodes": [
				{
					"id": "chk",
					"type": "validate",
					"config": {
						"assertions": [
							{"expression": 'input["n"] > 10', "code": "N_TOO_SMALL", "message": "n must exceed 10"}
						]
					},
					"next": "out",
				},
				{"id": "out", "type": "output", "config": {"value": "reached"}},
			],
		}
		outcome = execute_procedure(_pin(graph), {"n": 1}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("N_TOO_SMALL", outcome.error)


class TestForeachBounded(unittest.TestCase):
	def _graph(self, max_iterations=10):
		return {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "loop",
			"contract": _contract(max_foreach_iterations=100),
			"nodes": [
				{
					"id": "loop",
					"type": "foreach",
					"config": {
						"items": {"$from": "input.rows"},
						"item_var": "item",
						"index_var": "index",
						"body": ["double"],
						"max_iterations": max_iterations,
						"on_item_error": "fail",
						"collect": {"$from": "double"},
					},
					"next": "out",
				},
				{
					"id": "double",
					"type": "transform",
					"config": {"op": "coalesce", "input": {"values": [{"$from": "foreach.item"}]}},
				},
				{"id": "out", "type": "output", "config": {"value": {"$from": "loop"}}},
			],
		}

	def test_iterates_and_collects_in_order(self):
		outcome = execute_procedure(
			_pin(self._graph()), {"rows": [1, 2, 3]}, tool_invoker=FakeInvoker({})
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(outcome.output, [1, 2, 3])

	def test_does_not_charge_the_run_hop_budget_per_item(self):
		# 50 items, each visiting one body node -- if this charged the top-level max_hops
		# budget per item it would blow a max_nodes=50 ceiling (loop + out + 50 already
		# exceeds it). It doesn't, because foreach iteration is its own bounded sub-program
		# (F-3): the run's hop budget only ever sees "loop" and "out".
		outcome = execute_procedure(
			_pin(self._graph(max_iterations=200)),
			{"rows": list(range(50))},
			tool_invoker=FakeInvoker({}),
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(len(outcome.output), 50)

	def test_fails_closed_when_items_exceed_max_iterations(self):
		# execute_procedure catches ProcedureLimitExceeded internally (I7: a resource-limit
		# breach is a normal, reportable run failure, not a process-level crash) and returns
		# a FAILED outcome carrying the limit language, rather than silently processing a
		# truncated 2-of-3 prefix and calling it complete.
		outcome = execute_procedure(
			_pin(self._graph(max_iterations=2)), {"rows": [1, 2, 3]}, tool_invoker=FakeInvoker({})
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("max_iterations", outcome.error)


def _fan_out_graph(branch_ids: list[str] = ("branch_a", "branch_b")) -> dict:
	branches_cfg = [[b] for b in branch_ids]
	nodes = [
		{
			"id": "customer",
			"type": "tool.call",
			"config": {"tool_id": "fetch_customer", "input": {}},
			"next": "fan_out",
		},
		{
			"id": "fan_out",
			"type": "parallel",
			"config": {"branches": branches_cfg, "join": "all"},
			"next": "out",
		},
	]
	for b in branch_ids:
		nodes.append({"id": b, "type": "tool.call", "config": {"tool_id": f"fetch_{b}", "input": {}}})
	nodes.append(
		{
			"id": "out",
			"type": "output",
			"config": {"value": {b: {"$from": b} for b in branch_ids}},
		}
	)
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "customer",
		"contract": _contract(),
		"nodes": nodes,
	}


class JitteredInvoker:
	"""Like ``FakeInvoker`` but sleeps a small, randomized amount before returning --
	used to force branches of a ``parallel`` node to complete in a different wall-clock
	order on (almost) every call, so a determinism test that passes despite this jitter is
	actually proving something about result reassembly, not just getting lucky with thread
	scheduling. Thread-safe: ``calls`` append is protected by a lock, matching this track's
	rule against relying on MagicMock-only affordances for fixture logic.
	"""

	def __init__(self, table: dict[str, object], *, max_delay_s: float = 0.02):
		self.table = table
		self.max_delay_s = max_delay_s
		self.calls: list[tuple[str, dict]] = []
		self._lock = threading.Lock()

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		time.sleep(random.uniform(0, self.max_delay_s))
		with self._lock:
			self.calls.append((tool_id, copy.deepcopy(args)))
		if tool_id not in self.table:
			return ToolInvocation(tool_id, args, success=False, error=f"no such tool {tool_id!r}")
		value = self.table[tool_id]
		result = value(args) if callable(value) else value
		return ToolInvocation(tool_id, args, success=True, result=result)


class TestParallelConcurrentExecution(unittest.TestCase):
	def test_parallel_branches_both_complete_and_are_addressable(self):
		graph = _fan_out_graph()
		invoker = FakeInvoker(
			{"fetch_customer": {"id": "C1"}, "fetch_branch_a": ["INV-1"], "fetch_branch_b": ["PAY-1"]}
		)
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(outcome.output, {"branch_a": ["INV-1"], "branch_b": ["PAY-1"]})
		self.assertEqual(outcome.tool_call_count, 3)
		called_tools = {t for t, _ in invoker.calls}
		self.assertEqual(called_tools, {"fetch_customer", "fetch_branch_a", "fetch_branch_b"})

	def test_determinism_under_jittered_completion_order(self):
		"""Run the same graph 30 times with randomized per-call delays so branches finish
		in varying wall-clock order across runs, and assert the final output and the
		recorded node-visit sequence are byte-identical every time.
		"""
		graph = _fan_out_graph(["branch_a", "branch_b", "branch_c", "branch_d"])
		outputs = []
		visit_sequences = []
		for _ in range(30):
			invoker = JitteredInvoker(
				{
					"fetch_customer": {"id": "C1"},
					"fetch_branch_a": ["A"],
					"fetch_branch_b": ["B"],
					"fetch_branch_c": ["C"],
					"fetch_branch_d": ["D"],
				}
			)
			visits: list[tuple[str, str]] = []
			outcome = execute_procedure(
				_pin(graph),
				{},
				tool_invoker=invoker,
				on_visit=lambda node, outcome, visits=visits: visits.append((node.id, node.type)),
			)
			self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
			outputs.append(json.dumps(outcome.output, sort_keys=True))
			visit_sequences.append(visits)

		self.assertEqual(len(set(outputs)), 1, "output differed across runs under jittered completion order")
		first = visit_sequences[0]
		for other in visit_sequences[1:]:
			self.assertEqual(other, first, "node-visit order differed across runs under jittered completion order")

	def test_branch_count_exceeding_max_parallel_calls_is_rejected_not_queued(self):
		"""A deliberate concurrency-limit breach fails the node closed before any branch
		starts -- it is never silently serialized and never queued past the cap.
		"""
		branch_ids = [f"branch_{i}" for i in range(5)]
		graph = _fan_out_graph(branch_ids)
		graph["nodes"][1]["config"]["max_parallel_calls"] = 2
		invoker = FakeInvoker({"fetch_customer": {"id": "C1"}, **{f"fetch_{b}": [b] for b in branch_ids}})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("max_parallel_calls", outcome.error)
		# Rejected before any branch tool.call happened -- only fetch_customer (the
		# main-chain node before the parallel node) was ever invoked.
		called_tools = [t for t, _ in invoker.calls]
		self.assertEqual(called_tools, ["fetch_customer"])

	def test_branch_count_within_contract_max_parallel_calls_falls_back_and_succeeds(self):
		branch_ids = ["branch_a", "branch_b"]
		graph = _fan_out_graph(branch_ids)
		graph["contract"]["limits"]["max_parallel_calls"] = 2
		invoker = FakeInvoker({"fetch_customer": {"id": "C1"}, "fetch_branch_a": ["A"], "fetch_branch_b": ["B"]})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)

	def test_one_failing_branch_fails_the_parallel_node_closed(self):
		graph = _fan_out_graph(["branch_a", "branch_b"])
		invoker = FakeInvoker({"fetch_customer": {"id": "C1"}, "fetch_branch_a": ["A"]})  # branch_b's tool missing
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("branch", outcome.error)

	def test_tool_invoker_never_called_from_more_than_max_tool_concurrency_threads_at_once(self):
		"""Per-tool concurrency cap: a graph fanning out many branches that all call the
		SAME tool_id must never have more than ``max_tool_concurrency`` calls to that tool
		in flight simultaneously.
		"""
		branch_ids = [f"branch_{i}" for i in range(6)]
		graph = _fan_out_graph(branch_ids)
		for node in graph["nodes"]:
			if node["id"] in branch_ids:
				node["config"]["tool_id"] = "shared_tool"  # every branch hits the same tool
		graph["contract"]["limits"]["max_tool_concurrency"] = 2
		graph["contract"]["limits"]["max_parallel_calls"] = len(branch_ids)

		in_flight = {"count": 0, "max_seen": 0}
		lock = threading.Lock()

		def _shared_tool(_args):
			with lock:
				in_flight["count"] += 1
				in_flight["max_seen"] = max(in_flight["max_seen"], in_flight["count"])
			time.sleep(0.03)
			with lock:
				in_flight["count"] -= 1
			return "ok"

		invoker = FakeInvoker({"fetch_customer": {"id": "C1"}, "shared_tool": _shared_tool})
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertLessEqual(in_flight["max_seen"], 2)


class TestFrappeThreadConfinement(unittest.TestCase):
	def test_on_visit_is_never_invoked_off_the_calling_thread(self):
		"""The threading model (huf.ai.graph.scheduler module docstring) requires that
		``on_visit`` -- the frappe-writing callback in ``run_agent_procedure_run`` -- is
		only ever called from the thread that called ``execute_procedure``, never from a
		branch worker thread. This test double raises if called off that thread, standing
		in for a real ``frappe.db``-touching ``on_visit``.
		"""
		main_thread = threading.current_thread()
		violations = []

		def _on_visit(node, outcome):
			if threading.current_thread() is not main_thread:
				violations.append(node.id)

		graph = _fan_out_graph(["branch_a", "branch_b", "branch_c"])
		invoker = JitteredInvoker(
			{
				"fetch_customer": {"id": "C1"},
				"fetch_branch_a": ["A"],
				"fetch_branch_b": ["B"],
				"fetch_branch_c": ["C"],
			}
		)
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=invoker, on_visit=_on_visit)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(violations, [], "on_visit was invoked off the calling (owning) thread")


class TestOutputBudgetFailsClosed(unittest.TestCase):
	def test_output_list_under_budget_passes_through_untouched(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "out",
			"contract": _contract(max_rows=10, max_output_bytes=1_000_000),
			"nodes": [{"id": "out", "type": "output", "config": {"value": {"$from": "input.rows"}}}],
		}
		outcome = execute_procedure(
			_pin(graph), {"rows": [{"n": 1}, {"n": 2}, {"n": 3}]}, tool_invoker=FakeInvoker({})
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		self.assertEqual(outcome.output, [{"n": 1}, {"n": 2}, {"n": 3}])

	def test_output_list_exceeding_max_rows_fails_closed_not_truncated(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "out",
			"contract": _contract(max_rows=2, max_output_bytes=1_000_000),
			"nodes": [{"id": "out", "type": "output", "config": {"value": {"$from": "input.rows"}}}],
		}
		outcome = execute_procedure(
			_pin(graph), {"rows": [{"n": 1}, {"n": 2}, {"n": 3}]}, tool_invoker=FakeInvoker({})
		)
		# No spill sink is wired into this runtime configuration, so a breach fails the run
		# closed (I7) rather than emitting a silently-truncated 2-of-3 result. A future
		# caller that wires an Agent Context Artifact spill sink gets an inline preview +
		# dataset_handle instead (huf.ai.output_budget's own contract); that wiring is out
		# of this task's scope.
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("refusing to silently truncate", outcome.error)

	def test_output_dict_exceeding_max_bytes_fails_closed_not_truncated(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "out",
			"contract": _contract(max_output_bytes=10),
			"nodes": [{"id": "out", "type": "output", "config": {"value": {"summary": "way more than ten bytes"}}}],
		}
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("max_output_bytes", outcome.error)


class TestNoLLMPath(unittest.TestCase):
	def test_flow_only_node_type_is_not_a_registered_handler(self):
		"""I4: no handler exists for agent.run / router.llm anywhere in this module. A
		graph containing one (which should already be impossible per the Procedure
		profile's schema, T-24) still cannot execute here -- it fails with "Unknown node
		type", never silently dispatches to an LLM.
		"""
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "sneaky",
			"contract": _contract(),
			"nodes": [{"id": "sneaky", "type": "agent.run", "config": {}}],
		}
		outcome = execute_procedure(_pin(graph), {}, tool_invoker=FakeInvoker({}))
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("Unknown node type", outcome.error)


class TestAppliesWhen(unittest.TestCase):
	def test_short_circuits_before_any_node_runs(self):
		graph = {
			"schema_version": "1.0.0",
			"profile": "procedure",
			"entry": "would_call",
			"contract": {**_contract(), "applies_when": ['input["enabled"]']},
			"nodes": [
				{
					"id": "would_call",
					"type": "tool.call",
					"config": {"tool_id": "should_not_run", "input": {}},
				}
			],
		}
		invoker = FakeInvoker({"should_not_run": "should not be reached"})
		outcome = execute_procedure(_pin(graph), {"enabled": False}, tool_invoker=invoker)
		self.assertEqual(outcome.status, ProcedureOutcome.NOT_APPLICABLE)
		self.assertEqual(invoker.calls, [])


# ---------------------------------------------------------------------------
# Benchmark 1 -- customer financial context, end to end.
# ---------------------------------------------------------------------------


def _benchmark_1_graph() -> dict:
	"""Mirrors $TRACK/benchmarks/benchmark-1-customer-context/expected-procedure.md."""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fetch_customer",
		"contract": _contract(max_rows=200, max_output_bytes=200_000, max_external_calls=10),
		"nodes": [
			{
				"id": "fetch_customer",
				"type": "tool.call",
				"config": {"tool_id": "fetch_customer", "input": {"customer_id": {"$from": "input.customer_id"}}},
				"next": "fan_out",
			},
			{
				"id": "fan_out",
				"type": "parallel",
				"config": {"branches": [["fetch_invoices"], ["fetch_payments"]], "join": "all"},
				"next": "compute_outstanding",
			},
			{
				"id": "fetch_invoices",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_open_sales_invoices",
					"input": {
						"customer": {"$from": "fetch_customer.customer_id"},
						"company": {"$from": "fetch_customer.company"},
						"currency": {"$from": "fetch_customer.default_currency"},
					},
				},
			},
			{
				"id": "fetch_payments",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_payment_entries",
					"input": {
						"party": {"$from": "fetch_customer.customer_id"},
						"company": {"$from": "fetch_customer.company"},
					},
				},
			},
			{
				"id": "compute_outstanding",
				"type": "transform",
				"config": {"op": "aggregate", "input": {"rows": {"$from": "fetch_invoices"}, "op": "sum", "field": "outstanding_amount"}},
				"next": "count_invoices",
			},
			{
				"id": "count_invoices",
				"type": "transform",
				"config": {"op": "aggregate", "input": {"rows": {"$from": "fetch_invoices"}, "op": "count"}},
				"next": "scope_check",
			},
			{
				"id": "scope_check",
				"type": "validate",
				"config": {
					"assertions": [
						{
							"expression": 'fetch_customer["customer_id"] == input["customer_id"]',
							"code": "CUSTOMER_MISMATCH",
							"message": "fetched customer does not match requested customer_id",
						}
					]
				},
				"next": "out",
			},
			{
				"id": "out",
				"type": "output",
				"config": {
					"value": {
						"customer_id": {"$from": "fetch_customer.customer_id"},
						"company": {"$from": "fetch_customer.company"},
						"currency": {"$from": "fetch_customer.default_currency"},
						"total_outstanding": {"$from": "compute_outstanding"},
						"open_invoice_count": {"$from": "count_invoices"},
						"invoices": {"$from": "fetch_invoices"},
						"payments": {"$from": "fetch_payments"},
					}
				},
			},
		],
	}


class TestBenchmark1CustomerContext(unittest.TestCase):
	"""Executes Benchmark 1 end to end against the exact seed data in
	benchmarks/benchmark-1-customer-context/seed-data.md, then runs the benchmark's own
	invariants.py against the produced output.

	SIMULATED, not live-ERPNext: the tool layer here is a hand-written fake keyed by
	tool_id, returning the seed-data rows already scoped by company/currency/customer --
	exactly what a real fetch_open_sales_invoices/fetch_payment_entries Agent Tool Function
	backed by ERPNext would return for these filter args, on a bench where those DocTypes
	and records exist. What this test proves: the ProcedureRuntime correctly threads scope
	filters into tool args (never post-hoc filters), aggregates, validates, and bounds
	output -- i.e. the runtime's contribution to Benchmark 1. It does not prove an
	`Agent Tool Function` named `fetch_open_sales_invoices` exists and is correctly wired to
	ERPNext on any given bench; that is a fixture/tool-catalog concern, separate from this
	module.
	"""

	COMPANY = "Huf Retail Pvt Ltd"
	CURRENCY = "INR"

	def _seed_tools(self):
		customers = {
			"CUST-0001": {"customer_id": "CUST-0001", "company": self.COMPANY, "default_currency": self.CURRENCY},
			"CUST-0002": {"customer_id": "CUST-0002", "company": self.COMPANY, "default_currency": self.CURRENCY},
			"CUST-0009": {"customer_id": "CUST-0009", "company": "Globex Overseas Ltd", "default_currency": "USD"},
		}
		all_invoices = [
			{"name": "SINV-1001", "customer": "CUST-0001", "company": self.COMPANY, "currency": self.CURRENCY, "outstanding_amount": 0.0, "status": "Paid"},
			{"name": "SINV-1002", "customer": "CUST-0001", "company": self.COMPANY, "currency": self.CURRENCY, "outstanding_amount": 32000.0, "status": "Overdue"},
			{"name": "SINV-1003", "customer": "CUST-0001", "company": self.COMPANY, "currency": self.CURRENCY, "outstanding_amount": 18500.0, "status": "Unpaid"},
			{"name": "SINV-9001", "customer": "CUST-0009", "company": "Globex Overseas Ltd", "currency": "USD", "outstanding_amount": 999.0, "status": "Overdue"},
			{"name": "SINV-1004", "customer": "CUST-0002", "company": self.COMPANY, "currency": self.CURRENCY, "outstanding_amount": 500.0, "status": "Overdue"},
		]
		all_payments = [
			{"name": "PE-2001", "party": "CUST-0001", "company": self.COMPANY, "currency": self.CURRENCY},
		]

		def fetch_customer(args):
			return customers[args["customer_id"]]

		def fetch_open_sales_invoices(args):
			# The tool itself scopes by customer/company/currency (expected-procedure.md's
			# point: filters are threaded as query args, never applied post-hoc) and
			# excludes Paid invoices ("open" means outstanding > 0).
			return [
				inv
				for inv in all_invoices
				if inv["customer"] == args["customer"]
				and inv["company"] == args["company"]
				and inv["currency"] == args["currency"]
				and inv["outstanding_amount"] > 0
			]

		def fetch_payment_entries(args):
			return [
				pmt
				for pmt in all_payments
				if pmt["party"] == args["party"] and pmt["company"] == args["company"]
			]

		return {
			"fetch_customer": fetch_customer,
			"fetch_open_sales_invoices": fetch_open_sales_invoices,
			"fetch_payment_entries": fetch_payment_entries,
		}

	def test_benchmark_1_end_to_end(self):
		invoker = FakeInvoker(self._seed_tools())
		graph = _benchmark_1_graph()
		outcome = execute_procedure(_pin(graph), {"customer_id": "CUST-0001"}, tool_invoker=invoker)

		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS, outcome.error)

		result = dict(outcome.output)

		invariants = _load_invariants()
		invariants.assert_total_outstanding_preserved(result, expected_total=50500.00)
		invariants.assert_customer_ids_preserved(result, expected_customer_id="CUST-0001")
		invariants.assert_no_unauthorized_records(result, authorized_customer_id="CUST-0001")
		invariants.assert_no_duplicates(result)
		invariants.assert_currency_company_scope(result, self.COMPANY, self.CURRENCY)
		invariants.assert_output_is_bounded(result)

		# I5: exactly one Agent-Tool-Call-equivalent invocation per atomic operation --
		# fetch_customer, fetch_open_sales_invoices, fetch_payment_entries. scope_check is a
		# `validate` node and emits none (expected-procedure.md is explicit about this).
		self.assertEqual(outcome.tool_call_count, 3)
		called_tools = [t for t, _ in invoker.calls]
		self.assertEqual(called_tools, ["fetch_customer", "fetch_open_sales_invoices", "fetch_payment_entries"])
		# Sequential parallel proof, in this same run: invoices before payments.
		self.assertEqual(called_tools[1:], ["fetch_open_sales_invoices", "fetch_payment_entries"])

	def test_benchmark_1_scope_filters_are_threaded_not_post_hoc(self):
		"""The distractor company/customer rows must never even be requested, let alone
		filtered out after the fact -- the fake tool's own scoping proves the runtime
		passed company/currency/customer as query args (per expected-procedure.md), not
		that a post-hoc step happened to catch a leak.
		"""
		invoker = FakeInvoker(self._seed_tools())
		outcome = execute_procedure(
			_pin(_benchmark_1_graph()), {"customer_id": "CUST-0001"}, tool_invoker=invoker
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS, outcome.error)
		invoice_call_args = invoker.calls[1][1]
		self.assertEqual(invoice_call_args["customer"], "CUST-0001")
		self.assertEqual(invoice_call_args["company"], self.COMPANY)
		self.assertEqual(invoice_call_args["currency"], self.CURRENCY)


if __name__ == "__main__":
	unittest.main()
