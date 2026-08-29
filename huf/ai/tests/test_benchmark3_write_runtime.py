# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""T-40 write runtime: idempotency, checkpointing, recovery semantics, approval passthrough.

Frappe-free by design (mirrors test_procedure_runtime.py): :func:`execute_procedure` is
exercised directly with a hand-written fake ``tool_invoker`` and a hand-written fake ERPNext
ToDo store -- no frappe, no bench, runnable under plain pytest.

**What this proves, and what it does not.** Per the task brief: this SIMULATES the tool
layer exactly as T-23/T-30's own tests do (``FakeInvoker`` here mirrors
``test_procedure_runtime.py``'s). It proves the *runtime's* write-node contract: an
unmarked write node is refused, a duplicate invocation within the dedup window is a no-op,
a mid-run failure produces the correct partial-failure shape, and a replay after that
failure converges to exactly the right document count -- all against an in-memory
``_FakeTodoStore`` standing in for ERPNext's ``ToDo`` doctype. It does NOT prove that a
real ``frappe.get_doc("ToDo", ...).insert()`` behaves the same way under a real MariaDB
transaction, that ``Agent Tool Call``/``Agent Procedure Step`` rows persist correctly
through a real ``bench`` worker crash, or that ``huf.ai.tool_invocation.invoke_tool_sync``'s
real authorization/telemetry wiring is exercised -- those require a bench and are out of
this file's reach (see the task's "TEST HARNESS RULES" and "DO NOT TOUCH THE BENCH").
``huf.ai.graph.idempotency``'s ``reserve_idempotency_key``/``release_idempotency_key`` are
exercised here against a hand-rolled fake Redis-like cache injected via ``sys.modules``,
not a real ``frappe.cache()``.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.idempotency import (
	derive_idempotency_key,
	derive_operation_key,
	release_idempotency_key,
	reserve_idempotency_key,
)
from huf.ai.graph.procedure_runtime import (
	RECOVERY_MODES,
	RECOVERY_RESUME,
	RECOVERY_RETRY,
	ProcedureOutcome,
	ToolInvocation,
	execute_procedure,
)


def _find_benchmark_3_dir() -> Path | None:
	here = Path(__file__).resolve()
	for parent in here.parents:
		candidate = parent / "benchmarks" / "benchmark-3-crm-followup"
		if (candidate / "invariants.py").exists():
			return candidate
	return None


_BENCHMARK_3_DIR = _find_benchmark_3_dir()


def _load_invariants():
	if _BENCHMARK_3_DIR is None:
		raise unittest.SkipTest(
			"benchmarks/benchmark-3-crm-followup/invariants.py not found relative to this file"
		)
	spec = importlib.util.spec_from_file_location("benchmark3_invariants", _BENCHMARK_3_DIR / "invariants.py")
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


# ---------------------------------------------------------------------------
# A hand-rolled Redis-like double for huf.ai.graph.idempotency's frappe.cache()
# calls -- per TEST HARNESS RULES: no MagicMock .side_effect reliance, no
# mutating the real frappe module (there is none here at all; this replaces
# sys.modules['frappe'] wholesale for the duration of a test, same as
# conftest.py's own top-level stub, just with real nx/ex semantics instead of
# a bare MagicMock that would make every reservation trivially "succeed").
# ---------------------------------------------------------------------------


class _FakeCache:
	def __init__(self):
		self.store: dict[str, int] = {}

	def set(self, key, value, ex=None, nx=False):
		if nx and key in self.store:
			return False
		self.store[key] = value
		return True

	def delete(self, key):
		self.store.pop(key, None)


class _FakeFrappeModule:
	"""Stands in for the whole ``frappe`` module for idempotency.py's ``import frappe``.

	Only implements what ``huf.ai.graph.idempotency`` actually calls: ``cache()`` and
	``logger()``.
	"""

	def __init__(self):
		self._cache = _FakeCache()

	def cache(self):
		return self._cache

	def logger(self, *_a, **_kw):
		return MagicMock()


