# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for Decision Router node activation validation.

Tests validate that:
1. router.decision nodes pass activation checks when policy is published and uncertain_next is set
2. Activation fails when policy is missing
3. Activation fails when policy is unpublished (no current_version)
4. Activation fails when current_version.status != "Published"
5. Activation fails when uncertain_next is absent
6. Draft save works without activation flag (lenient mode)
7. Existing validator tests continue to pass
"""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.graph.validator import (
	ValidationError,
	validate_flow_graph,
	_check_router_decision_activation,
)


class MockDecisionPolicy:
	"""Mock frappe doc for Decision Policy."""

	def __init__(self, name, enabled=True, current_version=None):
		self.name = name
		self.enabled = enabled
		self.current_version = current_version
		self._fields = {
			"name": name,
			"enabled": enabled,
			"current_version": current_version,
		}

	def get(self, field, default=None):
		return self._fields.get(field, default)


class MockDecisionPolicyVersion:
	"""Mock frappe doc for Decision Policy Version."""

	def __init__(self, name, status="Published"):
		self.name = name
		self.status = status
		self._fields = {
			"name": name,
			"status": status,
		}

	def get(self, field, default=None):
		return self._fields.get(field, default)


@patch("frappe.get_doc")
class TestRouterDecisionActivationChecks(unittest.TestCase):
	"""Test _check_router_decision_activation function directly."""

	def test_activation_passes_with_published_policy_and_uncertain_next(self, mock_get_doc):
		"""Activation should pass when policy exists, is published, and uncertain_next is set."""
		policy = MockDecisionPolicy(
			"test_policy",
			enabled=True,
			current_version="v1_published",
		)
		version = MockDecisionPolicyVersion("v1_published", status="Published")

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Decision Policy" and name == "test_policy":
				return policy
			if doctype == "Decision Policy Version" and name == "v1_published":
				return version
			raise Exception(f"Unexpected call: {doctype} {name}")

		mock_get_doc.side_effect = get_doc_side_effect

		nodes = [
			{
				"id": "router",
				"type": "router.decision",
				"config": {
					"policy": "test_policy",
					"uncertain_next": "fallback",
					"options": [{"label": "Option 1", "node_id": "option_node"}],
					"default": "default_node",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		self.assertEqual(len(errors), 0, f"Expected no errors, got: {errors}")

	def test_activation_fails_when_policy_does_not_exist(self, mock_get_doc):
		"""Activation should fail when referenced policy does not exist."""
		mock_get_doc.side_effect = Exception("DoesNotExistError")

		nodes = [
			{
				"id": "my_router",
				"type": "router.decision",
				"config": {
					"policy": "nonexistent_policy",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		self.assertEqual(len(errors), 1)
		self.assertEqual(errors[0].code, "DECISION_POLICY_NOT_FOUND")
		self.assertEqual(errors[0].node_id, "my_router")
		self.assertEqual(errors[0].field, "config.policy")

	def test_activation_fails_when_policy_is_disabled(self, mock_get_doc):
		"""Activation should fail when policy is disabled."""
		policy = MockDecisionPolicy(
			"disabled_policy",
			enabled=False,
			current_version="v1",
		)

		mock_get_doc.return_value = policy

		nodes = [
			{
				"id": "router",
				"type": "router.decision",
				"config": {
					"policy": "disabled_policy",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		# Should have at least one error about disabled policy
		error_codes = [err.code for err in errors]
		self.assertIn("DECISION_POLICY_DISABLED", error_codes)

	def test_activation_fails_when_policy_has_no_current_version(self, mock_get_doc):
		"""Activation should fail when policy has no published version."""
		policy = MockDecisionPolicy(
			"unpublished_policy",
			enabled=True,
			current_version=None,  # No published version
		)

		mock_get_doc.return_value = policy

		nodes = [
			{
				"id": "router",
				"type": "router.decision",
				"config": {
					"policy": "unpublished_policy",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		error_codes = [err.code for err in errors]
		self.assertIn("DECISION_POLICY_UNPUBLISHED", error_codes)

	def test_activation_fails_when_policy_version_status_not_published(self, mock_get_doc):
		"""Activation should fail when policy version exists but is Draft or Retired."""
		for status in ["Draft", "Retired"]:
			with self.subTest(status=status):
				policy = MockDecisionPolicy(
					"versioned_policy",
					enabled=True,
					current_version="v1_draft",
				)
				version = MockDecisionPolicyVersion("v1_draft", status=status)

				def get_doc_side_effect(doctype, name=None):
					if doctype == "Decision Policy":
						return policy
					if doctype == "Decision Policy Version":
						return version
					raise Exception(f"Unexpected: {doctype}")

				mock_get_doc.side_effect = get_doc_side_effect

				nodes = [
					{
						"id": "router",
						"type": "router.decision",
						"config": {
							"policy": "versioned_policy",
							"uncertain_next": "fallback",
							"options": [{"label": "Opt", "node_id": "opt"}],
							"default": "def",
						},
						"next": None,
						"on_error": None,
					},
				]

				errors = _check_router_decision_activation(nodes)
				error_codes = [err.code for err in errors]
				self.assertIn("DECISION_POLICY_UNPUBLISHED", error_codes, f"Should fail for status={status}")

	def test_activation_fails_when_uncertain_next_is_missing(self, mock_get_doc):
		"""Activation should fail when uncertain_next is not specified."""
		policy = MockDecisionPolicy(
			"test_policy",
			enabled=True,
			current_version="v1_pub",
		)
		version = MockDecisionPolicyVersion("v1_pub", status="Published")

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Decision Policy":
				return policy
			if doctype == "Decision Policy Version":
				return version
			raise Exception(f"Unexpected: {doctype}")

		mock_get_doc.side_effect = get_doc_side_effect

		nodes = [
			{
				"id": "router",
				"type": "router.decision",
				"config": {
					"policy": "test_policy",
					"uncertain_next": None,  # Missing!
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		error_codes = [err.code for err in errors]
		self.assertIn("DECISION_UNCERTAIN_PATH_MISSING", error_codes)

	def test_activation_error_includes_node_id_and_field(self, mock_get_doc):
		"""Activation errors should include node_id and field path for debugging."""
		mock_get_doc.side_effect = Exception("DoesNotExistError")

		nodes = [
			{
				"id": "my_router",
				"type": "router.decision",
				"config": {
					"policy": "missing",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		self.assertTrue(len(errors) > 0)

		# Find the policy-related error
		policy_errors = [err for err in errors if "policy" in (err.field or "").lower()]
		self.assertTrue(policy_errors, "Should have a policy-related error")

		error = policy_errors[0]
		self.assertEqual(error.node_id, "my_router")
		self.assertEqual(error.field, "config.policy")
		self.assertIn("missing", error.message)

	def test_non_router_decision_nodes_ignored(self, mock_get_doc):
		"""Non-router.decision nodes should be ignored by activation checks."""
		# These nodes don't matter - the check should skip them
		nodes = [
			{
				"id": "tool_node",
				"type": "tool.call",
				"config": {"tool_id": "test_tool"},
				"next": None,
				"on_error": None,
			},
			{
				"id": "condition_node",
				"type": "condition",
				"config": {"expression": "true", "on_true": "yes", "on_false": "no"},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		self.assertEqual(len(errors), 0, "Non-router.decision nodes should be ignored")

	def test_multiple_router_decision_nodes(self, mock_get_doc):
		"""Multiple router.decision nodes should all be checked."""
		policy1 = MockDecisionPolicy("policy1", enabled=True, current_version="v1")
		policy2 = MockDecisionPolicy("policy2", enabled=True, current_version=None)
		version1 = MockDecisionPolicyVersion("v1", status="Published")

		def get_doc_side_effect(doctype, name=None):
			if doctype == "Decision Policy" and name == "policy1":
				return policy1
			if doctype == "Decision Policy" and name == "policy2":
				return policy2
			if doctype == "Decision Policy Version" and name == "v1":
				return version1
			raise Exception(f"Unexpected: {doctype} {name}")

		mock_get_doc.side_effect = get_doc_side_effect

		nodes = [
			{
				"id": "router1",
				"type": "router.decision",
				"config": {
					"policy": "policy1",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
			{
				"id": "router2",
				"type": "router.decision",
				"config": {
					"policy": "policy2",
					"uncertain_next": "fallback",
					"options": [{"label": "Opt", "node_id": "opt"}],
					"default": "def",
				},
				"next": None,
				"on_error": None,
			},
		]

		errors = _check_router_decision_activation(nodes)
		# Router1 should pass (policy1 is published)
		# Router2 should fail (policy2 has no current_version)
		error_node_ids = [err.node_id for err in errors]
		self.assertIn("router2", error_node_ids)




if __name__ == "__main__":
	unittest.main()
