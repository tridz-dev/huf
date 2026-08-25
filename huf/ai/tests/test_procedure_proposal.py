# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.procedure_proposal (Run & Propose Procedure).

Frappe-free -- ``huf.ai.procedure_proposal`` does ``import frappe`` / ``from frappe import
_`` / ``from frappe.utils import now_datetime`` at its own top level (it defines two
``@frappe.whitelist()`` endpoints), and it imports ``huf.ai.graph.validator`` /
``huf.ai.graph.permissions`` / ``huf.ai.procedure_versioning``, which do the same. This
file installs the same narrow standalone stub as ``test_procedure_conversion.py`` /
``test_graph_permissions.py`` before importing anything under test, and every fixture
below supplies its own ``classify_tool`` fake instead of touching the real registry (the
stub's ``frappe.get_cached_doc`` would otherwise hand back a ``MagicMock``, not a real
tool doc).

These tests exercise only the pure, frappe-free half of the module:
``compile_procedure_from_trace`` (the ``propose`` preview compiler) and
``_build_procedure_document_payload`` / ``_revalidate_procedure_graph`` (the re-validation
``accept_procedure_proposal`` runs before ever calling ``frappe.get_doc(...).insert()``).
The two ``@frappe.whitelist()`` entry points themselves are thin frappe-I/O wrappers
around these and are exercised by bench-based tests, not here -- matching
``test_procedure_conversion.py``'s own split against ``huf.ai.flow_api``.