def _install_fake_frappe() -> _FakeFrappeModule:
	# Snapshot whatever currently sits at sys.modules["frappe"] -- on a real bench run this
	# is the genuine frappe package -- so it can be restored exactly, not clobbered. A bare
	# unconditional overwrite here previously left a plain MagicMock() behind for the rest
	# of the process (see _restore_real_stub's old body), which any later code doing a
	# deferred `import frappe` inside a function body would pick up from the sys.modules
	# cache: `frappe.get_doc(...)` silently became `MagicMock().get_doc(...)`, breaking
	# unrelated tests elsewhere in the same `bench run-tests` run.
	global _PREVIOUS_FRAPPE_MODULE
	_PREVIOUS_FRAPPE_MODULE = sys.modules.get("frappe")
	fake = _FakeFrappeModule()
	sys.modules["frappe"] = fake
	return fake


def _restore_real_stub() -> None:
	# Restore exactly what was there before _install_fake_frappe ran -- the real frappe
	# module on a bench, or nothing (module absent) on a standalone run -- instead of
	# permanently replacing sys.modules["frappe"] with a MagicMock.
	if _PREVIOUS_FRAPPE_MODULE is None:
		sys.modules.pop("frappe", None)
	else:
		sys.modules["frappe"] = _PREVIOUS_FRAPPE_MODULE


_PREVIOUS_FRAPPE_MODULE = None


class IdempotencyKeyDerivationTests(unittest.TestCase):
	"""Pure unit tests for huf.ai.graph.idempotency (no frappe import at all)."""

	def test_content_derived_not_run_scoped(self):
		key_a = derive_idempotency_key(
			procedure_name="crm-followup",
			procedure_version="v1",
			normalised_inputs={"allocated_to": "collections@hufretail.example"},
			target_identity="CUST-0001:SINV-2001",
		)
		key_b = derive_idempotency_key(
			procedure_name="crm-followup",
			procedure_version="v1",
			normalised_inputs={"allocated_to": "collections@hufretail.example"},
			target_identity="CUST-0001:SINV-2001",
		)
		# Same content, computed twice (standing in for two separate Agent Procedure Runs) ->
		# identical key. D5: this is what "not run-scoped" means operationally.
		self.assertEqual(key_a, key_b)

	def test_different_target_identity_different_key(self):
		base = dict(procedure_name="crm-followup", procedure_version="v1", normalised_inputs={})
		key_1 = derive_idempotency_key(target_identity="CUST-0001:SINV-2001", **base)
		key_2 = derive_idempotency_key(target_identity="CUST-0002:SINV-2002", **base)
		self.assertNotEqual(key_1, key_2)

	def test_key_order_independent_of_dict_field_order(self):
		key_1 = derive_idempotency_key(
			procedure_name="p", procedure_version="v1", normalised_inputs={"a": 1, "b": 2}, target_identity="t"
		)
		key_2 = derive_idempotency_key(
			procedure_name="p", procedure_version="v1", normalised_inputs={"b": 2, "a": 1}, target_identity="t"
		)
		self.assertEqual(key_1, key_2)

	def test_operation_key_is_legible_not_a_hash(self):
		op_key = derive_operation_key(procedure_name="crm-followup", node_id="create_todo", target_identity="CUST-0001:SINV-2001")
		self.assertEqual(op_key, "crm-followup:create_todo:CUST-0001:SINV-2001")


class IdempotencyReservationTests(unittest.TestCase):
	"""reserve_idempotency_key / release_idempotency_key against the fake cache."""

	def setUp(self):
		self.fake_frappe = _install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_second_reservation_within_window_fails(self):
		self.assertTrue(reserve_idempotency_key("key-1", window_seconds=3600))
		self.assertFalse(reserve_idempotency_key("key-1", window_seconds=3600))

	def test_release_then_reserve_again_succeeds(self):
		self.assertTrue(reserve_idempotency_key("key-2", window_seconds=3600))
		release_idempotency_key("key-2")
		self.assertTrue(reserve_idempotency_key("key-2", window_seconds=3600))

	def test_release_of_unheld_key_is_a_no_op(self):
		release_idempotency_key("never-held")  # must not raise


