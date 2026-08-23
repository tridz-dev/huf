# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.procedure_conversion (T-52).

Frappe-free -- ``huf.ai.procedure_conversion`` imports ``huf.ai.graph.validator`` and
``huf.ai.graph.permissions``, both of which do ``import frappe`` at module load time
(``permissions.default_tool_classifier`` calls ``frappe.get_cached_doc``), so this file
installs the same narrow standalone stub as ``test_graph_permissions.py`` before
importing anything under test, and every fixture below supplies its own
``classify_tool`` fake instead of touching the real registry.

Run with:
  pytest huf/ai/tests/test_procedure_conversion.py
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_conversion
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
	fake.whitelist = lambda *a, **k: lambda f: f

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils


_install_standalone_frappe_stub()

from huf.ai.procedure_conversion import (
	BLOCKING_NODE_TYPES,
	ConversionResult,
	analyze_conversion,
	convert_flow_graph,
	find_blocking_nodes,
)


def _limits(**overrides) -> dict:
	limits = {
		"max_nodes": 20,
		"max_rows": 1000,
		"max_output_bytes": 100_000,
		"max_parallel_calls": 1,
		"max_foreach_iterations": 1,
		"max_external_calls": 5,
		"max_writes": 0,
		"max_wall_time_ms": 5000,
		"fail_closed": True,
	}
	limits.update(overrides)
	return limits


def _contract(*, read=(), write=(), input_schema=None, output_schema=None) -> dict:
	return {
		"input_schema": input_schema if input_schema is not None else {"type": "object"},
		"output_schema": output_schema if output_schema is not None else {"type": "object"},
		"applies_when": [],
		"permission_envelope": {
			"read": [{"doctype": d} for d in read],
			"write": [{"doctype": d} for d in write],
			"http": "none",
			"code": "none",
		},
		"limits": _limits(max_writes=1 if write else 0),
	}


def _flow_graph(nodes: list[dict], *, entry="trigger", contract=None) -> dict:
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": entry,
		"nodes": nodes,
		"contract": contract if contract is not None else _contract(read=("Customer",)),
	}


def _deterministic_flow_nodes() -> list[dict]:
	return [
		{
			"id": "trigger",
			"type": "trigger.webhook",
			"config": {"method": "POST"},
			"next": "fetch",
		},
		{
			"id": "fetch",
			"type": "tool.call",
			"config": {"tool_id": "get_customer", "input": {}},
			"next": "done",
		},
		{
			"id": "done",
			"type": "output",
			"config": {"value": {"$from": "fetch.result"}},
		},
	]


def _fake_classify_tool(tool_id: str):
	from huf.ai.graph.permissions import ToolPermission

	table = {
		"get_customer": ToolPermission(ptype="read", doctype="Customer"),
	}
	return table.get(tool_id, ToolPermission(ptype=None, doctype=None))


class TestFindBlockingNodes(unittest.TestCase):
	def test_deterministic_flow_has_no_blocking_nodes(self):
		graph = _flow_graph(_deterministic_flow_nodes())
		self.assertEqual(find_blocking_nodes(graph), [])

	def test_each_flow_only_type_is_detected(self):
		for node_type in BLOCKING_NODE_TYPES:
			nodes = [{"id": "n1", "type": node_type, "config": {}}]
			graph = _flow_graph(nodes, entry="n1")
			found = find_blocking_nodes(graph)
			self.assertEqual(found, [("n1", node_type)])


class TestConvertFlowGraph(unittest.TestCase):
	def test_strips_trigger_and_rewires_entry(self):
		graph = _flow_graph(_deterministic_flow_nodes())
		procedure = convert_flow_graph(graph)

		self.assertEqual(procedure["profile"], "procedure")
		self.assertEqual(procedure["entry"], "fetch")
		node_ids = {n["id"] for n in procedure["nodes"]}
		self.assertNotIn("trigger", node_ids)
		self.assertEqual(node_ids, {"fetch", "done"})

	def test_output_only_carries_the_six_graph_fields(self):
		graph = _flow_graph(_deterministic_flow_nodes())
		procedure = convert_flow_graph(graph)
		self.assertEqual(
			set(procedure.keys()), {"schema_version", "profile", "fingerprint", "entry", "nodes", "contract"}
		)

	def test_entry_without_a_trigger_node_is_kept_as_is(self):
		nodes = [
			{
				"id": "fetch",
				"type": "tool.call",
				"config": {"tool_id": "get_customer", "input": {}},
				"next": "done",
			},
			{"id": "done", "type": "output", "config": {"value": {"$from": "fetch.result"}}},
		]
		graph = _flow_graph(nodes, entry="fetch")
		procedure = convert_flow_graph(graph)
		self.assertEqual(procedure["entry"], "fetch")


