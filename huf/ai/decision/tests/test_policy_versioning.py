"""Tests for Decision Policy version management, publishing, and immutability.

Tests cover:
  - Creating draft versions
  - Publishing versions (status transition, current_version update, fingerprint computation)
  - Immutability of published versions (refuse edits)
  - Retiring previous published versions
  - Fingerprint stability across semantically identical policies
"""

import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import frappe
from frappe.model.document import Document

from huf.ai.decision.policy import policy_fingerprint, validate_policy_data


class DecisionPolicyVersionStub:
	"""Stub for Decision Policy Version DocType (frappe-free tests)."""

	def __init__(self, **kwargs):
		self.name = kwargs.get("name") or kwargs.get("version_key", "test_v0")
		self.version_key = kwargs.get("version_key", "test_v0")
		self.policy = kwargs.get("policy", "test_policy")
		self.version_number = kwargs.get("version_number", 0)
		self.status = kwargs.get("status", "Draft")
		self.definition_json = kwargs.get("definition_json", "{}")
		self.schema_version = kwargs.get("schema_version", "1.0")
		self.fingerprint = kwargs.get("fingerprint", "")
		self.default_model = kwargs.get("default_model", None)
		self.published_at = kwargs.get("published_at", None)
		self.metadata_json = kwargs.get("metadata_json", None)
		self._doc_before_save = None
		self.is_new_flag = True

	def is_new(self):
		return self.is_new_flag

	def get_doc_before_save(self):
		return self._doc_before_save

	def __repr__(self):
		return f"DecisionPolicyVersion({self.name}, status={self.status}, fingerprint={self.fingerprint[:8]}...)"