# ---------------------------------------------------------------------------
# Benchmark 3 graph: fetch -> foreach(qualify -> condition -> existing_check ->
# condition -> create_todo -> verify -> mark) -> compute_summary -> output.
#
# All four branch outcomes converge on a `coalesce` transform (the only
# multi-input "pick whichever ran" op the real transforms.py registry
# provides -- see huf/ai/graph/transforms.py REGISTRY) so the foreach body
# stays a single linear chain per spec/graph-ir.md section 2 while still
# expressing the 4-way branch expected-procedure.md describes.
# ---------------------------------------------------------------------------


def _contract(**limits) -> dict:
	defaults = dict(
		max_nodes=200,
		max_rows=1000,
		max_output_bytes=1_000_000,
		max_parallel_calls=4,
		max_foreach_iterations=20,
		max_external_calls=100,
		max_writes=10,
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


def _benchmark3_graph(*, create_recovery: str = RECOVERY_RESUME) -> dict:
	"""Benchmark 3's shape (fetch -> foreach(qualify -> condition -> existing_check ->
	create_todo -> verify) -> finalize) -> compute_summary -> output, adapted to a real
	constraint of this IR engine: ``GraphContext.node_outputs`` is a flat, run-wide dict
	keyed by node id, NOT reset per foreach iteration (see ``executor.py``'s
	``GraphContext``/``foreach_frames`` -- only the ``foreach`` root is frame-scoped, node
	outputs are not). A node that is conditionally SKIPPED in one iteration but visited in
	another carries a stale prior-iteration value forward. ``expected-procedure.md``'s
	pseudocode has FOUR separate terminal ``transform mark(...)`` nodes reached via
	divergent condition branches -- exactly the shape that trips this staleness trap.

	This graph keeps the required ``condition`` nodes (``branch`` on qualification,
	implicitly folded into ``create_todo``'s own existing-check-aware behaviour below) but
	converges on ONE always-visited terminal chain per iteration
	(``existing_check -> create_todo -> verify -> finalize``) so every node id ``finalize``
	reads from is fresh every iteration, never stale. ``existing_check`` remains the
	primary idempotency guard exactly as ``expected-procedure.md`` specifies (read-before-
	write); ``create_todo`` still receives ``existing_check``'s result and performs a real
	write only when nothing already exists -- it is unconditionally IN the chain (so its
	output is always current) but its OWN internal behaviour is conditional, matching how a
	real "insert-if-not-exists" ERPNext tool would actually be written server-side.
	"""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fetch",
		"contract": _contract(),
		"nodes": [
			{
				"id": "fetch",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_overdue_invoices_for",
					"input": {
						"selected_customers": {"$from": "input.selected_customers"},
						"company": {"$from": "input.company"},
					},
				},
				"next": "loop",
			},
			{
				"id": "loop",
				"type": "foreach",
				"config": {
					"items": {"$from": "fetch"},
					"body": ["qualify", "branch", "existing_check", "create_todo", "verify", "finalize"],
					"collect": {"$from": "finalize"},
					"on_item_error": "fail",
				},
				"next": "summarize",
			},
			{
				"id": "qualify",
				"type": "tool.call",
				"config": {
					"tool_id": "deterministic_qualification_check",
					"input": {"invoice": {"$from": "foreach.item"}},
				},
				"next": "branch",
			},
			{
				"id": "branch",
				"type": "condition",
				"config": {"expression": 'qualify["qualifies"] == True', "on_true": "existing_check", "on_false": "finalize"},
			},
			{
				"id": "existing_check",
				"type": "tool.call",
				"config": {
					"tool_id": "existing_followup_check",
					"input": {
						"reference_type": "Sales Invoice",
						"reference_name": {"$from": "foreach.item.invoice"},
						"allocated_to": {"$from": "input.allocated_to"},
					},
				},
				"next": "create_todo",
			},
			{
				"id": "create_todo",
				"type": "tool.call",
				"config": {
					"tool_id": "create_todo",
					"recovery": create_recovery,
					"input": {
						"reference_type": "Sales Invoice",
						"reference_name": {"$from": "foreach.item.invoice"},
						"allocated_to": {"$from": "input.allocated_to"},
						"idempotency_key": {"$from": "foreach.item.idempotency_key"},
						"operation_key": {"$from": "foreach.item.operation_key"},
						"skip_if_existing": {"$from": "existing_check.existing"},
					},
				},
				"next": "verify",
				"on_error": "finalize",
			},
			{
				"id": "verify",
				"type": "validate",
				"config": {
					"assertions": [
						{
							"expression": 'create_todo["created"] == True or create_todo["already_existed"] == True',
							"code": "NOT_VERIFIED",
							"message": "ToDo was neither created nor found already existing",
						}
					]
				},
				"next": "finalize",
				"on_error": "finalize",
			},
			{
				"id": "finalize",
				"type": "tool.call",
				"config": {
					"tool_id": "mark_row",
					"input": {
						"item": {"$from": "foreach.item"},
						"qualifies": {"$from": "qualify.qualifies"},
						"created": {"$from": "create_todo.created"},
						"already_existed": {"$from": "create_todo.already_existed"},
					},
				},
			},
			{
				"id": "summarize",
				"type": "tool.call",
				"config": {
					"tool_id": "compute_summary",
					"input": {"rows": {"$from": "loop"}, "company": {"$from": "input.company"}},
				},
				"next": "out",
			},
			{"id": "out", "type": "output", "config": {"value": {"$from": "summarize"}}},
		],
	}


