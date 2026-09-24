"""Tests for Hub Orchestrator Agent Routing decision binding integration (T7.01).

Tests that find_existing_agents integrates with Decision Runtime via the Hub
Orchestrator Agent's Agent Routing binding (PLAN.md D7, §3.10), with harness
principle compliance: no output change when decision is off.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_hub_triage_decision
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.decision.types import DecisionOrigin, DecisionStatus, Option, ServiceResult, DecisionResponse
from huf.ai.decision.agent_surfaces import SurfaceDecision


class _LazyModule:
	"""Defer heavy app imports until first use."""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib
		return getattr(importlib.import_module(self._module_path), name)


hub_triage = _LazyModule("huf.ai.tools.hub_triage")
BUILDER_ROLES = ["System Manager"]


class TestFindExistingAgentsWithDecisionGolden(IntegrationTestCase):
	"""Golden test: verify Off output equals pre-decision structure (harness principle)."""

	def test_off_output_byte_identical_to_predecide(self):
		"""When decision is off or not enabled, output must not include decision_hint or decision_call."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
				{"name": "agent_2", "agent_name": "Customer Agent", "description": "Customers"},
			]),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		# Result must have exactly these keys: matches, query (no decision_hint, no decision_call)
		self.assertEqual(set(result.keys()), {"matches", "query"})

		# Matches must not have agent_id field
		for match in result["matches"]:
			self.assertNotIn("agent_id", match)
			self.assertIn("agent_name", match)
			self.assertIn("description", match)
			self.assertIn("tools", match)
			self.assertIn("score", match)


class TestFindExistingAgentsWithDecision(IntegrationTestCase):
	"""Tests for Agent Routing decision integration in find_existing_agents."""

	def _make_hub_agent(self):
		"""Create a mock Hub Orchestrator Agent doc."""
		return SimpleNamespace(
			name="Hub Orchestrator",
			agent_name="Hub Orchestrator",
			decision_bindings=[],
		)

	def test_kill_switch_off_returns_base_list(self):
		"""When Agent Settings.decision_runtime_enabled is 0, return base list unchanged."""
		settings = SimpleNamespace(decision_runtime_enabled=0)
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query"})
		self.assertEqual(len(result["matches"]), 1)

	def test_no_enabled_binding_returns_base_list(self):
		"""When Hub Agent has no enabled Agent Routing binding, return base list unchanged."""
		agent = self._make_hub_agent()
		binding = SimpleNamespace(
			surface="Agent Routing",
			mode="Off",
			enabled=False,
		)
		agent.decision_bindings = [binding]
		settings = SimpleNamespace(decision_runtime_enabled=1)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query"})

	def test_no_hub_agent_returns_base_list(self):
		"""When Hub Orchestrator doesn't exist, return base list unchanged."""
		settings = SimpleNamespace(decision_runtime_enabled=1)
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc") as mock_get_doc,
		):
			mock_get_doc.side_effect = frappe.DoesNotExistError()
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query"})

	def test_shadow_mode_enqueues_without_output_change(self):
		"""Shadow mode enqueues decision without changing output keys."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=None),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query"})

	def test_advise_mode_adds_hint_only(self):
		"""Advise mode adds decision_hint and decision_call only."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		advise_decision = SurfaceDecision(
			mode="Advise",
			selected_ids=None,
			hint="Decision suggestion (advisory, not an instruction): agents Invoice Agent (0.95), Customer Agent (0.72)",
			decision_call="DC-001",
		)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
				{"name": "agent_2", "agent_name": "Customer Agent", "description": "Customers"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=advise_decision),
			patch("huf.ai.tools.hub_triage._has_enabled_agent_routing_binding", return_value=True),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query", "decision_hint", "decision_call"})
		self.assertIn("Decision suggestion", result["decision_hint"])
		self.assertEqual(result["decision_call"], "DC-001")

	def test_enforce_mode_reranks_list(self):
		"""Enforce mode reranks and filters the agent list."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		enforce_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("agent_2", "agent_1"),
			hint=None,
			decision_call="DC-002",
		)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
				{"name": "agent_2", "agent_name": "Customer Agent", "description": "Customers"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=enforce_decision),
			patch("huf.ai.tools.hub_triage._has_enabled_agent_routing_binding", return_value=True),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query", "decision_call"})
		self.assertEqual(len(result["matches"]), 2)
		self.assertEqual(result["matches"][0]["agent_name"], "Customer Agent")
		self.assertEqual(result["matches"][1]["agent_name"], "Invoice Agent")

	def test_enforce_mode_filters_unselected(self):
		"""Enforce mode filters out agents not in selected_ids."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		enforce_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("agent_1",),
			hint=None,
			decision_call="DC-003",
		)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
				{"name": "agent_2", "agent_name": "Customer Agent", "description": "Customers"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=enforce_decision),
			patch("huf.ai.tools.hub_triage._has_enabled_agent_routing_binding", return_value=True),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=5)

		self.assertEqual(len(result["matches"]), 1)
		self.assertEqual(result["matches"][0]["agent_name"], "Invoice Agent")

	def test_decide_for_surface_origin_type_is_hub(self):
		"""Verify decide_for_surface receives origin_type='Hub' (not 'Hub Triage')."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("frappe.session") as mock_session,
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=None) as mock_decide,
			patch("huf.ai.tools.hub_triage._has_enabled_agent_routing_binding", return_value=True),
		):
			mock_session.user = "testuser@example.com"
			hub_triage.find_existing_agents(query="invoice", limit=5)

		mock_decide.assert_called_once()
		origin = mock_decide.call_args[1]["origin"]
		self.assertEqual(origin.origin_type, "Hub")
		self.assertEqual(origin.agent, "Hub Orchestrator")
		self.assertEqual(origin.owner_user, "testuser@example.com")

	def test_decision_exception_swallowed(self):
		"""Decision integration exceptions don't break result."""
		agent = self._make_hub_agent()
		settings = SimpleNamespace(decision_runtime_enabled=1)

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[
				{"name": "agent_1", "agent_name": "Invoice Agent", "description": "Invoices"},
			]),
			patch("frappe.get_all", return_value=[]),
			patch("frappe.get_single", return_value=settings),
			patch("frappe.get_doc", return_value=agent),
			patch("huf.ai.decision.agent_surfaces.decide_for_surface", side_effect=RuntimeError("boom")),
			patch("huf.ai.tools.hub_triage._has_enabled_agent_routing_binding", return_value=True),
			patch.object(frappe, "logger"),
		):
			result = hub_triage.find_existing_agents(query="invoice", limit=5)

		self.assertEqual(set(result.keys()), {"matches", "query"})
