# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Benchmark 4 (reconciliation, batch scale) run against the T-30 concurrent runtime.

Frappe-free, standalone, no bench (mirrors test_procedure_runtime.py's benchmark-1 harness).
The tool layer is SIMULATED: a hand-written fake invoker returns the exact seed-data rows from
$TRACK/benchmarks/benchmark-4-reconciliation/seed-data.md and, for ``classify_payment``, performs
the candidate-matching algorithm described in expected-procedure.md (single exact matches plus
bounded 2-3 invoice combinations) directly in Python. This proves the RUNTIME's scheduling,
bounds, and determinism under simulated I/O latency (a ``parallel`` fan-out for the two batched
fetches, feeding a bounded ``foreach`` over payments) -- it does NOT prove real ERPNext batching/
paging behaviour, real network timeout behaviour, or real multi-connection Frappe DB behaviour
under load. Two things this fixture deliberately does not exercise: the fetch nodes here return
their full seed page in one simulated call rather than genuinely paging in ``batch_size`` chunks
(the Procedure IR's ``tool.call`` node does not itself express pagination; a real batching runtime
would page via ``foreach`` over page numbers, out of scope for this proof), and the internal
``validate no_duplicate_allocation`` / ``outstanding_unchanged`` steps from expected-procedure.md
are represented by one scope-check ``validate`` node here -- the duplicate/total checks are
performed by benchmark-4's own ``invariants.py`` against the final output, which is what this test
actually asserts against.
"""

from __future__ import annotations

import importlib.util
import itertools
import sys
import unittest
from pathlib import Path

from huf.ai.graph.executor import PinnedVersion
from huf.ai.graph.procedure_runtime import ProcedureOutcome, ToolInvocation, execute_procedure


def _find_benchmark_4_dir() -> Path | None:
	here = Path(__file__).resolve()
	for parent in here.parents:
		candidate = parent / "benchmarks" / "benchmark-4-reconciliation"
		if (candidate / "invariants.py").exists():
			return candidate
	return None


_BENCHMARK_4_DIR = _find_benchmark_4_dir()


def _load_invariants():
	if _BENCHMARK_4_DIR is None:
		raise unittest.SkipTest(
			"benchmarks/benchmark-4-reconciliation/invariants.py not found relative to this file"
		)
	spec = importlib.util.spec_from_file_location("benchmark4_invariants", _BENCHMARK_4_DIR / "invariants.py")
	module = importlib.util.module_from_spec(spec)
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


COMPANY = "Huf Retail Pvt Ltd"
CURRENCY = "INR"

_INVOICES = [
	{"name": "SINV-4001", "customer": "CUST-0001", "outstanding_amount": 5000.00, "company": COMPANY},
	{"name": "SINV-4002", "customer": "CUST-0001", "outstanding_amount": 9000.00, "company": COMPANY},
	{"name": "SINV-4010", "customer": "CUST-0002", "outstanding_amount": 12000.00, "company": COMPANY},
	{"name": "SINV-4011", "customer": "CUST-0002", "outstanding_amount": 12000.00, "company": COMPANY},
	{"name": "SINV-4020", "customer": "CUST-0004", "outstanding_amount": 7000.00, "company": COMPANY},
	{"name": "SINV-4021", "customer": "CUST-0004", "outstanding_amount": 8000.00, "company": COMPANY},
	{"name": "SINV-4022", "customer": "CUST-0004", "outstanding_amount": 15000.00, "company": COMPANY},
	{"name": "SINV-4030", "customer": "CUST-0006", "outstanding_amount": 4500.00, "company": COMPANY},
	{"name": "SINV-4031", "customer": "CUST-0006", "outstanding_amount": 6200.00, "company": COMPANY},
	{"name": "SINV-4040", "customer": "CUST-0007", "outstanding_amount": 22000.00, "company": COMPANY},
	{"name": "SINV-4050", "customer": "CUST-0008", "outstanding_amount": 3000.00, "company": COMPANY},
	{"name": "SINV-4051", "customer": "CUST-0008", "outstanding_amount": 3000.00, "company": COMPANY},
	{"name": "SINV-4052", "customer": "CUST-0008", "outstanding_amount": 3000.00, "company": COMPANY},
	{"name": "SINV-4060", "customer": "CUST-0003", "outstanding_amount": 12000.00, "company": COMPANY},
	{"name": "SINV-9010", "customer": "CUST-0009", "outstanding_amount": 5000.00, "company": "Globex Overseas"},
]

_PAYMENTS = [
	{"name": "PE-4001", "customer": "CUST-0001", "amount": 5000.00, "company": COMPANY},
	{"name": "PE-4002", "customer": "CUST-0001", "amount": 9000.00, "company": COMPANY},
	{"name": "PE-4010", "customer": "CUST-0002", "amount": 12000.00, "company": COMPANY},
	{"name": "PE-4020", "customer": "CUST-0004", "amount": 15000.00, "company": COMPANY},
	{"name": "PE-4030", "customer": "CUST-0006", "amount": 4500.00, "company": COMPANY},
	{"name": "PE-4040", "customer": "CUST-0007", "amount": 22000.00, "company": COMPANY},
	{"name": "PE-4050", "customer": "CUST-0008", "amount": 3000.00, "company": COMPANY},
	{"name": "PE-4099", "customer": "CUST-0003", "amount": 9999.00, "company": COMPANY},
	{"name": "PE-9099", "customer": "CUST-0009", "amount": 5000.00, "company": "Globex Overseas"},
]


def _classify_payment(args: dict) -> dict:
	"""The fake invoker's ``classify_payment`` tool: the candidate-matching algorithm from
	expected-procedure.md, implemented directly (simulated tool layer -- see module docstring).
	"""
	payment = args["payment"]
	invoices = [inv for inv in args["invoices"] if inv["customer"] == payment["customer"]]

	singles = [inv["name"] for inv in invoices if abs(inv["outstanding_amount"] - payment["amount"]) < 0.01]
	combos = []
	for size in (2, 3):
		for combo in itertools.combinations(invoices, size):
			if abs(sum(inv["outstanding_amount"] for inv in combo) - payment["amount"]) < 0.01:
				combos.append("+".join(inv["name"] for inv in combo))

	candidates = singles + combos
	row = {"payment": payment["name"], "customer": payment["customer"], "amount": payment["amount"]}
	if not candidates:
		row["classification"] = "unmatched"
	elif len(candidates) == 1 and candidates[0] in singles:
		row["classification"] = "resolved"
		row["matched_invoice"] = candidates[0]
	else:
		row["classification"] = "ambiguous"
		row["candidates"] = candidates
	return row


class Benchmark4Invoker:
	def __init__(self):
		self.calls: list[tuple[str, dict]] = []

	def __call__(self, tool_id: str, args: dict) -> ToolInvocation:
		self.calls.append((tool_id, args))
		if tool_id == "fetch_open_invoices_batched":
			return ToolInvocation(tool_id, args, success=True, result=list(_INVOICES))
		if tool_id == "fetch_unallocated_payments_batched":
			return ToolInvocation(tool_id, args, success=True, result=list(_PAYMENTS))
		if tool_id == "classify_payment":
			return ToolInvocation(tool_id, args, success=True, result=_classify_payment(args))
		return ToolInvocation(tool_id, args, success=False, error=f"no such tool {tool_id!r}")


def _benchmark_4_graph() -> dict:
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fan_out",
		"contract": {
			"limits": {
				"max_nodes": 500,
				"max_rows": 500,
				"max_output_bytes": 500_000,
				"max_parallel_calls": 4,
				"max_foreach_iterations": 50,
				"max_external_calls": 50,
			}
		},
		"nodes": [
			{
				"id": "fan_out",
				"type": "parallel",
				"config": {
					"branches": [["fetch_invoices"], ["fetch_payments"]],
					"join": "all",
					"max_parallel_calls": 2,
				},
				"next": "scope_invoices",
			},
			{
				"id": "fetch_invoices",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_open_invoices_batched",
					"input": {"company": {"$from": "input.company"}, "batch_size": 10},
				},
			},
			{
				"id": "fetch_payments",
				"type": "tool.call",
				"config": {
					"tool_id": "fetch_unallocated_payments_batched",
					"input": {"company": {"$from": "input.company"}, "batch_size": 10},
				},
			},
			{
				"id": "scope_invoices",
				"type": "transform",
				"config": {
					"op": "filter",
					"input": {"rows": {"$from": "fetch_invoices"}, "where": 'row["company"] == "Huf Retail Pvt Ltd"'},
				},
				"next": "scope_payments",
			},
			{
				"id": "scope_payments",
				"type": "transform",
				"config": {
					"op": "filter",
					"input": {"rows": {"$from": "fetch_payments"}, "where": 'row["company"] == "Huf Retail Pvt Ltd"'},
				},
				"next": "total_outstanding",
			},
			{
				"id": "total_outstanding",
				"type": "transform",
				"config": {
					"op": "aggregate",
					"input": {"rows": {"$from": "scope_invoices"}, "op": "sum", "field": "outstanding_amount"},
				},
				"next": "scope_check",
			},
			{
				"id": "scope_check",
				"type": "validate",
				"config": {
					"assertions": [
						{
							"expression": 'input["company"] == "Huf Retail Pvt Ltd"',
							"code": "COMPANY_SCOPE",
							"message": "run must be scoped to Huf Retail Pvt Ltd",
						}
					]
				},
				"next": "classify_all",
			},
			{
				"id": "classify_all",
				"type": "foreach",
				"config": {
					"items": {"$from": "scope_payments"},
					"max_iterations": 20,
					"body": ["classify_payment"],
					"collect": {"$from": "classify_payment"},
					"on_item_error": "fail",
				},
				"next": "resolved_rows",
			},
			{
				"id": "classify_payment",
				"type": "tool.call",
				"config": {
					"tool_id": "classify_payment",
					"input": {"payment": {"$from": "foreach.item"}, "invoices": {"$from": "scope_invoices"}},
				},
			},
			{
				"id": "resolved_rows",
				"type": "transform",
				"config": {
					"op": "filter",
					"input": {"rows": {"$from": "classify_all"}, "where": 'row["classification"] == "resolved"'},
				},
				"next": "ambiguous_rows",
			},
			{
				"id": "ambiguous_rows",
				"type": "transform",
				"config": {
					"op": "filter",
					"input": {"rows": {"$from": "classify_all"}, "where": 'row["classification"] == "ambiguous"'},
				},
				"next": "unmatched_rows",
			},
			{
				"id": "unmatched_rows",
				"type": "transform",
				"config": {
					"op": "filter",
					"input": {"rows": {"$from": "classify_all"}, "where": 'row["classification"] == "unmatched"'},
				},
				"next": "out",
			},
			{
				"id": "out",
				"type": "output",
				"config": {
					"value": {
						"company": {"$from": "input.company"},
						"currency": CURRENCY,
						"total_outstanding": {"$from": "total_outstanding"},
						"resolved": {"$from": "resolved_rows"},
						"ambiguous": {"$from": "ambiguous_rows"},
						"unmatched": {"$from": "unmatched_rows"},
					}
				},
			},
		],
	}


class TestBenchmark4Reconciliation(unittest.TestCase):
	def test_runtime_output_satisfies_all_benchmark_4_invariants(self):
		invariants = _load_invariants()
		graph = _benchmark_4_graph()
		invoker = Benchmark4Invoker()
		outcome = execute_procedure(
			PinnedVersion(graph=graph, fingerprint="benchmark-4"),
			{"company": COMPANY, "date_from": "2026-07-01", "date_to": "2026-08-23"},
			tool_invoker=invoker,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS, outcome.error)
		result = outcome.output

		valid_customers = {
			"CUST-0001", "CUST-0002", "CUST-0003", "CUST-0004", "CUST-0006", "CUST-0007", "CUST-0008",
		}
		excluded = {"CUST-0009", "PE-9099", "SINV-9010"}

		for fn in invariants.ALL_INVARIANTS:
			if fn is invariants.assert_total_outstanding_preserved:
				# seed-data.md sums its own 14-row invoice table to 121700.00 but states the
				# total as 122700.00 -- a documentation arithmetic error in the fixture
				# (verified independently, see final report), not a runtime discrepancy.
				fn(result, expected_total=121700.00)
			elif fn is invariants.assert_customer_ids_preserved:
				fn(result, valid_customer_ids=valid_customers)
			elif fn is invariants.assert_no_unauthorized_records:
				fn(result, excluded_ids=excluded)
			elif fn is invariants.assert_classification_counts:
				fn(result, expected_resolved=4, expected_ambiguous=3, expected_unmatched=1)
			else:
				fn(result)

		# Batch-scale telemetry floor (expected-procedure.md): at least 2 batched fetches +
		# 9 in-scope-and-distractor per-payment classification calls were issued (the
		# distractor payment PE-9099 is fetched, then scoped OUT before foreach -- it is
		# never classified, which is itself part of the scope proof).
		classify_calls = [c for t, c in invoker.calls if t == "classify_payment"]
		self.assertEqual(len(classify_calls), 8)  # 9 payments minus the 1 distractor scoped out

	def test_two_fetch_branches_ran_under_the_parallel_scheduler(self):
		"""Sanity check that fan_out really is a T-30 parallel node (both branches recorded,
		regardless of order) rather than accidentally falling back to a single tool call.
		"""
		graph = _benchmark_4_graph()
		invoker = Benchmark4Invoker()
		outcome = execute_procedure(
			PinnedVersion(graph=graph, fingerprint="benchmark-4"),
			{"company": COMPANY, "date_from": "2026-07-01", "date_to": "2026-08-23"},
			tool_invoker=invoker,
		)
		self.assertEqual(outcome.status, ProcedureOutcome.SUCCESS, outcome.error)
		fetch_tools = {t for t, _ in invoker.calls if t.startswith("fetch_")}
		self.assertEqual(fetch_tools, {"fetch_open_invoices_batched", "fetch_unallocated_payments_batched"})


if __name__ == "__main__":
	unittest.main()
