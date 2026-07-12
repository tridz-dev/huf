# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


def _make_definition(flow_id, **overrides):
	"""Build a minimal valid v0.1 flow definition JSON string."""
	definition = {
		"schema_version": 1,
		"id": flow_id,
		"version": 1,
		"entry": "start",
		"nodes": [
			{"id": "start", "type": "trigger.webhook"},
			{"id": "end", "type": "end"},
		],
		"edges": [
			{"from": "start", "to": "end", "type": "always"},
		],
		"settings": {},
		"metadata": {},
	}
	definition.update(overrides)
	return json.dumps(definition)


def _make_flow(flow_id, **overrides):
	doc = {
		"doctype": "Flow Definition",
		"flow_id": flow_id,
		"flow_name": f"Test Flow {flow_id}",
		"definition_json": _make_definition(flow_id),
	}
	doc.update(overrides)
	return frappe.get_doc(doc)


class TestFlowDefinition(HufTestSuite):
	def test_valid_minimal_definition_inserts(self):
		flow = _make_flow("_Test Flow Valid").insert(ignore_permissions=True)

		self.assertTrue(flow.name)
		self.assertEqual(flow.name, "_Test Flow Valid")
		self.assertEqual(flow.schema_version, 1)
		self.assertTrue(flow.updated_by)
		self.assertTrue(flow.updated_at)

	def test_missing_required_key_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Missing Key"))
		del definition["edges"]

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Missing Key",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_id_flow_id_mismatch_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Mismatch",
				definition_json=_make_definition("some-other-id"),
			).insert(ignore_permissions=True)

	def test_duplicate_node_id_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Dup Node"))
		definition["nodes"].append({"id": "start", "type": "end"})

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Dup Node",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_unknown_node_type_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Bad Node"))
		definition["nodes"][0]["type"] = "trigger.carrier_pigeon"

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Bad Node",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_entry_not_in_nodes_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Bad Entry"))
		definition["entry"] = "nonexistent-node"

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Bad Entry",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_edge_unknown_node_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Bad Edge"))
		definition["edges"] = [{"from": "start", "to": "ghost", "type": "always"}]

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Bad Edge",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_unknown_edge_type_rejected(self):
		definition = json.loads(_make_definition("_Test Flow Bad Edge Type"))
		definition["edges"] = [{"from": "start", "to": "end", "type": "sometimes"}]

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow Bad Edge Type",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_expression_edge_without_condition_rejected(self):
		definition = json.loads(_make_definition("_Test Flow No Condition"))
		definition["edges"] = [{"from": "start", "to": "end", "type": "expression"}]

		with self.assertRaises(frappe.ValidationError):
			_make_flow(
				"_Test Flow No Condition",
				definition_json=json.dumps(definition),
			).insert(ignore_permissions=True)

	def test_version_increments_on_update_not_insert(self):
		flow = _make_flow("_Test Flow Versioning").insert(ignore_permissions=True)
		self.assertEqual(flow.version, 1)

		flow.flow_name = "Test Flow Versioning Updated"
		flow.save(ignore_permissions=True)
		self.assertEqual(flow.version, 2)

		flow.flow_name = "Test Flow Versioning Updated Again"
		flow.save(ignore_permissions=True)
		self.assertEqual(flow.version, 3)
