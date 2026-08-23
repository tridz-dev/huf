# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.graph.permissions (T-14).

Pure unit tests against the static pass (no frappe calls -- ``classify_tool`` is faked)
and against the runtime ``authorize_tool_call`` helper (frappe is mocked, per this
package's conftest.py, and reconfigured per-test to exercise both the allow and deny
paths).

Run with:
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_graph_permissions
"""

import unittest
from unittest.mock import patch

import frappe

from huf.ai.graph.permissions import (
	ToolPermission,
	authorize_tool_call,
	compute_static_envelope,
	envelope_declares,
	static_tool_closure,
)
from huf.ai.tool_registry import PermissionAwareToolRegistry


# ----------------------------------------------------------------------------------
# Fixture graphs -- one per benchmark, matching spec/graph-ir.md worked examples and
# Tracks/.../benchmarks/*/expected-procedure.md shapes.
# ----------------------------------------------------------------------------------


def _node(id_, type_, config=None, next_=None, on_error=None):
	node = {"id": id_, "type": type_, "config": config or {}}
	if next_ is not None:
		node["next"] = next_
	if on_error is not None:
		node["on_error"] = on_error
	return node


def benchmark1_graph():
	"""Straight tool.call chain -- spec/graph-ir.md section 9.1, verbatim shape."""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "load_invoices",
		"nodes": [
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
		],
	}


def benchmark2_graph():
	"""foreach containing a nested parallel -- benchmark-2-collection-prioritization."""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "load_overdue",
		"nodes": [
			_node(
				"load_overdue", "tool.call",
				{"tool_id": "erpnext.get_overdue_invoices", "input": {}},
				next_="group_by_customer",
			),
			_node(
				"group_by_customer", "transform",
				{"op": "group_by", "input": {}},
				next_="per_customer",
			),
			_node(
				"per_customer", "foreach",
				{
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
			_node("aggregate_row", "transform", {"op": "aggregate", "input": {}}),
			_node("sort_rows", "transform", {"op": "sort", "input": {}}, next_="emit"),
			_node("emit", "output", {"value": {}}),
		],
	}


def benchmark3_graph():
	"""foreach containing nested conditions, several levels deep -- benchmark-3-crm-followup."""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fetch_invoices",
		"nodes": [
			_node(
				"fetch_invoices", "tool.call",
				{"tool_id": "erpnext.fetch_overdue_invoices_for", "input": {}},
				next_="per_invoice",
			),
			_node(
				"per_invoice", "foreach",
				{
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
					"expression": "row[\"qualifies\"] == True",
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
					"expression": "row[\"existing\"] is not None",
					"on_true": "mark_existed",
					"on_false": "create_todo",
				},
			),
			_node("mark_existed", "transform", {"op": "mark", "input": {}}),
			_node(
				"create_todo", "tool.call",
				{"tool_id": "erpnext.create_todo", "input": {}},
				next_="verify_created",
			),
			_node(
				"verify_created", "validate",
				{"op": "verify_todo_created", "input": {}},
				next_="mark_created",
			),
			_node("mark_created", "transform", {"op": "mark", "input": {}}),
			_node("mark_skipped", "transform", {"op": "mark", "input": {}}),
			_node("emit", "output", {"value": {}}),
		],
	}


def benchmark4_graph():
	"""Two independent tool.call roots feeding a foreach with nested conditions."""
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "fetch_invoices",
		"nodes": [
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
			_node("flatten", "transform", {"op": "flatten_and_scope_check", "input": {}}, next_="index"),
			_node("index", "transform", {"op": "index_invoices", "input": {}}, next_="per_payment"),
			_node(
				"per_payment", "foreach",
				{
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
				{"op": "find_candidates", "input": {}},
				next_="branch_on_candidates",
			),
			_node(
				"branch_on_candidates", "condition",
				{
					"expression": "len(row[\"candidates\"]) == 0",
					"on_true": "mark_unmatched",
					"on_false": "branch_on_single_match",
				},
			),
			_node("mark_unmatched", "transform", {"op": "mark", "input": {}}),
			_node(
				"branch_on_single_match", "condition",
				{
					"expression": "len(row[\"candidates\"]) == 1",
					"on_true": "mark_resolved",
					"on_false": "mark_ambiguous",
				},
			),
			_node("mark_resolved", "transform", {"op": "mark", "input": {}}),
			_node("mark_ambiguous", "transform", {"op": "mark", "input": {}}),
			_node(
				"validate_dupes", "validate",
				{"op": "no_duplicate_allocation", "input": {}},
				next_="emit",
			),
			_node("emit", "output", {"value": {}}),
		],
	}


# tool_id -> ToolPermission, standing in for the Agent Tool Function doctype lookup so the
# static-pass tests never touch frappe at all.
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


class TestStaticEnvelopeAllBenchmarks(unittest.TestCase):
	"""Envelope must be derivable for all four T-03 benchmark fixtures (T-14 done-when)."""

	def test_benchmark1_straight_chain(self):
		envelope = compute_static_envelope(benchmark1_graph(), classify_tool=_fake_classify_tool)
		self.assertEqual(
			envelope["read"],
			[{"doctype": "Customer"}, {"doctype": "Payment Entry"}, {"doctype": "Sales Invoice"}],
		)
		self.assertEqual(envelope["write"], [])
		self.assertEqual(envelope["http"], "none")
		self.assertEqual(envelope["code"], "none")

	def test_benchmark2_foreach_with_nested_parallel(self):
		envelope = compute_static_envelope(benchmark2_graph(), classify_tool=_fake_classify_tool)
		# fetch_customer / fetch_payment_history only live inside per_customer's foreach ->
		# fan_out's parallel branches; a main-chain-only walk would miss both entirely.
		self.assertIn({"doctype": "Customer"}, envelope["read"])
		self.assertIn({"doctype": "Payment Entry"}, envelope["read"])
		self.assertIn({"doctype": "Sales Invoice"}, envelope["read"])
		self.assertEqual(envelope["write"], [])

	def test_benchmark3_foreach_with_nested_conditions(self):
		envelope = compute_static_envelope(benchmark3_graph(), classify_tool=_fake_classify_tool)
		# create_todo only lives behind two nested condition branches inside the foreach body.
		self.assertEqual(envelope["write"], [{"doctype": "ToDo"}])
		self.assertIn({"doctype": "Sales Invoice"}, envelope["read"])
		self.assertIn({"doctype": "ToDo"}, envelope["read"])  # existing_followup_check

	def test_benchmark4_two_roots_plus_foreach_with_nested_conditions(self):
		envelope = compute_static_envelope(benchmark4_graph(), classify_tool=_fake_classify_tool)
		self.assertEqual(
			envelope["read"],
			[{"doctype": "Payment Entry"}, {"doctype": "Sales Invoice"}],
		)
		self.assertEqual(envelope["write"], [])


class TestStaticToolClosure(unittest.TestCase):
	def test_closure_includes_nested_foreach_and_parallel_tool_ids(self):
		closure = static_tool_closure(benchmark2_graph())
		self.assertEqual(
			closure,
			{
				"erpnext.get_overdue_invoices",
				"erpnext.get_customer",
				"erpnext.get_payment_entries",
			},
		)

	def test_closure_includes_nested_condition_tool_ids(self):
		closure = static_tool_closure(benchmark3_graph())
		self.assertIn("erpnext.create_todo", closure)
		self.assertIn("erpnext.existing_followup_check", closure)


class TestEnvelopeDeclares(unittest.TestCase):
	def test_declares_true_for_present_read(self):
		envelope = {"read": [{"doctype": "Sales Invoice"}], "write": [], "http": "none", "code": "none"}
		self.assertTrue(envelope_declares(envelope, ptype="read", doctype="Sales Invoice"))

	def test_declares_false_for_absent_doctype(self):
		envelope = {"read": [{"doctype": "Sales Invoice"}], "write": [], "http": "none", "code": "none"}
		self.assertFalse(envelope_declares(envelope, ptype="read", doctype="Customer"))

	def test_declares_false_for_write_declared_as_read_only(self):
		envelope = {"read": [{"doctype": "ToDo"}], "write": [], "http": "none", "code": "none"}
		self.assertFalse(envelope_declares(envelope, ptype="create", doctype="ToDo"))


class TestAuthorizeToolCallI1Intersection(unittest.TestCase):
	"""Proves the module's central claim: the compiled envelope is NEVER a runtime substitute (I2)."""

	def setUp(self):
		# frappe is a MagicMock (see conftest.py) shared across this test module; give it real
		# exception semantics for the duration of each test so assertRaises works like it does
		# against the real frappe in a bench.
		frappe.PermissionError = PermissionError
		frappe.throw.side_effect = self._raise_from_throw
		self.addCleanup(self._reset_frappe_mock)

		self.tool_doc = type("FakeToolDoc", (), {
			"types": "Get Document",
			"reference_doctype": "Sales Invoice",
			"required_permission": None,
			"allowed_for_guest": False,
			"is_read_only": False,
			"function_path": "",
			"tool_name": "get_sales_invoice",
		})()
		frappe.get_cached_doc.side_effect = lambda doctype, name: self.tool_doc

		self.agent_doc = type("FakeAgent", (), {"name": "Test Agent"})()

		self.envelope = {
			"read": [{"doctype": "Sales Invoice"}],
			"write": [],
			"http": "none",
			"code": "none",
		}

	@staticmethod
	def _raise_from_throw(msg, exc_class=None, *args, **kwargs):
		raise (exc_class or Exception)(msg)

	@staticmethod
	def _reset_frappe_mock():
		frappe.throw.side_effect = None
		frappe.get_cached_doc.side_effect = None

	def test_allows_when_envelope_declares_and_live_check_passes(self):
		with patch.object(PermissionAwareToolRegistry, "_can_use_tool", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_code_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ssh_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_docker_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ask_user", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_document_artifact_tools", return_value=True):
			# Must not raise.
			authorize_tool_call(
				tool_id="erpnext.get_sales_invoices",
				user="someone@example.com",
				agent_doc=self.agent_doc,
				envelope=self.envelope,
				classify_tool=_fake_classify_tool,
			)

	def test_denies_when_envelope_declares_it_but_live_permission_says_no(self):
		"""THE negative test: the envelope says yes, but the live registry check says no --
		and the call must still be denied. This is I2 made concrete: a procedure can never
		execute a tool its caller lacks permission for, even when the compiled envelope
		declares it in scope."""
		with patch.object(PermissionAwareToolRegistry, "_can_use_tool", return_value=False), \
			patch.object(PermissionAwareToolRegistry, "_allows_code_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ssh_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_docker_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ask_user", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_document_artifact_tools", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				authorize_tool_call(
					tool_id="erpnext.get_sales_invoices",
					user="someone@example.com",
					agent_doc=self.agent_doc,
					envelope=self.envelope,
					classify_tool=_fake_classify_tool,
				)

	def test_denies_when_envelope_does_not_declare_it_even_if_live_check_would_pass(self):
		"""The other half of the intersection: a tool the live registry would happily allow is
		still denied if it falls outside this procedure's compiled envelope."""
		empty_envelope = {"read": [], "write": [], "http": "none", "code": "none"}
		with patch.object(PermissionAwareToolRegistry, "_can_use_tool", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_code_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ssh_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_docker_execution", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_ask_user", return_value=True), \
			patch.object(PermissionAwareToolRegistry, "_allows_document_artifact_tools", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				authorize_tool_call(
					tool_id="erpnext.get_sales_invoices",
					user="someone@example.com",
					agent_doc=self.agent_doc,
					envelope=empty_envelope,
					classify_tool=_fake_classify_tool,
				)


if __name__ == "__main__":
	unittest.main()
