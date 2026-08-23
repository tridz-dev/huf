# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for huf.ai.procedure_versioning (T-20).

This module has zero import-time frappe dependency, so these tests run under plain
pytest with no bench and no stub, and unmodified on a bench (real frappe simply is not
imported by the module under test). See huf/ai/tests/test_graph_permissions.py for the
sibling pattern this test package uses when a module under test DOES need frappe.

Run with:
  pytest huf/ai/tests/test_procedure_versioning.py
  bench --site <site> run-tests --app huf --module huf.ai.tests.test_procedure_versioning
"""

import copy
import sys
import types
import unittest


def _install_standalone_frappe_stub():
	"""Make ``huf`` importable without a real Frappe bench. ``huf/__init__.py`` does
	``import frappe`` unconditionally at import time; conftest.py's own stub runs too
	late for that (see huf.ai.tests.test_graph_permissions for the same precedent).
	On a real bench 'frappe' already has a __file__ and is left untouched.
	"""
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return

	fake = types.ModuleType("frappe")
	fake._ = lambda msg, *a, **k: msg
	fake.whitelist = lambda *a, **k: lambda f: f
	sys.modules["frappe"] = fake


_install_standalone_frappe_stub()

from huf.ai.procedure_versioning import (
	CONTENT_FIELDS,
	FLOW_ONLY_NODE_TYPES,
	FlowOnlyNodeError,
	assert_no_flow_only_nodes,
	canonical_json_bytes,
	compute_fingerprint,
	extract_contract_fields,
	find_flow_only_nodes,
)


def _minimal_procedure_graph():
	return {
		"schema_version": "1.0.0",
		"profile": "procedure",
		"entry": "n1",
		"nodes": [
			{"id": "n1", "type": "tool.call", "config": {"tool_id": "get_thing"}, "next": "n2"},
			{"id": "n2", "type": "output", "config": {"value": {"$from": "n1.result"}}},
		],
		"contract": {
			"input_schema": {"type": "object"},
			"output_schema": {"type": "object"},
			"applies_when": [],
			"permission_envelope": {"read": ["Thing"], "write": [], "http": "none", "code": "none"},
			"limits": {
				"max_nodes": 10,
				"max_rows": 100,
				"max_output_bytes": 10000,
				"max_parallel_calls": 1,
				"max_foreach_iterations": 1,
				"max_external_calls": 1,
				"max_writes": 0,
				"max_wall_time_ms": 5000,
				"fail_closed": True,
			},
		},
	}


class TestFingerprint(unittest.TestCase):
	def test_identical_content_same_fingerprint(self):
		a = _minimal_procedure_graph()
		b = copy.deepcopy(a)
		self.assertEqual(compute_fingerprint(a), compute_fingerprint(b))

	def test_key_order_does_not_change_fingerprint(self):
		a = _minimal_procedure_graph()
		# Rebuild with reversed top-level key insertion order -- canonicalization must
		# sort keys, so this must not change the hash.
		b = {k: a[k] for k in reversed(list(a.keys()))}
		self.assertEqual(compute_fingerprint(a), compute_fingerprint(b))

	def test_content_change_changes_fingerprint(self):
		a = _minimal_procedure_graph()
		b = copy.deepcopy(a)
		b["nodes"][0]["config"]["tool_id"] = "get_other_thing"
		self.assertNotEqual(compute_fingerprint(a), compute_fingerprint(b))

	def test_fingerprint_excludes_its_own_field(self):
		"""Section 7 step 1: fingerprint is computed with any existing 'fingerprint' key
		removed first, so embedding a (possibly stale) fingerprint in the input document
		must not perturb the computed value."""
		a = _minimal_procedure_graph()
		b = copy.deepcopy(a)
		b["fingerprint"] = "0" * 64
		self.assertEqual(compute_fingerprint(a), compute_fingerprint(b))

	def test_fingerprint_is_64_char_hex(self):
		fp = compute_fingerprint(_minimal_procedure_graph())
		self.assertEqual(len(fp), 64)
		int(fp, 16)  # raises ValueError if not hex

	def test_no_site_specific_fields_in_hashed_content(self):
		"""Fingerprint must never be perturbed by things like docname/timestamps, which
		are never part of the graph document in the first place -- this test documents
		that expectation by asserting the graph dict alone has no such keys and that
		canonical_json_bytes only ever serializes what was given to it."""
		graph = _minimal_procedure_graph()
		canonical = canonical_json_bytes(graph)
		for forbidden in (b'"name"', b'"docname"', b'"creation"', b'"modified"'):
			self.assertNotIn(forbidden, canonical)


class TestFlowOnlyNodeRejection(unittest.TestCase):
	def test_clean_procedure_graph_passes(self):
		assert_no_flow_only_nodes(_minimal_procedure_graph())  # must not raise

	def test_each_task_card_flow_only_type_is_rejected(self):
		for node_type in ("agent.run", "router.llm", "human.approval"):
			with self.subTest(node_type=node_type):
				graph = _minimal_procedure_graph()
				graph["nodes"].append({"id": "flow_node", "type": node_type, "config": {}})
				found = find_flow_only_nodes(graph)
				self.assertEqual(found, [("flow_node", node_type)])
				with self.assertRaises(FlowOnlyNodeError):
					assert_no_flow_only_nodes(graph)

	def test_flow_only_node_inside_foreach_body_is_still_caught(self):
		"""Flow-only nodes referenced only from foreach.config.body / parallel.config.branches
		are still top-level entries in the nodes array (spec/graph-ir.md section 2.1/2.2/6),
		so a flat walk must catch them too -- not just nodes on the main entry chain."""
		graph = _minimal_procedure_graph()
		graph["nodes"].append(
			{"id": "loop", "type": "foreach", "config": {"body": ["approve_step"], "max_iterations": 5}}
		)
		graph["nodes"].append({"id": "approve_step", "type": "human.approval", "config": {}})
		found = find_flow_only_nodes(graph)
		self.assertIn(("approve_step", "human.approval"), found)

	def test_trigger_nodes_also_rejected(self):
		graph = _minimal_procedure_graph()
		graph["nodes"].append({"id": "t1", "type": "trigger.webhook", "config": {}})
		self.assertTrue(find_flow_only_nodes(graph))

	def test_flow_only_node_types_constant_is_a_superset_of_task_card_three(self):
		self.assertTrue({"agent.run", "router.llm", "human.approval"} <= FLOW_ONLY_NODE_TYPES)


class TestExtractContractFields(unittest.TestCase):
	def test_read_only_graph(self):
		derived = extract_contract_fields(_minimal_procedure_graph())
		self.assertTrue(derived["is_read_only"])
		self.assertFalse(derived["contains_writes"])
		self.assertFalse(derived["contains_code"])

	def test_write_graph(self):
		graph = _minimal_procedure_graph()
		graph["contract"]["permission_envelope"]["write"] = ["Thing"]
		derived = extract_contract_fields(graph)
		self.assertTrue(derived["contains_writes"])
		self.assertFalse(derived["is_read_only"])

	def test_code_none_literal_is_not_contains_code(self):
		graph = _minimal_procedure_graph()
		graph["contract"]["permission_envelope"]["code"] = "none"
		derived = extract_contract_fields(graph)
		self.assertFalse(derived["contains_code"])

	def test_code_list_is_contains_code(self):
		graph = _minimal_procedure_graph()
		graph["contract"]["permission_envelope"]["code"] = ["sandbox-1"]
		derived = extract_contract_fields(graph)
		self.assertTrue(derived["contains_code"])

	def test_missing_contract_does_not_raise(self):
		derived = extract_contract_fields({"nodes": []})
		self.assertIsNone(derived["input_schema"])
		self.assertFalse(derived["contains_writes"])


class TestContentFields(unittest.TestCase):
	def test_content_fields_include_definition_and_fingerprint(self):
		self.assertIn("definition_json", CONTENT_FIELDS)
		self.assertIn("fingerprint", CONTENT_FIELDS)
		self.assertIn("procedure_id", CONTENT_FIELDS)
		self.assertIn("version", CONTENT_FIELDS)


if __name__ == "__main__":
	unittest.main()
