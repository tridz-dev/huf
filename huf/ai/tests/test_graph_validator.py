# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.graph.validator (T-24).

Pure unit tests, no frappe calls beyond what ``huf.ai.graph.permissions`` needs at import time
(stubbed below exactly as ``test_graph_permissions.py`` does) and beyond what
``compute_static_envelope`` needs (``classify_tool`` is always a fake in these tests, never the
frappe-backed default).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_graph_validator
"""

import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_standalone_frappe_stub():
	"""See test_graph_permissions.py for the full rationale -- huf/__init__.py does an
	unconditional ``import frappe`` before conftest.py's stub has a chance to run, so this test
	module installs its own narrow fake when frappe isn't the genuine package."""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph.permissions import ToolPermission
from huf.ai.graph.validator import (
	POLICY_LIMIT_CEILINGS,
	ValidationError,
	ValidationResult,
	validate_graph,
)

# ----------------------------------------------------------------------------------
# Shared fixture plumbing -- benchmark graphs, matching spec/graph-ir.md worked examples and
# Tracks/.../benchmarks/*/expected-procedure.md shapes (same shapes T-14's tests use).
# ----------------------------------------------------------------------------------

_VALID_LIMITS = {
	"max_nodes": 50,
	"max_rows": 10_000,
	"max_output_bytes": 1_000_000,
	"max_parallel_calls": 4,
	"max_foreach_iterations": 200,
	"max_external_calls": 100,
	"max_writes": 10,
	"max_wall_time_ms": 60_000,
	"fail_closed": True,
}


def _envelope(read=(), write=(), http="none", code="none"):
	return {
		"read": [{"doctype": d} for d in read],
		"write": [{"doctype": d} for d in write],
		"http": http,
		"code": code,
	}


def _contract(*, read=(), write=(), http="none", code="none", limits=None):
	return {
		"input_schema": {},
		"output_schema": {},
		"applies_when": [],
		"permission_envelope": _envelope(read=read, write=write, http=http, code=code),
		"limits": limits if limits is not None else dict(_VALID_LIMITS),
	}


def _graph(nodes, entry, *, profile="procedure", contract=None, fingerprint=None):
	return {
		"schema_version": "1.0.0",
		"profile": profile,
		"fingerprint": fingerprint or ("a" * 64),
		"entry": entry,
		"nodes": nodes,
		"contract": contract if contract is not None else _contract(),
	}


def _node(id_, type_, config=None, next_=None, on_error=None):
	node = {"id": id_, "type": type_, "config": config or {}}
	if next_ is not None:
		node["next"] = next_
	if on_error is not None:
		node["on_error"] = on_error
	return node


# tool_id -> ToolPermission, standing in for the Agent Tool Function doctype lookup, matching
# test_graph_permissions.py's table so envelope-derivation results agree between T-14 and T-24.
_FAKE_TOOL_TABLE = {
	"erpnext.get_sales_invoices": ToolPermission(ptype="read", doctype="Sales Invoice"),
	"erpnext.get_payment_entries": ToolPermission(ptype="read", doctype="Payment Entry"),
	"erpnext.get_customer": ToolPermission(ptype="read", doctype="Customer"),
	"erpnext.get_overdue_invoices": ToolPermission(ptype="read", doctype="Sales Invoice"),
	"erpnext.fetch_overdue_invoices_for": ToolPermission(ptype="read", doctype="Sales Invoice"),
	"erpnext.deterministic_qualification_check": ToolPermission(ptype=None, doctype=None),
	"erpnext.existing_followup_check": ToolPermission(ptype="read", doctype="ToDo"),
	"erpnext.create_todo": ToolPermission(ptype="create", doctype="ToDo"),
	"erpnext.fetch_open_invoices_batched": ToolPermission(ptype="read", doctype="Sales Invoice"),
	"erpnext.fetch_unallocated_payments_batched": ToolPermission(ptype="read", doctype="Payment Entry"),
}


def _fake_classify_tool(tool_id: str) -> ToolPermission:
	return _FAKE_TOOL_TABLE.get(tool_id, ToolPermission(ptype=None, doctype=None))