class TestAnalyzeConversion(unittest.TestCase):
	def test_deterministic_flow_is_convertible(self):
		graph = _flow_graph(_deterministic_flow_nodes())
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)

		self.assertIsInstance(result, ConversionResult)
		self.assertTrue(result.convertible, result.reason)
		self.assertIsNotNone(result.procedure_graph)
		self.assertEqual(result.summary.reads, ("Customer",))
		self.assertEqual(result.summary.writes, ())
		self.assertEqual(result.summary.atomic_operations, 1)

	def test_agent_run_node_is_refused_by_name(self):
		nodes = _deterministic_flow_nodes()
		nodes.insert(
			1,
			{
				"id": "ask_llm",
				"type": "agent.run",
				"config": {"agent": "some-agent", "prompt": "summarize"},
				"next": "fetch",
			},
		)
		nodes[0]["next"] = "ask_llm"
		graph = _flow_graph(nodes)

		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)

		self.assertFalse(result.convertible)
		self.assertIsNone(result.procedure_graph)
		self.assertIsNone(result.summary)
		self.assertIn("ask_llm", result.reason)
		self.assertEqual(result.blocking_nodes, (("ask_llm", "agent.run"),))

	def test_router_llm_node_is_refused_by_name(self):
		nodes = [
			{"id": "trigger", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "route"},
			{
				"id": "route",
				"type": "router.llm",
				"config": {"options": [{"label": "a", "node_id": "done"}]},
			},
			{"id": "done", "type": "output", "config": {"value": {"$from": "input"}}},
		]
		graph = _flow_graph(nodes)
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)
		self.assertIn("route", result.reason)

	def test_human_approval_node_is_refused_by_name(self):
		nodes = [
			{"id": "trigger", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "approve"},
			{
				"id": "approve",
				"type": "human.approval",
				"config": {"message": "ok?", "approve_next": "done", "reject_next": "done"},
			},
			{"id": "done", "type": "output", "config": {"value": {"$from": "input"}}},
		]
		graph = _flow_graph(nodes)
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)
		self.assertIn("approve", result.reason)

	def test_multiple_trigger_entries_are_refused(self):
		graph = _flow_graph(_deterministic_flow_nodes(), entry=["trigger", "trigger"])
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)
		self.assertIn("trigger", result.reason.lower())

	def test_trigger_with_no_next_is_refused(self):
		nodes = [{"id": "trigger", "type": "trigger.webhook", "config": {"method": "POST"}}]
		graph = _flow_graph(nodes, entry="trigger")
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)

	def test_schema_invalid_flow_is_refused_with_validation_errors(self):
		graph = {"not": "a graph"}
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)
		self.assertTrue(result.validation_errors)

	def test_non_dict_input_is_refused(self):
		result = analyze_conversion("not a graph", classify_tool=_fake_classify_tool)
		self.assertFalse(result.convertible)

	def test_write_flow_converts_with_writes_in_summary(self):
		nodes = [
			{"id": "trigger", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "upsert"},
			{
				"id": "upsert",
				"type": "tool.call",
				"config": {"tool_id": "update_customer", "input": {}},
				"next": "done",
			},
			{"id": "done", "type": "output", "config": {"value": {"$from": "upsert.result"}}},
		]

		def classify(tool_id):
			from huf.ai.graph.permissions import ToolPermission

			if tool_id == "update_customer":
				return ToolPermission(ptype="write", doctype="Customer")
			return ToolPermission(ptype=None, doctype=None)

		graph = _flow_graph(nodes, contract=_contract(write=("Customer",)))
		result = analyze_conversion(graph, classify_tool=classify)

		self.assertTrue(result.convertible, result.reason)
		self.assertEqual(result.summary.writes, ("Customer",))
		# I8: conversion only ever produces a graph; it is the caller's job to insert it
		# as a Draft and never as Active. Nothing here decides activation.

	def test_multi_step_flow_reports_a_reduction_estimate(self):
		nodes = [
			{"id": "trigger", "type": "trigger.webhook", "config": {"method": "POST"}, "next": "a"},
			{"id": "a", "type": "tool.call", "config": {"tool_id": "get_customer", "input": {}}, "next": "b"},
			{
				"id": "b",
				"type": "transform",
				"config": {
					"op": "select",
					"input": {"rows": {"$from": "a.result"}, "fields": ["name"]},
				},
				"next": "done",
			},
			{"id": "done", "type": "output", "config": {"value": {"$from": "b"}}},
		]
		graph = _flow_graph(nodes)
		result = analyze_conversion(graph, classify_tool=_fake_classify_tool)

		self.assertTrue(result.convertible, result.reason)
		self.assertEqual(result.summary.atomic_operations, 2)
		self.assertGreater(result.summary.estimated_round_trip_reduction_pct, 0)


if __name__ == "__main__":
	unittest.main()