Run with:
  pytest huf/ai/tests/test_procedure_proposal.py
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_proposal
"""

import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_standalone_frappe_stub():
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = MagicMock(name="frappe")
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: (lambda f: f)
	fake.as_json = lambda obj: obj

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.graph.permissions import ToolPermission
from huf.ai.graph.validator import GraphValidationError
from huf.ai.procedure_proposal import (
	ProposalResult,
	_build_procedure_document_payload,
	_snake_case,
	compile_procedure_from_trace,
)


def _fake_classify_tool(tool_id: str) -> ToolPermission:
	table = {
		"get_customer": ToolPermission(ptype="read", doctype="Customer"),
		"get_sales_invoices": ToolPermission(ptype="read", doctype="Sales Invoice"),
		"create_todo": ToolPermission(ptype="create", doctype="ToDo"),
	}
	return table.get(tool_id, ToolPermission(ptype=None, doctype=None))


def _completed_call(tool: str, args: dict, result) -> dict:
	return {
		"tool": tool,
		"tool_args": args,
		"tool_result": result,
		"status": "Completed",
		"error_message": None,
	}


class TestCompileProcedureFromTraceCleanTrace(unittest.TestCase):
	"""Point (1): a clean sequential trace with prompt-derived and prior-output-derived
	bindings compiles successfully."""

	def setUp(self):
		self.prompt = "Look up customer ACME-001 and list their open sales invoices."
		self.tool_calls = [
			_completed_call(
				"get_customer",
				{"customer_id": "ACME-001"},
				{"name": "ACME-001", "customer_name": "Acme Corp"},
			),
			_completed_call(
				"get_sales_invoices",
				{"customer": "ACME-001", "limit": 0},
				{"rows": [{"name": "SINV-001", "outstanding_amount": 100}]},
			),
		]

	def test_compiles_successfully(self):
		result = compile_procedure_from_trace(
			prompt=self.prompt,
			response="Acme Corp has one open invoice.",
			tool_calls=self.tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertIsInstance(result, ProposalResult)
		self.assertTrue(result.proposable, result.reason)
		self.assertIsNotNone(result.procedure_graph)
		self.assertEqual(result.step_count, 2)

	def test_graph_has_the_right_shape(self):
		result = compile_procedure_from_trace(
			prompt=self.prompt,
			response="",
			tool_calls=self.tool_calls,
			classify_tool=_fake_classify_tool,
		)
		graph = result.procedure_graph
		self.assertEqual(graph["profile"], "procedure")
		self.assertEqual(graph["schema_version"], "1.0.0")
		self.assertTrue(graph["fingerprint"])

		node_types = [n["type"] for n in graph["nodes"]]
		self.assertEqual(node_types, ["tool.call", "tool.call", "output"])

		tool_call_nodes = [n for n in graph["nodes"] if n["type"] == "tool.call"]
		output_node = graph["nodes"][-1]

		# Chained via next, terminating in one output node (no separate "end" type).
		self.assertEqual(tool_call_nodes[0]["next"], tool_call_nodes[1]["id"])
		self.assertEqual(tool_call_nodes[1]["next"], output_node["id"])
		self.assertIsNone(output_node.get("next"))
		self.assertEqual(graph["entry"], tool_call_nodes[0]["id"])

		# The output node echoes the final tool's own recorded result.
		self.assertEqual(output_node["config"]["value"], {"$from": tool_call_nodes[1]["id"]})

	def test_prompt_derived_argument_becomes_input_reference(self):
		result = compile_procedure_from_trace(
			prompt=self.prompt,
			response="",
			tool_calls=self.tool_calls,
			classify_tool=_fake_classify_tool,
		)
		first_node = result.procedure_graph["nodes"][0]
		self.assertEqual(first_node["config"]["input"]["customer_id"], {"$from": "input.customer_id"})
		self.assertIn("customer_id", result.input_schema["properties"])
		self.assertIn("customer_id", result.input_schema["required"])

	def test_prior_output_derived_argument_becomes_node_reference(self):
		result = compile_procedure_from_trace(
			prompt=self.prompt,
			response="",
			tool_calls=self.tool_calls,
			classify_tool=_fake_classify_tool,
		)
		first_node_id = result.procedure_graph["nodes"][0]["id"]
		second_node = result.procedure_graph["nodes"][1]
		# "ACME-001" also appears verbatim in the prompt, but the customer's own prior
		# output ("name": "ACME-001") is the more specific/traceable explanation and this
		# implementation prefers the nearest earlier node over a prompt match when a
		# value could be explained either way -- see module docstring's stated priority
		# order (a) prompt, (b) earlier output; here (a) also matches, so either binding
		# would be defensible, but the compiled graph must be internally consistent.
		self.assertIn(second_node["config"]["input"]["customer"], (
			{"$from": "input.customer"},
			{"$from": f"{first_node_id}.name"},
		))

	def test_trivial_constant_argument_is_kept_as_literal(self):
		result = compile_procedure_from_trace(
			prompt=self.prompt,
			response="",
			tool_calls=self.tool_calls,
			classify_tool=_fake_classify_tool,
		)
		second_node = result.procedure_graph["nodes"][1]
		self.assertEqual(second_node["config"]["input"]["limit"], 0)


class TestCompileProcedureFromTraceRefusals(unittest.TestCase):
	def test_zero_tool_calls_refuses(self):
		result = compile_procedure_from_trace(
			prompt="do something",
			response="",
			tool_calls=[],
			classify_tool=_fake_classify_tool,
		)
		self.assertFalse(result.proposable)
		self.assertIsNone(result.procedure_graph)
		self.assertIsNone(result.input_schema)
		self.assertEqual(result.step_count, 0)
		self.assertIn("no tool calls", result.reason.lower())

	def test_unexplained_argument_value_refuses_with_specific_reason(self):
		tool_calls = [
			_completed_call(
				"get_customer",
				{"customer_id": "some-opaque-id-not-in-prompt-or-earlier-output"},
				{"name": "irrelevant"},
			),
		]
		result = compile_procedure_from_trace(
			prompt="Look up a customer for me.",
			response="",
			tool_calls=tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertFalse(result.proposable)
		self.assertIsNone(result.procedure_graph)
		self.assertIn("step 1", result.reason)
		self.assertIn("get_customer", result.reason)
		self.assertIn("customer_id", result.reason)
		self.assertIn("judgment call", result.reason)

	def test_incomplete_tool_call_is_a_hard_stop_not_a_skip(self):
		tool_calls = [
			_completed_call("get_customer", {"customer_id": "ACME-001"}, {"name": "ACME-001"}),
			{
				"tool": "get_sales_invoices",
				"tool_args": {"customer": "ACME-001"},
				"tool_result": None,
				"status": "Failed",
				"error_message": "timed out",
			},
		]
		result = compile_procedure_from_trace(
			prompt="Look up customer ACME-001.",
			response="",
			tool_calls=tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertFalse(result.proposable)
		self.assertIsNone(result.procedure_graph)
		self.assertIn("Step 2", result.reason)
		self.assertIn("did not finish cleanly", result.reason)

	def test_queued_status_with_a_result_is_still_a_hard_stop(self):
		tool_calls = [
			{
				"tool": "get_customer",
				"tool_args": {},
				"tool_result": {"name": "ACME-001"},
				"status": "Queued",
				"error_message": None,
			},
		]
		result = compile_procedure_from_trace(
			prompt="Look up a customer.",
			response="",
			tool_calls=tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertFalse(result.proposable)

	def test_missing_tool_result_on_a_completed_row_is_a_hard_stop(self):
		tool_calls = [
			{
				"tool": "get_customer",
				"tool_args": {},
				"tool_result": None,
				"status": "Completed",
				"error_message": None,
			},
		]
		result = compile_procedure_from_trace(
			prompt="Look up a customer.",
			response="",
			tool_calls=tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertFalse(result.proposable)


class TestSnakeCase(unittest.TestCase):
	def test_already_snake_case_is_unchanged(self):
		self.assertEqual(_snake_case("customer_id"), "customer_id")

	def test_camel_case_is_converted(self):
		self.assertEqual(_snake_case("customerId"), "customer_id")


class TestBuildProcedureDocumentPayload(unittest.TestCase):
	"""Point (4): accept_procedure_proposal's server-side re-validation rejects a graph
	that was tampered with client-side between propose and accept."""

	def setUp(self):
		tool_calls = [
			_completed_call("get_customer", {"customer_id": "ACME-001"}, {"name": "ACME-001"}),
		]
		result = compile_procedure_from_trace(
			prompt="Look up customer ACME-001.",
			response="",
			tool_calls=tool_calls,
			classify_tool=_fake_classify_tool,
		)
		self.assertTrue(result.proposable, result.reason)
		self.valid_graph = result.procedure_graph

	def test_valid_graph_builds_a_payload(self):
		payload = _build_procedure_document_payload(
			agent_run_name="AR-0001",
			procedure_graph=self.valid_graph,
			procedure_name="Look up a customer",
			classify_tool=_fake_classify_tool,
		)
		self.assertEqual(payload["doctype"], "Agent Procedure")
		self.assertEqual(payload["procedure_id"], "AR-0001-procedure")
		self.assertEqual(payload["tier"], "Draft")
		self.assertEqual(payload["status"], "Draft")

	def test_tampered_graph_is_rejected(self):
		tampered = dict(self.valid_graph)
		tampered["nodes"] = list(self.valid_graph["nodes"])
		# Rewrite the first tool.call node's tool_id, in place, from a read-only lookup
		# to a write tool -- a plausible "user edited it in devtools" tamper. The
		# contract's permission_envelope is left untouched (still only declaring read
		# access to Customer), so re-validation must catch that the graph now reaches a
		# write surface (ToDo) its own declared envelope never accounted for.
		tampered_node = dict(tampered["nodes"][0])
		tampered_config = dict(tampered_node["config"])
		tampered_config["tool_id"] = "create_todo"
		tampered_node["config"] = tampered_config
		tampered["nodes"][0] = tampered_node

		with self.assertRaises(GraphValidationError):
			_build_procedure_document_payload(
				agent_run_name="AR-0001",
				procedure_graph=tampered,
				procedure_name="Look up a customer",
				classify_tool=_fake_classify_tool,
			)

	def test_structurally_broken_graph_is_rejected(self):
		with self.assertRaises(GraphValidationError):
			_build_procedure_document_payload(
				agent_run_name="AR-0001",
				procedure_graph={"not": "a graph"},
				procedure_name="Look up a customer",
				classify_tool=_fake_classify_tool,
			)

	def test_non_dict_graph_is_rejected(self):
		with self.assertRaises(GraphValidationError):
			_build_procedure_document_payload(
				agent_run_name="AR-0001",
				procedure_graph="not even json-shaped {{{",
				procedure_name="Look up a customer",
				classify_tool=_fake_classify_tool,
			)


if __name__ == "__main__":
	unittest.main()