def _validate(graph, profile="procedure"):
	return validate_graph(graph, profile, classify_tool=_fake_classify_tool)


# ----------------------------------------------------------------------------------
# The four T-03 benchmark fixtures -- done-when requirement: all four validate.
# ----------------------------------------------------------------------------------


def benchmark1_graph():
	"""Straight tool.call chain -- spec/graph-ir.md section 9.1, verbatim shape."""
	nodes = [
		_node(
			"load_invoices", "tool.call",
			{"tool_id": "erpnext.get_sales_invoices", "input": {}},
			next_="load_payments",
		),
		_node(
			"load_payments", "tool.call",
			{"tool_id": "erpnext.get_payment_entries", "input": {}},
			next_="load_customer",
		),
		_node(
			"load_customer", "tool.call",
			{"tool_id": "erpnext.get_customer", "input": {}},
			next_="emit",
		),
		_node("emit", "output", {"value": {}}),
	]
	contract = _contract(read=["Customer", "Payment Entry", "Sales Invoice"])
	return _graph(nodes, "load_invoices", contract=contract)


def benchmark2_graph():
	"""foreach containing a nested parallel -- benchmark-2-collection-prioritization."""
	nodes = [
		_node(
			"load_overdue", "tool.call",
			{"tool_id": "erpnext.get_overdue_invoices", "input": {}},
			next_="group_by_customer",
		),
		_node(
			"group_by_customer", "transform",
			{"op": "group_by", "input": {"rows": {"$from": "load_overdue.rows"}, "key": "customer"}},
			next_="per_customer",
		),
		_node(
			"per_customer", "foreach",
			{
				"items": {"$from": "group_by_customer.rows"},
				"item_var": "customer_id",
				"max_iterations": 200,
				"body": ["fan_out", "aggregate_row"],
				"collect": {"$from": "aggregate_row.summary"},
				"on_item_error": "fail",
			},
			next_="sort_rows",
		),
		_node(
			"fan_out", "parallel",
			{
				"max_parallel_calls": 4,
				"join": "all",
				"branches": [["fetch_customer"], ["fetch_payment_history"]],
			},
			next_="aggregate_row",
		),
		_node(
			"fetch_customer", "tool.call",
			{"tool_id": "erpnext.get_customer", "input": {}},
		),
		_node(
			"fetch_payment_history", "tool.call",
			{"tool_id": "erpnext.get_payment_entries", "input": {}},
		),
		_node(
			"aggregate_row", "transform",
			{"op": "aggregate", "input": {"rows": {"$from": "fetch_payment_history.rows"}, "op": "sum"}},
		),
		_node(
			"sort_rows", "transform",
			{"op": "sort", "input": {"rows": {"$from": "per_customer"}, "key": "total"}},
			next_="emit",
		),
		_node("emit", "output", {"value": {"$from": "sort_rows.rows"}}),
	]
	contract = _contract(read=["Customer", "Payment Entry", "Sales Invoice"])
	return _graph(nodes, "load_overdue", contract=contract)


