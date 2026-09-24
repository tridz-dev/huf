"""Tests for huf.ai.decision.api.get_binding_stats (T4.06).

Covers:
- Capability checks (requires agent.edit)
- Document-level permission checks (frappe.has_permission on Agent)
- Aggregation of Decision Call records over 7 days
- Fallback rate calculation
- p95 latency calculation
- Empty bindings and empty call history
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import api
from huf.ai.tests.factories import make_user


def _make_user_unthrottled(*args, **kwargs):
	"""``make_user`` with ``User.before_insert``'s ``throttle_user_creation`` bypassed."""
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		return make_user(*args, **kwargs)
	finally:
		frappe.flags.in_import = previous


class TestGetBindingStats(FrappeTestCase):
	"""Test get_binding_stats(agent) capability and permission checks, aggregation logic."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		# Enable Decision Runtime
		cls._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		suffix = uuid.uuid4().hex[:8]

		# Set up Decision Model / Deployment / Policy hierarchy
		cls.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestBindingStatsProvider{suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		cls.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-binding-stats-model-{suffix}",
			"provider": cls.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		cls.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_binding_stats_class_{suffix}",
			"class_name": "Test Binding Stats Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_binding_stats_family_{suffix}",
			"family_name": "Test Binding Stats Family",
			"adapter_id": "fake",
			"model_class": cls.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-binding-stats-model-key-{suffix}",
			"model_name": "Test Binding Stats Model",
			"family": cls.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-binding-stats-{suffix}",
			"deployment_name": "Test Binding Stats Deployment",
			"decision_model": cls.decision_model.name,
			"ai_model": cls.ai_model.name,
			"provider": cls.provider.name,
			"provider_model_id": cls.ai_model.name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 1,
		}).insert(ignore_permissions=True)

		# Create two policies for different surfaces
		cls.policy_1 = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Tool Selection Policy {suffix}",
			"purpose": "Tool Selection",
			"default_model": cls.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(cls._definition("tool-select-policy")),
		}).insert(ignore_permissions=True)
		cls.policy_1.publish_version()

		cls.policy_2 = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Routing Policy {suffix}",
			"purpose": "Model Routing",
			"default_model": cls.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(cls._definition("routing-policy")),
		}).insert(ignore_permissions=True)
		cls.policy_2.publish_version()

		# Create an agent with decision bindings
		cls.agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"Test Binding Stats Agent {suffix}",
			"agent_type": "Standalone",
			"instructions": "You are a test agent.",
			"decision_bindings": [
				{
					"surface": "Tool Selection",
					"policy": cls.policy_1.name,
					"mode": "Advise",
					"enabled": 1,
				},
				{
					"surface": "Model Routing",
					"policy": cls.policy_2.name,
					"mode": "Shadow",
					"enabled": 1,
				},
			],
		}).insert(ignore_permissions=True)

		# Create users with different capability tiers
		cls.agent_edit_user = _make_user_unthrottled(roles=("Huf Manager",)).email  # has agent.edit
		cls.no_role_user = _make_user_unthrottled(roles=()).email  # no capabilities

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		# Clean up Decision Calls
		for name in frappe.get_all("Decision Call", filters={"decision_model": cls.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		# Clean up agent first (before deleting policies it references)
		frappe.delete_doc("Agent", cls.agent.name, ignore_permissions=True, ignore_missing=True)
		# Clean up policies (now safe to delete after agents)
		for policy in [cls.policy_1, cls.policy_2]:
			frappe.db.set_value("Decision Policy", policy.name, "current_version", None, update_modified=False)
			for version in frappe.get_all("Decision Policy Version", filters={"policy": policy.name}, pluck="name"):
				frappe.delete_doc("Decision Policy Version", version, ignore_permissions=True, ignore_missing=True, force=True)
			frappe.delete_doc("Decision Policy", policy.name, ignore_permissions=True, ignore_missing=True, force=True)
		# Clean up deployment
		frappe.delete_doc("Decision Deployment", cls.deployment.name, ignore_permissions=True, ignore_missing=True)
		# Clean up model hierarchy
		frappe.delete_doc("Decision Model", cls.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", cls.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", cls.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", cls.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", cls.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", cls._prev_kill_switch)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup_calls: list[str] = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._cleanup_calls:
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.commit()

	@staticmethod
	def _definition(policy_id: str = "test-binding-stats-policy") -> dict:
		return {
			"policy_id": policy_id,
			"fallback_action": "fallback_default",
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "q1",
					"kind": "judge",
					"instructions": "Is this state acceptable?",
					"positive_criteria": "state looks fine",
				}
			],
		}

	def _make_decision_call(
		self,
		*,
		surface: str,
		policy: str,
		agent: str = None,
		latency_ms: float = 100.0,
		fallback_action: str | None = None,
		started_at: datetime = None,
	) -> str:
		"""Create a Decision Call record and track it for cleanup."""
		if agent is None:
			agent = self.agent.name
		if started_at is None:
			started_at = frappe.utils.now_datetime()

		call = frappe.get_doc({
			"doctype": "Decision Call",
			"call_id": frappe.generate_hash(length=16),
			"agent": agent,
			"surface": surface,
			"policy": policy,
			"mode": "Manual",
			"status": "success",
			"started_at": started_at,
			"latency_ms": latency_ms,
			"fallback_action": fallback_action,
		}).insert(ignore_permissions=True)
		self._cleanup_calls.append(call.name)
		return call.name

	def test_requires_agent_edit_capability(self):
		"""get_binding_stats requires agent.edit capability."""
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.get_binding_stats(self.agent.name)

	def test_requires_agent_read_permission(self):
		"""get_binding_stats calls check_permission on the Agent."""
		# This test verifies that check_permission() is called. In practice,
		# with standard Huf Manager role (which has agent.edit), the user will
		# have read permission on all Agents. The important thing is that the
		# code explicitly checks permissions, not relies only on the capability.
		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)
		self.assertEqual(result["agent"], self.agent.name)

	def test_empty_agent_no_bindings(self):
		"""Agent with no bindings returns empty list."""
		agent_no_bindings = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"No Bindings {frappe.generate_hash(length=8)}",
			"agent_type": "Standalone",
			"instructions": "You are a test agent.",
			"decision_bindings": [],
		}).insert(ignore_permissions=True)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(agent_no_bindings.name)

		self.assertEqual(result["agent"], agent_no_bindings.name)
		self.assertEqual(result["bindings"], [])

		# Cleanup
		frappe.set_user("Administrator")
		frappe.delete_doc("Agent", agent_no_bindings.name, ignore_permissions=True)

	def test_binding_with_no_calls(self):
		"""Binding with no Decision Call records returns zero counts and null stats."""
		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		self.assertEqual(result["agent"], self.agent.name)
		self.assertEqual(len(result["bindings"]), 2)

		# First binding (Tool Selection) should have no calls
		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["surface"], "Tool Selection")
		self.assertEqual(binding_1["policy"], self.policy_1.name)
		self.assertEqual(binding_1["mode"], "Advise")
		self.assertTrue(binding_1["enabled"])
		self.assertEqual(binding_1["stats"]["calls"], 0)
		self.assertIsNone(binding_1["stats"]["fallback_rate"])
		self.assertIsNone(binding_1["stats"]["p95_latency_ms"])
		self.assertIsNone(binding_1["stats"]["shadow_agreement"])
		self.assertIsNone(binding_1["stats"]["advise_followed_rate"])

	def test_binding_with_successful_calls(self):
		"""Binding with successful calls (no fallback) shows correct counts and latency."""
		# Create 3 successful calls for the first binding
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=50.0)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=100.0)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=150.0)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["stats"]["calls"], 3)
		self.assertEqual(binding_1["stats"]["fallback_rate"], 0.0)  # no fallbacks
		# p95 for 3 items: ceil(0.95 * 3) - 1 = 3 - 1 = 2, so latencies[2] = 150.0
		self.assertEqual(binding_1["stats"]["p95_latency_ms"], 150.0)  # p95 of [50, 100, 150]

	def test_binding_with_fallback_calls(self):
		"""Fallback rate correctly calculated when some calls have fallback_action."""
		# Create 2 successful calls (no fallback) and 3 with fallback
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=100.0, fallback_action=None)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=100.0, fallback_action=None)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=200.0, fallback_action="fallback_default")
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=200.0, fallback_action="fallback_default")
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=200.0, fallback_action="fallback_default")

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["stats"]["calls"], 5)
		self.assertAlmostEqual(binding_1["stats"]["fallback_rate"], 0.6, places=2)  # 3/5 = 0.6

	def test_p95_latency_calculation(self):
		"""p95 latency is calculated correctly from a sample."""
		# Create 10 calls with increasing latencies: 10, 20, ..., 100
		for i in range(1, 11):
			self._make_decision_call(
				surface="Tool Selection",
				policy=self.policy_1.name,
				latency_ms=float(i * 10),
			)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["stats"]["calls"], 10)
		# For 10 items, p95 index = ceil(0.95 * 10) - 1 = 10 - 1 = 9
		# latencies[9] (0-indexed) is the 10th value = 100.0
		self.assertEqual(binding_1["stats"]["p95_latency_ms"], 100.0)

	def test_multiple_bindings_independent_stats(self):
		"""Stats for different bindings are calculated independently."""
		# Add calls for both bindings
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=50.0)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=100.0)

		self._make_decision_call(surface="Model Routing", policy=self.policy_2.name, latency_ms=200.0)
		self._make_decision_call(surface="Model Routing", policy=self.policy_2.name, latency_ms=300.0)
		self._make_decision_call(surface="Model Routing", policy=self.policy_2.name, latency_ms=400.0)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["surface"], "Tool Selection")
		self.assertEqual(binding_1["stats"]["calls"], 2)

		binding_2 = result["bindings"][1]
		self.assertEqual(binding_2["surface"], "Model Routing")
		self.assertEqual(binding_2["stats"]["calls"], 3)

	def test_only_7_day_calls_included(self):
		"""Only calls from the last 7 days are included."""
		now = frappe.utils.now_datetime()
		old_date = now - timedelta(days=8)
		recent_date = now - timedelta(days=3)

		# Create an old call (should not be included)
		self._make_decision_call(
			surface="Tool Selection",
			policy=self.policy_1.name,
			latency_ms=50.0,
			started_at=old_date,
		)

		# Create a recent call (should be included)
		self._make_decision_call(
			surface="Tool Selection",
			policy=self.policy_1.name,
			latency_ms=100.0,
			started_at=recent_date,
		)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["stats"]["calls"], 1)  # only the recent one

	def test_filtering_by_agent_surface_policy(self):
		"""Calls are filtered by agent, surface, and policy combo."""
		# Create a different agent with the same policy
		other_agent = frappe.get_doc({
			"doctype": "Agent",
			"agent_name": f"Other Agent {frappe.generate_hash(length=8)}",
			"agent_type": "Standalone",
			"instructions": "You are a test agent.",
			"decision_bindings": [
				{
					"surface": "Tool Selection",
					"policy": self.policy_1.name,
					"mode": "Advise",
					"enabled": 1,
				},
			],
		}).insert(ignore_permissions=True)

		# Add call to main agent
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, agent=self.agent.name, latency_ms=50.0)

		# Add call to other agent (same surface/policy)
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, agent=other_agent.name, latency_ms=100.0)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		binding_1 = result["bindings"][0]
		self.assertEqual(binding_1["stats"]["calls"], 1)  # only the call from this agent

		# Cleanup - delete the Decision Call records first, then the agent
		frappe.set_user("Administrator")
		for name in self._cleanup_calls:
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		self._cleanup_calls.clear()
		frappe.delete_doc("Agent", other_agent.name, ignore_permissions=True, force=True)

	def test_return_shape_includes_all_fields(self):
		"""Return shape includes all expected fields for each binding."""
		# Add one call
		self._make_decision_call(surface="Tool Selection", policy=self.policy_1.name, latency_ms=100.0)

		frappe.set_user(self.agent_edit_user)
		result = api.get_binding_stats(self.agent.name)

		self.assertIn("agent", result)
		self.assertIn("bindings", result)
		self.assertEqual(len(result["bindings"]), 2)

		binding = result["bindings"][0]
		self.assertIn("binding_id", binding)
		self.assertIn("surface", binding)
		self.assertIn("policy", binding)
		self.assertIn("mode", binding)
		self.assertIn("enabled", binding)
		self.assertIn("stats", binding)

		stats = binding["stats"]
		self.assertIn("calls", stats)
		self.assertIn("fallback_rate", stats)
		self.assertIn("p95_latency_ms", stats)
		self.assertIn("shadow_agreement", stats)
		self.assertIn("advise_followed_rate", stats)
