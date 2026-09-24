"""Tests for Decision Policy reference detection in Flow Definitions.

Tests the get_policy_references() function and the DecisionPolicy.on_trash() behavior
when policies are referenced by active Flow Definitions.
"""

import json
import frappe
from frappe.tests.utils import FrappeTestCase
from huf.ai.decision.policy_references import get_policy_references


class TestPolicyReferences(FrappeTestCase):
	"""Test suite for policy reference detection."""

	def setUp(self):
		"""Set up test fixtures."""
		self.test_policy_name = "test_policy_refs"
		self.create_test_policy()

	def tearDown(self):
		"""Clean up after tests."""
		# Delete any created Flow Definitions
		frappe.db.delete("Flow Definition", {"status": "Active"})
		# Delete test policy
		try:
			frappe.delete_doc("Decision Policy", self.test_policy_name, ignore_missing=True)
		except:
			pass

	def create_test_policy(self):
		"""Create a test Decision Policy."""
		if not frappe.db.exists("Decision Policy", self.test_policy_name):
			policy = frappe.get_doc({
				"doctype": "Decision Policy",
				"policy_name": self.test_policy_name,
				"purpose": "Generic",
				"definition_json": json.dumps({
					"policy_id": self.test_policy_name,
					"questions": [
						{
							"id": "q1",
							"kind": "select",
							"instructions": "Test question",
							"options": [
								{"id": "a", "description": "Option A"},
								{"id": "b", "description": "Option B"}
							]
						}
					],
					"fallback_action": "fallback"
				})
			})
			policy.insert()

	def create_flow_definition(self, flow_id: str, flow_name: str, definition_dict: dict,
								status: str = "Active"):
		"""Helper to create a Flow Definition."""
		from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition

		flow_def = frappe.get_doc({
			"doctype": "Flow Definition",
			"flow_id": flow_id,
			"flow_name": flow_name,
			"status": status,
			"definition_json": json.dumps(definition_dict),
		})

		# Temporarily bypass validation by monkey-patching the validate method
		original_validate = FlowDefinition.validate
		FlowDefinition.validate = lambda self: None
		try:
			flow_def.insert(ignore_permissions=True)
		finally:
			FlowDefinition.validate = original_validate

		return flow_def

	def create_flow_with_decision_router(self, flow_id: str, policy_name: str,
										  status: str = "Active"):
		"""Helper to create a Flow Definition with a router.decision node."""
		definition = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{
					"id": "start",
					"type": "trigger.manual",
					"next": "decision_node"
				},
				{
					"id": "decision_node",
					"type": "router.decision",
					"config": {
						"policy": policy_name,
						"options": [
							{"label": "Option A", "node_id": "node_a"},
							{"label": "Option B", "node_id": "node_b"}
						],
						"default": "node_a"
					}
				},
				{
					"id": "node_a",
					"type": "output",
					"config": {"value": "A"}
				},
				{
					"id": "node_b",
					"type": "output",
					"config": {"value": "B"}
				}
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": {"max_rows": 1000, "max_output_bytes": 100000, "max_foreach_iterations": 50}
			}
		}
		return self.create_flow_definition(flow_id, f"Flow {flow_id}", definition, status)

	def test_get_policy_references_no_flows(self):
		"""Test with no Flow Definitions."""
		refs = get_policy_references(self.test_policy_name)
		self.assertEqual(refs, [])

	def test_get_policy_references_no_match(self):
		"""Test with Flow Definitions that don't reference the policy."""
		self.create_flow_definition(
			"flow_no_match",
			"Flow Without Policy",
			{
				"schema_version": "1.0.0",
				"profile": "flow",
				"fingerprint": "0" * 64,
				"entry": "start",
				"nodes": [
					{"id": "start", "type": "trigger.manual"},
					{"id": "end", "type": "output", "config": {"value": "ok"}}
				],
				"contract": {
					"input_schema": {"type": "object"},
					"output_schema": {"type": "object"},
					"applies_when": [],
					"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
					"limits": {"max_rows": 1000, "max_output_bytes": 100000, "max_foreach_iterations": 50}
				}
			}
		)
		refs = get_policy_references(self.test_policy_name)
		self.assertEqual(refs, [])

	def test_get_policy_references_single_match(self):
		"""Test finding a single reference."""
		self.create_flow_with_decision_router("flow_single", self.test_policy_name)
		refs = get_policy_references(self.test_policy_name)

		self.assertEqual(len(refs), 1)
		ref = refs[0]
		self.assertEqual(ref["flow_id"], "flow_single")
		self.assertEqual(ref["node_id"], "decision_node")
		self.assertIn("flow_def_name", ref)

	def test_get_policy_references_multiple_matches(self):
		"""Test finding multiple references in different flows."""
		self.create_flow_with_decision_router("flow_1", self.test_policy_name)
		self.create_flow_with_decision_router("flow_2", self.test_policy_name)

		refs = get_policy_references(self.test_policy_name)
		self.assertEqual(len(refs), 2)

		flow_ids = {ref["flow_id"] for ref in refs}
		self.assertIn("flow_1", flow_ids)
		self.assertIn("flow_2", flow_ids)

	def test_get_policy_references_multiple_nodes_in_flow(self):
		"""Test with multiple router.decision nodes in a single flow."""
		# Create a flow with two decision routers both referencing the same policy
		definition = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{
					"id": "start",
					"type": "trigger.manual",
					"next": "decision_1"
				},
				{
					"id": "decision_1",
					"type": "router.decision",
					"config": {
						"policy": self.test_policy_name,
						"options": [{"label": "A", "node_id": "decision_2"}],
						"default": "decision_2"
					}
				},
				{
					"id": "decision_2",
					"type": "router.decision",
					"config": {
						"policy": self.test_policy_name,
						"options": [{"label": "B", "node_id": "end"}],
						"default": "end"
					}
				},
				{
					"id": "end",
					"type": "output",
					"config": {"value": "done"}
				}
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": {"max_rows": 1000, "max_output_bytes": 100000, "max_foreach_iterations": 50}
			}
		}
		self.create_flow_definition("flow_multi_node", "Multi Node Flow", definition)

		refs = get_policy_references(self.test_policy_name)
		# Should find both nodes
		self.assertEqual(len(refs), 2)
		node_ids = {ref["node_id"] for ref in refs}
		self.assertIn("decision_1", node_ids)
		self.assertIn("decision_2", node_ids)

	def test_get_policy_references_ignores_inactive_flows(self):
		"""Test that Draft and Archived flows are ignored."""
		# Create an Active flow that matches
		self.create_flow_with_decision_router("flow_active", self.test_policy_name, "Active")

		# Create Draft and Archived flows that also match
		self.create_flow_with_decision_router("flow_draft", self.test_policy_name, "Draft")
		self.create_flow_with_decision_router("flow_archived", self.test_policy_name, "Archived")

		refs = get_policy_references(self.test_policy_name)

		# Should only find the Active one
		self.assertEqual(len(refs), 1)
		self.assertEqual(refs[0]["flow_id"], "flow_active")

	def test_get_policy_references_different_policies(self):
		"""Test that different policy names don't cross-match."""
		self.create_flow_with_decision_router("flow_1", self.test_policy_name)
		self.create_flow_with_decision_router("flow_2", "other_policy")

		refs = get_policy_references(self.test_policy_name)
		self.assertEqual(len(refs), 1)
		self.assertEqual(refs[0]["flow_id"], "flow_1")

		refs_other = get_policy_references("other_policy")
		self.assertEqual(len(refs_other), 1)
		self.assertEqual(refs_other[0]["flow_id"], "flow_2")

	def test_get_policy_references_malformed_json(self):
		"""Test graceful handling of non-dict definition_json."""
		from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition

		# Create a flow with a non-dict JSON structure (e.g., array)
		# This is valid JSON but not a flow graph dict
		flow_def = frappe.get_doc({
			"doctype": "Flow Definition",
			"flow_id": "flow_broken",
			"flow_name": "Broken Flow",
			"status": "Active",
			"definition_json": json.dumps(["not", "a", "dict"]),
		})

		# Temporarily bypass validation by monkey-patching the validate method
		original_validate = FlowDefinition.validate
		FlowDefinition.validate = lambda self: None
		try:
			flow_def.insert(ignore_permissions=True)
		finally:
			FlowDefinition.validate = original_validate

		# Should not crash, just skip it (returns [] because the JSON is not a dict)
		refs = get_policy_references(self.test_policy_name)
		self.assertEqual(refs, [])

	def test_get_policy_references_empty_string_policy(self):
		"""Test with empty policy name."""
		refs = get_policy_references("")
		self.assertEqual(refs, [])

	def test_get_policy_references_returns_correct_fields(self):
		"""Test that returned references have all expected fields."""
		self.create_flow_with_decision_router("flow_test", self.test_policy_name)
		refs = get_policy_references(self.test_policy_name)

		self.assertEqual(len(refs), 1)
		ref = refs[0]

		# Check all expected fields are present
		self.assertIn("flow_id", ref)
		self.assertIn("flow_name", ref)
		self.assertIn("node_id", ref)
		self.assertIn("node_label", ref)
		self.assertIn("flow_def_name", ref)

		# Verify values
		self.assertEqual(ref["flow_id"], "flow_test")
		self.assertEqual(ref["node_id"], "decision_node")