_SEED_INVOICES = {
	"CUST-0001": [{"invoice": "SINV-2001"}],
	"CUST-0002": [{"invoice": "SINV-2002"}],
	"CUST-0004": [{"invoice": "SINV-2004"}],
	"CUST-0006": [{"invoice": "SINV-2006A"}, {"invoice": "SINV-2006B"}],
}

_ALLOCATED_TO = "collections@hufretail.example"
_COMPANY = "Huf Retail Pvt Ltd"
_PROCEDURE_NAME = "crm-followup-benchmark-3"
_PROCEDURE_VERSION = "v1"


class _FakeTodoStore:
	"""Stands in for ERPNext's ``ToDo`` doctype (see module docstring: what this proves)."""

	def __init__(self):
		self.rows: list[dict] = [
			{"name": "TODO-3001", "reference_type": "Sales Invoice", "reference_name": "SINV-2002", "allocated_to": _ALLOCATED_TO}
		]
		self._counter = 3002

	def find(self, reference_type: str, reference_name: str, allocated_to: str) -> str | None:
		for row in self.rows:
			if (
				row["reference_type"] == reference_type
				and row["reference_name"] == reference_name
				and row["allocated_to"] == allocated_to
			):
				return row["name"]
		return None

	def create(self, reference_type: str, reference_name: str, allocated_to: str) -> str:
		name = f"TODO-{self._counter}"
		self._counter += 1
		self.rows.append(
			{"name": name, "reference_type": reference_type, "reference_name": reference_name, "allocated_to": allocated_to}
		)
		return name