def benchmark3_graph():
	"""foreach containing nested conditions -- benchmark-3-crm-followup."""
	nodes = [
		_node(
			"fetch_invoices", "tool.call",
			{"tool_id": "erpnext.fetch_overdue_invoices_for", "input": {}},
			next_="per_invoice",
		),
		_node(
			"per_invoice", "foreach",
			{
				"items": {"$from": "fetch_invoices.rows"},
				"item_var": "invoice",
				"max_iterations": 200,
				"body": ["qualify", "check_qualified"],
				"collect": {"$from": "check_qualified"},
				"on_item_error": "fail",
			},
			next_="emit",
		),
		_node(
			"qualify", "tool.call",
			{"tool_id": "erpnext.deterministic_qualification_check", "input": {}},
			next_="check_qualified",
		),
		_node(
			"check_qualified", "condition",
			{
				"expression": 'row["qualifies"] == True',
				"on_true": "check_existing",
				"on_false": "mark_skipped",
			},
		),
		_node(
			"check_existing", "tool.call",
			{"tool_id": "erpnext.existing_followup_check", "input": {}},
			next_="branch_on_existing",
		),
		_node(
			"branch_on_existing", "condition",
			{
				"expression": 'row["existing"] != None',
				"on_true": "mark_existed",
				"on_false": "create_todo",
			},
		),
		_node("mark_existed", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node(
			"create_todo", "tool.call",
			{"tool_id": "erpnext.create_todo", "input": {}},
			next_="verify_created",
		),
		_node(
			"verify_created", "validate",
			{
				"assertions": [
					{"expression": 'row["created"] == True', "code": "TODO_NOT_CREATED", "message": "todo missing"},
				]
			},
			next_="mark_created",
		),
		_node("mark_created", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node("mark_skipped", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node("emit", "output", {"value": {}}),
	]
	contract = _contract(read=["Sales Invoice", "ToDo"], write=["ToDo"])
	return _graph(nodes, "fetch_invoices", contract=contract)


def benchmark4_graph():
	"""Two independent tool.call roots feeding a foreach with nested conditions."""
	nodes = [
		_node(
			"fetch_invoices", "tool.call",
			{"tool_id": "erpnext.fetch_open_invoices_batched", "input": {}},
			next_="fetch_payments",
		),
		_node(
			"fetch_payments", "tool.call",
			{"tool_id": "erpnext.fetch_unallocated_payments_batched", "input": {}},
			next_="flatten",
		),
		_node(
			"flatten", "transform",
			{"op": "join", "input": {
				"left": {"$from": "fetch_invoices.rows"},
				"right": {"$from": "fetch_payments.rows"},
				"left_key": "name",
				"right_key": "invoice",
				"how": "left",
			}},
			next_="index",
		),
		_node("index", "transform", {"op": "distinct", "input": {"rows": {"$from": "flatten.rows"}}}, next_="per_payment"),
		_node(
			"per_payment", "foreach",
			{
				"items": {"$from": "index.rows"},
				"item_var": "payment",
				"max_iterations": 200,
				"body": ["find_candidates", "branch_on_candidates"],
				"collect": {"$from": "branch_on_candidates"},
				"on_item_error": "fail",
			},
			next_="validate_dupes",
		),
		_node(
			"find_candidates", "transform",
			{"op": "filter", "input": {"rows": {"$from": "foreach.item"}, "where": "True", "candidate_count": 0}},
			next_="branch_on_candidates",
		),
		_node(
			"branch_on_candidates", "condition",
			{
				"expression": 'row["candidate_count"] == 0',
				"on_true": "mark_unmatched",
				"on_false": "branch_on_single_match",
			},
		),
		_node("mark_unmatched", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node(
			"branch_on_single_match", "condition",
			{
				"expression": 'row["candidate_count"] == 1',
				"on_true": "mark_resolved",
				"on_false": "mark_ambiguous",
			},
		),
		_node("mark_resolved", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node("mark_ambiguous", "transform", {"op": "coalesce", "input": {"values": []}}),
		_node(
			"validate_dupes", "validate",
			{
				"assertions": [
					{"expression": "True", "code": "NO_DUPLICATE_ALLOCATION", "message": "duplicate allocation"},
				]
			},
			next_="emit",
		),
		_node("emit", "output", {"value": {}}),
	]
	contract = _contract(read=["Payment Entry", "Sales Invoice"])
	return _graph(nodes, "fetch_invoices", contract=contract)


class TestBenchmarksValidateUnderProcedureProfile(unittest.TestCase):
	"""Done-when requirement: all four T-03 benchmark fixtures validate under the procedure
	profile, and a passing result carries a derived permission envelope."""

	def test_benchmark1(self):
		result = _validate(benchmark1_graph())
		self.assertTrue(result.ok, msg=[str(e) for e in result.errors])
		self.assertIsNotNone(result.envelope)

	def test_benchmark2(self):
		result = _validate(benchmark2_graph())
		self.assertTrue(result.ok, msg=[str(e) for e in result.errors])

	def test_benchmark3(self):
		result = _validate(benchmark3_graph())
		self.assertTrue(result.ok, msg=[str(e) for e in result.errors])

	def test_benchmark4(self):
		result = _validate(benchmark4_graph())
		self.assertTrue(result.ok, msg=[str(e) for e in result.errors])


# ----------------------------------------------------------------------------------
# Rejection corpus -- each proves one specific, structurally-enforced invariant.
# ----------------------------------------------------------------------------------


class TestRejectionCorpus(unittest.TestCase):
	def _assert_rejected(self, graph, profile="procedure", *, code=None):
		result = _validate(graph, profile=profile)
		self.assertFalse(result.ok)
		self.assertTrue(result.errors, "a rejection must always carry at least one specific reason")
		for err in result.errors:
			self.assertIsInstance(err, ValidationError)
			self.assertTrue(err.message)
		self.assertIsNone(result.envelope, "a rejected graph must never carry a derived envelope")
		if code is not None:
			self.assertTrue(
				any(err.code == code for err in result.errors),
				f"expected an error with code {code!r}, got {[e.code for e in result.errors]}",
			)
		return result

	def test_dynamic_tool_dispatch_is_rejected(self):
		"""tool_id as a Reference instead of a literal string -- the exact 'dynamic dispatch'
		example graph-ir.md section 6 calls out as structurally impossible; the schema itself
		has no member that accepts an object here."""
		nodes = [
			_node("pick_tool", "transform", {"op": "coalesce", "input": {"values": ["erpnext.get_customer"]}}, next_="call_it"),
			_node(
				"call_it", "tool.call",
				{"tool_id": {"$from": "pick_tool.value"}, "input": {}},
				next_="emit",
			),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "pick_tool")
		self._assert_rejected(graph, code="SCHEMA")

	def test_flow_only_node_under_procedure_profile_is_rejected(self):
		"""agent.run -- an I4 violation (no LLM inside Procedure execution) -- submitted under
		the procedure profile must be rejected, not silently accepted because the Flow profile
		would have allowed it."""
		nodes = [
			_node(
				"ask_llm", "agent.run",
				{"agent": "some-agent", "prompt": "decide something"},
				next_="emit",
			),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "ask_llm")
		self._assert_rejected(graph, code="SCHEMA")

	def test_cycle_is_rejected(self):
		nodes = [
			_node("a", "transform", {"op": "coalesce", "input": {"values": []}}, next_="b"),
			_node("b", "transform", {"op": "coalesce", "input": {"values": []}}, next_="a"),
		]
		graph = _graph(nodes, "a")
		self._assert_rejected(graph, code="CYCLE")

	def test_unreachable_node_is_rejected(self):
		nodes = [
			_node("a", "output", {"value": {}}),
			_node("orphan", "transform", {"op": "coalesce", "input": {"values": []}}),
		]
		graph = _graph(nodes, "a")
		self._assert_rejected(graph, code="UNREACHABLE_NODE")

	def test_dangling_from_reference_is_rejected(self):
		nodes = [
			_node(
				"emit", "output",
				{"value": {"$from": "does_not_exist.rows"}},
			),
		]
		graph = _graph(nodes, "emit")
		self._assert_rejected(graph, code="DANGLING_REFERENCE")

	def test_forward_reference_is_rejected(self):
		"""'a' references 'b', but 'b' only runs after 'a' -- 'b' has not produced output yet
		at the point 'a' would need it, regardless of array order."""
		nodes = [
			_node("a", "transform", {"op": "coalesce", "input": {"values": [{"$from": "b.value"}]}}, next_="b"),
			_node("b", "output", {"value": {}}),
		]
		graph = _graph(nodes, "a")
		self._assert_rejected(graph, code="FORWARD_REFERENCE")

	def test_missing_limits_graph_is_rejected(self):
		nodes = [_node("emit", "output", {"value": {}})]
		contract = _contract()
		del contract["limits"]
		graph = _graph(nodes, "emit", contract=contract)
		self._assert_rejected(graph, code="SCHEMA")

	def test_limits_present_but_exceeding_policy_is_rejected(self):
		nodes = [_node("emit", "output", {"value": {}})]
		limits = dict(_VALID_LIMITS)
		limits["max_wall_time_ms"] = POLICY_LIMIT_CEILINGS["max_wall_time_ms"] * 10
		graph = _graph(nodes, "emit", contract=_contract(limits=limits))
		self._assert_rejected(graph, code="LIMIT_EXCEEDS_POLICY")

	def test_unknown_transform_op_is_rejected(self):
		nodes = [
			_node("bad", "transform", {"op": "eval_arbitrary_python", "input": {}}, next_="emit"),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "bad")
		self._assert_rejected(graph, code="SCHEMA")

	def test_unparseable_expression_is_rejected(self):
		nodes = [
			_node(
				"check", "condition",
				{"expression": "__import__('os').system('rm -rf /')", "on_true": "emit", "on_false": "emit"},
			),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "check")
		self._assert_rejected(graph, code="BAD_EXPRESSION")

	def test_self_reference_is_rejected(self):
		nodes = [_node("emit", "output", {"value": {"$from": "emit.value"}})]
		graph = _graph(nodes, "emit")
		self._assert_rejected(graph, code="SELF_REFERENCE")

	def test_dangling_control_flow_target_is_rejected(self):
		nodes = [
			_node(
				"check", "condition",
				{"expression": "True", "on_true": "does_not_exist", "on_false": "emit"},
			),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "check")
		self._assert_rejected(graph, code="DANGLING_TARGET")

	def test_dangling_entry_is_rejected(self):
		nodes = [_node("emit", "output", {"value": {}})]
		graph = _graph(nodes, "does_not_exist")
		self._assert_rejected(graph, code="DANGLING_ENTRY")

	def test_duplicate_node_id_is_rejected(self):
		nodes = [
			_node("a", "output", {"value": {}}),
			_node("a", "output", {"value": {}}),
		]
		graph = _graph(nodes, "a")
		self._assert_rejected(graph, code="DUPLICATE_NODE_ID")

	def test_undeclared_read_envelope_is_rejected(self):
		"""A tool.call whose classified permission needs read access to a doctype the graph's
		own contract.permission_envelope does not declare -- must fail even though the graph is
		otherwise structurally sound (graph-ir.md section 6)."""
		nodes = [
			_node("load", "tool.call", {"tool_id": "erpnext.get_customer", "input": {}}, next_="emit"),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "load", contract=_contract(read=[]))  # deliberately empty
		self._assert_rejected(graph, code="ENVELOPE_UNDER_DECLARED")

	def test_unknown_profile_argument_is_rejected(self):
		nodes = [_node("emit", "output", {"value": {}})]
		graph = _graph(nodes, "emit")
		result = _validate(graph, profile="not-a-real-profile")
		self.assertFalse(result.ok)
		self.assertEqual(result.errors[0].code, "UNKNOWN_PROFILE")


class TestFlowProfileAllowsFlowOnlyNodes(unittest.TestCase):
	"""Sanity check that profile enforcement is symmetric: the same agent.run node rejected
	under the procedure profile validates under the flow profile."""

	def test_agent_run_valid_under_flow_profile(self):
		nodes = [
			_node(
				"ask_llm", "agent.run",
				{"agent": "some-agent", "prompt": "decide something"},
				next_="emit",
			),
			_node("emit", "output", {"value": {}}),
		]
		graph = _graph(nodes, "ask_llm", profile="flow")
		result = _validate(graph, profile="flow")
		self.assertTrue(result.ok, msg=[str(e) for e in result.errors])


class TestValidationResultShape(unittest.TestCase):
	def test_raise_if_invalid_raises_with_all_errors(self):
		nodes = [
			_node("a", "transform", {"op": "coalesce", "input": {"values": []}}, next_="a"),
		]
		graph = _graph(nodes, "a")
		result = _validate(graph)
		with self.assertRaises(Exception):
			result.raise_if_invalid()

	def test_ok_result_is_immutable_dataclass(self):
		result = _validate(benchmark1_graph())
		self.assertIsInstance(result, ValidationResult)
		with self.assertRaises(Exception):
			result.ok = False  # frozen dataclass


if __name__ == "__main__":
	unittest.main()