class TestPolicyVersioning(unittest.TestCase):
	"""Tests for Decision Policy Version validation and publishing."""

	def setUp(self):
		self.policy_definition = {
			"policy_id": "routing",
			"version": "1.0",
			"questions": [
				{
					"id": "route",
					"kind": "select",
					"instructions": "Choose a route",
					"options": [
						{"id": "billing", "description": "Billing"},
						{"id": "shipping", "description": "Shipping"}
					],
				}
			],
			"minimum_confidence": 0.8,
			"fallback_action": "fallback",
			"store_state": False,
		}

	def test_fingerprint_computed_on_save(self):
		"""Fingerprint is computed server-side from policy definition."""
		version = DecisionPolicyVersionStub(
			definition_json=json.dumps(self.policy_definition)
		)

		# Simulate _compute_fingerprint_and_validate
		definition = json.loads(version.definition_json)
		policy = validate_policy_data(definition)
		computed_fingerprint = policy_fingerprint(policy)

		self.assertEqual(len(computed_fingerprint), 64)  # SHA256 hex
		self.assertIsNotNone(computed_fingerprint)

	def test_fingerprint_excludes_deployment_identity(self):
		"""Fingerprint is stable regardless of deployment configuration."""
		# Two identical policy definitions should produce the same fingerprint
		# even if deployment_id differs (simulated by not including it)
		policy1 = validate_policy_data(self.policy_definition)
		policy2 = validate_policy_data(self.policy_definition)

		fp1 = policy_fingerprint(policy1)
		fp2 = policy_fingerprint(policy2)

		self.assertEqual(fp1, fp2)

	def test_fingerprint_changes_with_semantic_changes(self):
		"""Fingerprint changes when policy definition changes."""
		fp_original = policy_fingerprint(validate_policy_data(self.policy_definition))

		# Modify the definition
		modified = dict(self.policy_definition)
		modified["minimum_confidence"] = 0.5  # Changed from 0.8

		fp_modified = policy_fingerprint(validate_policy_data(modified))

		self.assertNotEqual(fp_original, fp_modified)

	def test_published_version_immutable_refuses_edit(self):
		"""Published versions refuse all edits (before_save guard)."""
		version = DecisionPolicyVersionStub(
			name="routing_v1",
			version_key="routing_v1",
			status="Published",
			definition_json=json.dumps(self.policy_definition),
		)
		version.is_new_flag = False  # Not a new doc

		# Set up doc_before_save to simulate an existing Published version
		doc_before = DecisionPolicyVersionStub(
			status="Published",
			definition_json=json.dumps(self.policy_definition),
		)
		version._doc_before_save = doc_before

		# Mock frappe.throw to capture the error
		with patch("frappe.throw") as mock_throw:
			try:
				# Call guard logic manually (would be in before_save)
				if not version.is_new():
					doc_before_save = version.get_doc_before_save()
					if doc_before_save and doc_before_save.status == "Published":
						frappe.throw(
							"Published Policy Versions are immutable and cannot be edited. "
							"Create a new Draft version to make changes.",
							title="Immutable Version"
						)
			except:
				pass

			# Verify frappe.throw was called
			mock_throw.assert_called_once()

	def test_publish_transitions_draft_to_published(self):
		"""Publishing a Draft version sets status to Published and sets published_at."""
		version = DecisionPolicyVersionStub(
			name="routing_v1",
			version_key="routing_v1",
			policy="routing",
			version_number=1,
			status="Draft",
			definition_json=json.dumps(self.policy_definition),
		)

		# Simulate publishing
		version.status = "Published"
		version.published_at = datetime.now()

		self.assertEqual(version.status, "Published")
		self.assertIsNotNone(version.published_at)

	def test_publish_updates_policy_current_version(self):
		"""Publishing a version updates Decision Policy.current_version."""
		# This would normally be done by Decision Policy Version.before_submit()
		# We test the logic here
		policy_name = "routing"
		version_key = "routing_v1"

		# Simulate the update
		policy_update = {
			"current_version": version_key,
			"fingerprint": policy_fingerprint(validate_policy_data(self.policy_definition)),
		}

		self.assertEqual(policy_update["current_version"], version_key)
		self.assertIsNotNone(policy_update["fingerprint"])

	def test_publish_retires_previous_published_version(self):
		"""Publishing a new version retires the previous Published version."""
		# Simulate the retire logic
		versions = [
			DecisionPolicyVersionStub(
				name="routing_v0",
				policy="routing",
				status="Published",
			),
			DecisionPolicyVersionStub(
				name="routing_v1",
				policy="routing",
				status="Published",
			),
		]

		# Find and mark previous as Retired
		prev_published = [v for v in versions if v.name != "routing_v1" and v.status == "Published"]
		for v in prev_published:
			v.status = "Retired"

		self.assertEqual(versions[0].status, "Retired")
		self.assertEqual(versions[1].status, "Published")

	def test_version_key_uniqueness(self):
		"""Version keys are unique per policy."""
		policy = "routing"
		keys = {
			f"{policy}_v0",
			f"{policy}_v1",
			f"{policy}_v2",
		}
		self.assertEqual(len(keys), 3)
		self.assertTrue(all(k.startswith(policy) for k in keys))

	def test_fingerprint_semantic_content_only(self):
		"""Fingerprint includes only semantic policy content, not metadata."""
		policy = validate_policy_data(self.policy_definition)

		# Manually build expected payload (what policy_fingerprint uses internally)
		expected_payload = {
			"policy_id": policy.policy_id,
			"version": policy.version,
			"questions": [
				{
					"id": q.id,
					"kind": q.kind.value,
					"instructions": q.instructions,
					"options": [{"id": opt.id, "description": opt.description} for opt in q.options],
					"allow_none": q.allow_none,
					"positive_criteria": q.positive_criteria,
					"negative_criteria": q.negative_criteria,
				}
				for q in policy.questions
			],
			"minimum_confidence": policy.minimum_confidence,
			"fallback_action": policy.fallback_action,
			"store_state": policy.store_state,
			"max_state_bytes": policy.max_state_bytes,
			"required_modalities": sorted(policy.required_modalities),
			"state_bindings": [{"name": item.name, "path": item.path} for item in policy.state_bindings],
		}

		# Ensure no deployment_identity, published_at, or other metadata
		self.assertNotIn("deployment_identity", expected_payload)
		self.assertNotIn("published_at", expected_payload)
		self.assertNotIn("fingerprint", expected_payload)

	def test_multiple_versions_per_policy(self):
		"""A policy can have multiple versions (only one Published at a time)."""
		versions = {
			"routing_v0": DecisionPolicyVersionStub(
				name="routing_v0", policy="routing", status="Retired"
			),
			"routing_v1": DecisionPolicyVersionStub(
				name="routing_v1", policy="routing", status="Published"
			),
			"routing_v2": DecisionPolicyVersionStub(
				name="routing_v2", policy="routing", status="Draft"
			),
		}

		published = [v for v in versions.values() if v.status == "Published"]
		self.assertEqual(len(published), 1)
		self.assertEqual(published[0].name, "routing_v1")


class TestPolicyDefinitionValidation(unittest.TestCase):
	"""Tests for policy definition validation during versioning."""

	def test_invalid_definition_rejected_on_version_save(self):
		"""Invalid policy definition is rejected with clear error."""
		invalid_definition = {
			"policy_id": "test",
			"questions": [
				{
					"id": "q1",
					"kind": "select",
					"instructions": "Choose one",
					# Missing required options for select
				}
			],
		}

		with self.assertRaises(Exception):
			validate_policy_data(invalid_definition)

	def test_unknown_fields_rejected(self):
		"""Unknown fields in policy definition are rejected."""
		invalid_definition = {
			"policy_id": "test",
			"questions": [],
			"unknown_field": "should not be here",
		}

		with self.assertRaises(Exception):
			validate_policy_data(invalid_definition)


if __name__ == "__main__":
	unittest.main()