class _Benchmark3Invoker:
	"""Hand-written fake tool layer (mirrors test_procedure_runtime.py's FakeInvoker).

	``fault_customer_invoice`` names the (customer, invoice) pair whose ``create_todo``
	call raises a simulated transient fault -- but only ``fault_budget`` times total, so a
	later replay call (standing in for "the fault does not repeat", per seed-data.md) goes
	through cleanly.
	"""

	def __init__(self, store: _FakeTodoStore, *, fault_target: tuple[str, str] | None = None, fault_budget: int = 0):
		self.store = store
		self.fault_target = fault_target
		self.fault_budget = fault_budget
		self.calls: list[tuple[str, dict]] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append((tool_id, copy.deepcopy(args)))

		if tool_id == "fetch_overdue_invoices_for":
			rows = []
			for customer in args["selected_customers"]:
				for entry in _SEED_INVOICES.get(customer, []):
					invoice = entry["invoice"]
					target_identity = f"{customer}:{invoice}"
					rows.append(
						{
							"customer_id": customer,
							"invoice": invoice,
							"idempotency_key": derive_idempotency_key(
								procedure_name=_PROCEDURE_NAME,
								procedure_version=_PROCEDURE_VERSION,
								normalised_inputs={"allocated_to": args.get("allocated_to")},
								target_identity=target_identity,
							),
							"operation_key": derive_operation_key(
								procedure_name=_PROCEDURE_NAME, node_id="create_todo", target_identity=target_identity
							),
						}
					)
			return ToolInvocation(tool_id, args, success=True, result=rows)

		if tool_id == "deterministic_qualification_check":
			return ToolInvocation(tool_id, args, success=True, result={"qualifies": True})

		if tool_id == "existing_followup_check":
			existing = self.store.find(args["reference_type"], args["reference_name"], args["allocated_to"])
			return ToolInvocation(tool_id, args, success=True, result={"existing": existing})

		if tool_id == "create_todo":
			# Realistic "insert-if-not-exists" shape: existing_check already ran and its
			# result is passed straight through as skip_if_existing -- when set, this is a
			# genuine no-op (no write, no fault injection, no idempotency race to worry
			# about) rather than a second branch-specific node the graph would need to
			# reach separately.
			if args.get("skip_if_existing"):
				return ToolInvocation(
					tool_id, args, success=True, result={"created": False, "already_existed": True, "name": args["skip_if_existing"]}
				)
			customer_invoice = None
			for customer, entries in _SEED_INVOICES.items():
				for entry in entries:
					if entry["invoice"] == args["reference_name"]:
						customer_invoice = (customer, entry["invoice"])
			if customer_invoice == self.fault_target and self.fault_budget > 0:
				self.fault_budget -= 1
				return ToolInvocation(
					tool_id, args, success=False, error="simulated frappe.db deadlock/timeout (transient)"
				)
			name = self.store.create(args["reference_type"], args["reference_name"], args["allocated_to"])
			return ToolInvocation(tool_id, args, success=True, result={"created": True, "already_existed": False, "name": name})

		if tool_id == "mark_row":
			item = args["item"]
			if not args.get("qualifies"):
				outcome = "skipped_not_qualified"
			elif args.get("already_existed"):
				outcome = "already_existed"
			elif args.get("created"):
				outcome = "created"
			else:
				outcome = "failed"
			return ToolInvocation(
				tool_id, args, success=True, result={"customer_id": item["customer_id"], "invoice": item["invoice"], "outcome": outcome}
			)

		if tool_id == "compute_summary":
			rows = args["rows"]
			outcomes = [r["outcome"] for r in rows if r["outcome"] != "skipped_not_qualified"]
			if not outcomes:
				status = "success"
			elif all(o in ("created", "already_existed") for o in outcomes):
				status = "success"
			elif all(o == "failed" for o in outcomes):
				status = "failure"
			else:
				status = "partial_success"
			return ToolInvocation(tool_id, args, success=True, result={"company": args["company"], "status": status, "rows": rows})

		return ToolInvocation(tool_id, args, success=False, error=f"no such tool {tool_id!r}")


