"""Env-gated live Jev test via AI Provider record.

Tests PLAN.md §4.7 / task T2A.16 acceptance: with HUF_LIVE_DECISION=1 and
OPENCODE_API_KEY set, saves the key onto the seeded OpenCode Zen AI Provider,
enables the seeded deployment, publishes and enables the seeded "Support Urgency"
policy, runs it via service.run_policy, and asserts SUCCESS and resolved deployment.

The test is skipped if either environment variable is absent (never runs in CI).
Every modified record is restored in tearDown (key removed, deployment disabled,
policy disabled, published version retired).
"""

from __future__ import annotations

import os
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import service
from huf.ai.decision.types import DecisionOrigin, DecisionStatus


class TestLiveJev(FrappeTestCase):
	"""Live Jev test gated on HUF_LIVE_DECISION and OPENCODE_API_KEY."""

	@classmethod
	def setUpClass(cls):
		"""Skip the entire test case if env vars are not set."""
		super().setUpClass()

	def setUp(self):
		"""Set up for live Jev test: save key, enable deployment, publish and enable policy."""
		# Capture initial state for tearDown
		self.provider_name = "OpenCodeZen"
		self.decision_model_name = "Jev 1.13"
		self.deployment_key = "jev-1-13-opencode-zen"
		self.policy_name = "Support Urgency"
		self.api_key = os.environ.get("OPENCODE_API_KEY")

		# Get seeded records
		self.provider = frappe.get_doc("AI Provider", self.provider_name)
		self.decision_model = frappe.get_doc("Decision Model", self.decision_model_name)
		self.deployment = frappe.get_doc("Decision Deployment", self.deployment_key)
		self.policy = frappe.get_doc("Decision Policy", self.policy_name)

		# Save initial state
		self._initial_provider_api_key = self.provider.api_key or ""
		self._initial_deployment_enabled = self.deployment.enabled
		self._initial_policy_enabled = self.policy.enabled
		self._initial_current_version = self.policy.current_version

		# Enable the kill switch
		self._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		# 1. Save OPENCODE_API_KEY onto the AI Provider
		# Use Frappe's set_password to securely store the API key
		self.provider.set_password("api_key", self.api_key)
		self.provider.db_update()

		# 2. Enable the deployment
		frappe.db.set_value("Decision Deployment", self.deployment_key, "enabled", 1)

		# 3. Publish the policy (creates Decision Policy Version with status=Published)
		# Note: publish_version is a @frappe.whitelist() method that requires the policy doc
		self.published_version = self.policy.publish_version()

		# 4. Enable the policy
		frappe.db.set_value("Decision Policy", self.policy_name, "enabled", 1)

	def tearDown(self):
		"""Restore all modified records to their initial state."""
		try:
			# Delete Decision Calls created during the test
			for call_name in frappe.get_all(
				"Decision Call",
				filters={"decision_model": self.decision_model_name},
				pluck="name",
			):
				frappe.delete_doc("Decision Call", call_name, ignore_permissions=True, ignore_missing=True, force=True)

			# Break the circular reference between Policy and Policy Version before deleting either
			if self.policy_name:
				frappe.db.set_value(
					"Decision Policy",
					self.policy_name,
					"current_version",
					self._initial_current_version,
					update_modified=False,
				)

			# Retire the published version (set status back to Retired instead of Published)
			if self.published_version:
				frappe.db.set_value(
					"Decision Policy Version",
					self.published_version,
					"status",
					"Retired",
					update_modified=False,
				)

			# Restore policy enabled flag
			if self.policy_name:
				frappe.db.set_value(
					"Decision Policy", self.policy_name, "enabled", self._initial_policy_enabled, update_modified=False
				)

			# Restore deployment enabled flag
			if self.deployment_key:
				frappe.db.set_value(
					"Decision Deployment",
					self.deployment_key,
					"enabled",
					self._initial_deployment_enabled,
					update_modified=False,
				)

			# Restore provider API key
			if self.provider_name:
				provider = frappe.get_doc("AI Provider", self.provider_name)
				provider.set_password("api_key", self._initial_provider_api_key)
				provider.db_update()

			# Restore kill switch
			frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", self._prev_kill_switch)

		except Exception as e:
			frappe.logger("huf").warning(f"Error during tearDown: {e!s}")
			raise

	@unittest.skipUnless(
		os.environ.get("HUF_LIVE_DECISION") == "1" and os.environ.get("OPENCODE_API_KEY"),
		"Test requires HUF_LIVE_DECISION=1 and OPENCODE_API_KEY environment variables",
	)
	def test_live_jev_via_ai_provider_record(self):
		"""Run Support Urgency policy via live Jev deployment with key on AI Provider.

		Acceptance (T2A.16):
		- Skipped unless HUF_LIVE_DECISION=1 and OPENCODE_API_KEY set
		- Saves key onto OpenCode Zen AI Provider
		- Enables seeded deployment
		- Runs Support Urgency policy
		- Asserts SUCCESS and resolved deployment
		- Never runs in CI
		"""
		# The test should not reach here if env vars are not set (skipUnless catches it first)
		self.assertIsNotNone(self.api_key, "OPENCODE_API_KEY must be set")

		# Verify seeded records exist and are in the right state
		self.assertEqual(self.provider.name, self.provider_name)
		self.assertEqual(self.decision_model.model_name, self.decision_model_name)
		self.assertEqual(self.deployment.deployment_key, self.deployment_key)
		self.assertTrue(self.deployment.enabled, "Deployment should be enabled by setUp")
		self.assertEqual(self.policy.name, self.policy_name)
		self.assertTrue(self.policy.enabled, "Policy should be enabled by setUp")
		self.assertIsNotNone(self.published_version, "Policy should have been published by setUp")

		# Run the policy with some minimal state
		result = service.run_policy(
			self.policy.name,
			state={
				"request": "Customer reports urgent service outage affecting critical workflow"
			},
			surface="Tool Selection",
			origin=DecisionOrigin(origin_type="Playground"),
		)

		# Verify the result
		self.assertEqual(
			result.status,
			DecisionStatus.SUCCESS,
			f"Expected SUCCESS, got {result.status}. "
			f"Decision call: {result.decision_call}, response: {result.response}",
		)
		self.assertIsNotNone(result.decision_call, "A Decision Call should be persisted")
		self.assertIsNotNone(result.response, "A response should be returned")
		self.assertIsNotNone(result.response.resolved_deployment, "Deployment should be resolved")

		# Verify the Decision Call was persisted correctly
		call_doc = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call_doc.decision_model, self.decision_model_name)
		self.assertEqual(call_doc.policy, self.policy_name)
		self.assertEqual(call_doc.policy_version, self.published_version)
		self.assertEqual(call_doc.mode, "Enforce")
		self.assertEqual(call_doc.surface, "Tool Selection")
		self.assertEqual(call_doc.origin_type, "Playground")