class TestDecisionPolicyOnTrash(FrappeTestCase):
	"""Test suite for DecisionPolicy.on_trash() behavior."""

	def setUp(self):
		"""Set up test fixtures."""
		self.test_policy_name = "test_trash_policy"
		self.create_test_policy()

	def tearDown(self):
		"""Clean up after tests."""
		# Delete any created Flow Definitions
		frappe.db.delete("Flow Definition", {"status": "Active"})
		# Delete test policy
		try:
			frappe.delete_doc("Decision Policy", self.test_policy_name, ignore_missing=True)
		except:
			pass

	def create_test_policy(self):
		"""Create a test Decision Policy."""
		if not frappe.db.exists("Decision Policy", self.test_policy_name):
			policy = frappe.get_doc({
				"doctype": "Decision Policy",
				"policy_name": self.test_policy_name,
				"purpose": "Generic",
				"definition_json": json.dumps({
					"policy_id": self.test_policy_name,
					"questions": [
						{
							"id": "q1",
							"kind": "select",
							"instructions": "Test question",
							"options": [
								{"id": "a", "description": "Option A"},
								{"id": "b", "description": "Option B"}
							]
						}
					],
					"fallback_action": "fallback"
				})
			})
			policy.insert()

	def create_flow_with_decision_router(self, flow_id: str, policy_name: str):
		"""Helper to create a Flow Definition with a router.decision node."""
		from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition

		definition = {
			"schema_version": "1.0.0",
			"profile": "flow",
			"fingerprint": "0" * 64,
			"entry": "start",
			"nodes": [
				{
					"id": "start",
					"type": "trigger.manual",
					"next": "decision_node"
				},
				{
					"id": "decision_node",
					"type": "router.decision",
					"config": {
						"policy": policy_name,
						"options": [
							{"label": "Option A", "node_id": "node_a"},
							{"label": "Option B", "node_id": "node_b"}
						],
						"default": "node_a"
					}
				},
				{
					"id": "node_a",
					"type": "output",
					"config": {"value": "A"}
				},
				{
					"id": "node_b",
					"type": "output",
					"config": {"value": "B"}
				}
			],
			"contract": {
				"input_schema": {"type": "object"},
				"output_schema": {"type": "object"},
				"applies_when": [],
				"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
				"limits": {"max_rows": 1000, "max_output_bytes": 100000, "max_foreach_iterations": 50}
			}
		}

		flow_def = frappe.get_doc({
			"doctype": "Flow Definition",
			"flow_id": flow_id,
			"flow_name": f"Flow {flow_id}",
			"status": "Active",
			"definition_json": json.dumps(definition),
		})

		# Temporarily bypass validation by monkey-patching the validate method
		original_validate = FlowDefinition.validate
		FlowDefinition.validate = lambda self: None
		try:
			flow_def.insert(ignore_permissions=True)
		finally:
			FlowDefinition.validate = original_validate

		return flow_def

	def test_delete_policy_with_no_references(self):
		"""Test that policy can be deleted when not referenced."""
		# This policy has no references, so deletion should succeed
		policy = frappe.get_doc("Decision Policy", self.test_policy_name)
		policy.delete()

		# Verify it's gone
		self.assertFalse(frappe.db.exists("Decision Policy", self.test_policy_name))

	def test_delete_policy_blocked_by_flow_reference(self):
		"""Test that deletion is blocked when policy is referenced by active flow."""
		# Create a flow that references the policy
		self.create_flow_with_decision_router("flow_ref", self.test_policy_name)

		# Try to delete the policy, should raise an exception
		policy = frappe.get_doc("Decision Policy", self.test_policy_name)
		with self.assertRaises(frappe.exceptions.ValidationError) as ctx:
			policy.delete()

		# Verify the error mentions the flow reference
		error_msg = str(ctx.exception)
		self.assertIn("Flow", error_msg)
		self.assertIn("decision_node", error_msg)

	def test_delete_policy_blocked_by_multiple_flow_references(self):
		"""Test deletion blocked with multiple flow references."""
		# Create multiple flows that reference the policy
		self.create_flow_with_decision_router("flow_1", self.test_policy_name)
		self.create_flow_with_decision_router("flow_2", self.test_policy_name)

		# Try to delete, should fail
		policy = frappe.get_doc("Decision Policy", self.test_policy_name)
		with self.assertRaises(frappe.exceptions.ValidationError) as ctx:
			policy.delete()

		error_msg = str(ctx.exception)
		self.assertIn("active Flow(s)", error_msg)

	def test_delete_policy_allows_after_flow_deactivation(self):
		"""Test that deletion succeeds after flows referencing it are deactivated."""
		# Create and then deactivate a flow
		flow = self.create_flow_with_decision_router("flow_temp", self.test_policy_name)
		frappe.db.set_value("Flow Definition", flow.name, "status", "Draft")

		# Now deletion should succeed
		policy = frappe.get_doc("Decision Policy", self.test_policy_name)
		policy.delete()

		# Verify it's gone
		self.assertFalse(frappe.db.exists("Decision Policy", self.test_policy_name))

	def test_error_message_format(self):
		"""Test that error message is properly formatted."""
		self.create_flow_with_decision_router("flow_msg_test", self.test_policy_name)

		policy = frappe.get_doc("Decision Policy", self.test_policy_name)
		try:
			policy.delete()
			self.fail("Expected ValidationError to be raised")
		except frappe.exceptions.ValidationError as e:
			error_msg = str(e)
			# Should mention the policy name
			self.assertIn(self.test_policy_name, error_msg)
			# Should mention it's a Flow
			self.assertIn("Flow", error_msg)
			# Should mention the count
			self.assertIn("1", error_msg)