class _WriteClassifier:
	"""Hand-written fake classify_tool -- create_todo is the only write, everything else
	is read. Mirrors huf.ai.graph.permissions.ToolPermission's duck-typed .ptype shape
	without importing that (frappe-backed) module.
	"""

	class _Perm:
		def __init__(self, ptype):
			self.ptype = ptype

	_WRITE_TOOLS = {"create_todo"}

	def __call__(self, tool_id: str):
		return self._Perm("create" if tool_id in self._WRITE_TOOLS else "read")


def _run(store: _FakeTodoStore, *, fault_target=None, fault_budget=0, create_recovery=RECOVERY_RESUME):
	graph = _benchmark3_graph(create_recovery=create_recovery)
	invoker = _Benchmark3Invoker(store, fault_target=fault_target, fault_budget=fault_budget)
	outcome = execute_procedure(
		PinnedVersion.pin(graph),
		{"selected_customers": ["CUST-0001", "CUST-0002", "CUST-0004", "CUST-0006"], "allocated_to": _ALLOCATED_TO, "company": _COMPANY},
		tool_invoker=invoker,
		classify_tool=_WriteClassifier(),
		procedure_name=_PROCEDURE_NAME,
	)
	return outcome, invoker


class Benchmark3WriteRuntimeTests(unittest.TestCase):
	"""End-to-end against benchmark-3-crm-followup's own invariants.py."""

	def setUp(self):
		self.invariants = _load_invariants()
		self.fake_frappe = _install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_write_node_without_recovery_mode_fails_closed(self):
		graph = _benchmark3_graph(create_recovery="not-a-real-mode")
		# Drop the node's own on_error escape hatch for this test -- it exists so a
		# genuine transient tool fault doesn't abort the whole run (see the graph's
		# docstring), but that same routing would also quietly absorb a *runtime-level*
		# fail-closed rejection (missing/invalid recovery) into a normal "failed" row.
		# This test wants to observe the rejection itself, at the top level.
		for node in graph["nodes"]:
			if node["id"] == "create_todo":
				del node["on_error"]
		store = _FakeTodoStore()
		invoker = _Benchmark3Invoker(store)
		outcome = execute_procedure(
			PinnedVersion.pin(graph),
			{"selected_customers": ["CUST-0001"], "allocated_to": _ALLOCATED_TO, "company": _COMPANY},
			tool_invoker=invoker,
			classify_tool=_WriteClassifier(),
			procedure_name=_PROCEDURE_NAME,
		)
		# create_todo is reached (SINV-2001 has no prior ToDo, qualifies), and its
		# undeclared recovery mode must fail the node closed rather than guessing one.
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("recovery", outcome.error)
		self.assertEqual(len(store.rows), 1)  # unchanged: only the pre-seeded TODO-3001

	def test_write_node_without_idempotency_key_fails_closed(self):
		graph = _benchmark3_graph()
		# Strip idempotency_key from the create_todo node's input to prove D5 is enforced,
		# and drop its on_error escape hatch for the same reason as the test above.
		for node in graph["nodes"]:
			if node["id"] == "create_todo":
				del node["config"]["input"]["idempotency_key"]
				del node["on_error"]
		store = _FakeTodoStore()
		invoker = _Benchmark3Invoker(store)
		outcome = execute_procedure(
			PinnedVersion.pin(graph),
			{"selected_customers": ["CUST-0001"], "allocated_to": _ALLOCATED_TO, "company": _COMPANY},
			tool_invoker=invoker,
			classify_tool=_WriteClassifier(),
			procedure_name=_PROCEDURE_NAME,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.FAILED)
		self.assertIn("idempotency_key", outcome.error)
		self.assertEqual(len(store.rows), 1)  # unchanged: only the pre-seeded TODO-3001

	def _first_run_mid_write_failure(self):
		store = _FakeTodoStore()
		outcome, invoker = _run(store, fault_target=("CUST-0006", "SINV-2006B"), fault_budget=1)

		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)  # the run itself completes...
		result = outcome.output
		self.assertEqual(result["status"], "partial_success")  # ...reporting partial_success (never rounded up/down)

		for fn in self.invariants.ALL_INVARIANTS:
			fn(result, {"CUST-0001", "CUST-0002", "CUST-0004", "CUST-0006"}) if fn is self.invariants.assert_customer_ids_preserved else (
				fn(result, {"CUST-0003", "CUST-0005", "CUST-0009"}) if fn is self.invariants.assert_no_unauthorized_records else fn(result)
			)

		outcomes_by_invoice = {row["invoice"]: row["outcome"] for row in result["rows"]}
		self.assertEqual(
			outcomes_by_invoice,
			{
				"SINV-2001": "created",
				"SINV-2002": "already_existed",
				"SINV-2004": "created",
				"SINV-2006A": "created",
				"SINV-2006B": "failed",
			},
		)
		# Exactly 4 ToDos exist after the first (faulted) run -- TODO-3001 pre-existed for
		# SINV-2002, plus the three that were newly created; SINV-2006B never committed.
		self.assertEqual(len(store.rows), 4)
		self.invariants.assert_no_duplicate_todos(store.rows)
		return store  # used by the recovery test below

	def test_first_run_mid_write_failure_is_partial_success(self):
		self._first_run_mid_write_failure()

	def test_recovery_run_heals_without_duplicating(self):
		store = self._first_run_mid_write_failure()
		store_after_run1 = copy.deepcopy(store.rows)

		# Recovery: same input, replayed. The fault does not repeat (fault_budget=0 this
		# time -- seed-data.md: "fault was transient and does not repeat").
		outcome2, invoker2 = _run(store, fault_target=None, fault_budget=0)

		self.assertEqual(outcome2.status, ProcedureOutcome.SUCCESS)
		result2 = outcome2.output
		self.assertEqual(result2["status"], "success")  # GOAL.md ss2.4: honest aggregate, no partial left over
		self.invariants.assert_run_status_reflects_rows(result2)

		outcomes_by_invoice = {row["invoice"]: row["outcome"] for row in result2["rows"]}
		self.assertEqual(outcomes_by_invoice["SINV-2006B"], "created")
		for invoice in ("SINV-2001", "SINV-2002", "SINV-2004", "SINV-2006A"):
			self.assertEqual(outcomes_by_invoice[invoice], "already_existed")

		# The core cross-run idempotency invariant (invariants.py): recovery must not lose
		# or duplicate writes. Exactly 5 ToDos total for these five invoices, never 4, never 6+.
		self.assertEqual(len(store.rows), 5)
		self.invariants.assert_idempotent_across_runs(store_after_run1, store.rows)

	def test_third_run_after_full_success_creates_nothing_new(self):
		store = self._first_run_mid_write_failure()
		_run(store, fault_target=None, fault_budget=0)  # recovery run
		store_after_recovery = copy.deepcopy(store.rows)

		outcome3, _ = _run(store, fault_target=None, fault_budget=0)  # duplicate invocation, no fault, nothing new to do
		self.assertEqual(outcome3.status, ProcedureOutcome.SUCCESS)
		result3 = outcome3.output
		self.assertEqual(result3["status"], "success")
		self.assertTrue(all(row["outcome"] == "already_existed" for row in result3["rows"]))

		self.assertEqual(len(store.rows), 5)  # unchanged -- a third, fully-redundant invocation creates nothing
		self.invariants.assert_idempotent_across_runs(store_after_recovery, store.rows)


class ConcurrentDuplicateReservationTests(unittest.TestCase):
	"""The reservation's actual job: closing a truly CONCURRENT race.

	Sequential replays (checkpoint-resume, a duplicate Procedure invocation after full
	success) are proven safe by ``Benchmark3WriteRuntimeTests`` above via the graph's own
	``existing_followup_check`` -- the runtime releases its reservation promptly on every
	normal path (see idempotency.py "Dedup window"), so those never collide with the
	reservation at all. This test proves the narrower case the reservation exists for: a
	second attempt for the exact same key that is CONCURRENT with (or crashed mid-way,
	leaving a stuck hold during) a first one. Simulated here by reserving the key directly
	via :func:`reserve_idempotency_key` *before* running the graph -- standing in for
	"another worker is mid-flight on this exact write right now."
	"""

	def setUp(self):
		self.fake_frappe = _install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_key_held_by_another_attempt_short_circuits_as_duplicate_no_write(self):
		store = _FakeTodoStore()
		target_identity = "CUST-0001:SINV-2001"
		key = derive_idempotency_key(
			procedure_name=_PROCEDURE_NAME,
			procedure_version=_PROCEDURE_VERSION,
			# Must match exactly how _Benchmark3Invoker.fetch_overdue_invoices_for derives
			# it: normalised against the args THAT tool call actually receives (which does
			# not include allocated_to -- that argument only reaches existing_check /
			# create_todo later in the chain), so "allocated_to" is None here, not the
			# real value, to reproduce the identical key the graph itself will compute.
			normalised_inputs={"allocated_to": None},
			target_identity=target_identity,
		)
		# Simulate another attempt already holding this exact key (a concurrent worker
		# mid-write, or a crashed attempt that has not yet hit its TTL).
		self.assertTrue(reserve_idempotency_key(key, window_seconds=3600))

		outcome, invoker = _run(store, fault_target=None, fault_budget=0)

		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		outcomes_by_invoice = {row["invoice"]: row["outcome"] for row in outcome.output["rows"]}
		# create_todo never actually ran for SINV-2001 -- the runtime's own dedup
		# reservation intercepted it before the tool was invoked at all -- so verify's
		# assertion (create_todo.created or already_existed) cannot pass, and this row
		# correctly reports "failed" rather than silently fabricating "created". This is
		# the honest outcome: a genuinely concurrent collision is not the same as an
		# idempotent no-op, and this module does not pretend otherwise.
		self.assertEqual(outcomes_by_invoice["SINV-2001"], "failed")
		# No write happened for SINV-2001 -- the reservation did its one job.
		self.assertIsNone(store.find("Sales Invoice", "SINV-2001", _ALLOCATED_TO))
		# All other (non-colliding) invoices in this run proceed normally.
		self.assertEqual(outcomes_by_invoice["SINV-2004"], "created")

		create_todo_calls = [args for tool_id, args in invoker.calls if tool_id == "create_todo"]
		self.assertFalse(
			any(a.get("reference_name") == "SINV-2001" for a in create_todo_calls),
			"create_todo must never be invoked for a key another attempt is actively holding",
		)


class RetryRecoveryModeTests(unittest.TestCase):
	"""RECOVERY_RETRY: bounded, exactly-one inline retry, distinct from RECOVERY_RESUME."""

	def setUp(self):
		self.fake_frappe = _install_fake_frappe()
		self.addCleanup(_restore_real_stub)

	def test_retry_heals_a_single_transient_fault_within_one_run(self):
		store = _FakeTodoStore()
		# fault_budget=1: the FIRST invocation of create_todo for SINV-2001 fails, the
		# inline retry (bounded to exactly one extra attempt) succeeds -- all within this
		# one execute_procedure call, no second run needed.
		outcome, invoker = _run(
			store, fault_target=("CUST-0001", "SINV-2001"), fault_budget=1, create_recovery=RECOVERY_RETRY
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS)
		result = outcome.output
		self.assertEqual(result["status"], "success")
		outcomes_by_invoice = {row["invoice"]: row["outcome"] for row in result["rows"]}
		self.assertEqual(outcomes_by_invoice["SINV-2001"], "created")

	def test_retry_modes_are_the_declared_set(self):
		self.assertEqual(set(RECOVERY_MODES), {"retry", "resume", "abort", "compensate"})


if __name__ == "__main__":
	unittest.main()
