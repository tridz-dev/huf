# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for hub triage routing wiring: new tools in registry, BUILDER_TOOL_NAMES,
and orchestrator instructions.

Verifies:
1. find_existing_agents and discover_site_capabilities are in BUILDER_TOOL_NAMES
2. erpnext_list_reports is in BUILDER_TOOL_NAMES
3. erpnext_run_report is NOT in BUILDER_TOOL_NAMES
4. Each new tool exists in the registry with correct function_path
5. Hub Orchestrator instructions contain TRIAGE step before GATHER

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_hub_triage_wiring
"""

import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	"""Defer heavy app imports until first use.

	bench run-tests discovers (imports) test modules before frappe.init
	completes on some Frappe versions; importing modules eagerly can cause issues.
	"""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


hub_orchestrator_module = _LazyModule("huf.ai.app_seeding.hub_orchestrator")
registry_module = _LazyModule("huf.ai.tools._registry")


class TestHubTriageWiring(IntegrationTestCase):
	"""Verify hub triage routing integration."""

	def test_find_existing_agents_in_builder_tool_names(self):
		"""find_existing_agents must be in BUILDER_TOOL_NAMES."""
		self.assertIn(
			"find_existing_agents",
			hub_orchestrator_module.BUILDER_TOOL_NAMES,
			"find_existing_agents not in BUILDER_TOOL_NAMES"
		)

	def test_discover_site_capabilities_in_builder_tool_names(self):
		"""discover_site_capabilities must be in BUILDER_TOOL_NAMES."""
		self.assertIn(
			"discover_site_capabilities",
			hub_orchestrator_module.BUILDER_TOOL_NAMES,
			"discover_site_capabilities not in BUILDER_TOOL_NAMES"
		)

	def test_erpnext_list_reports_in_builder_tool_names(self):
		"""erpnext_list_reports must be in BUILDER_TOOL_NAMES."""
		self.assertIn(
			"erpnext_list_reports",
			hub_orchestrator_module.BUILDER_TOOL_NAMES,
			"erpnext_list_reports not in BUILDER_TOOL_NAMES"
		)

	def test_erpnext_run_report_not_in_builder_tool_names(self):
		"""erpnext_run_report must NOT be in BUILDER_TOOL_NAMES."""
		self.assertNotIn(
			"erpnext_run_report",
			hub_orchestrator_module.BUILDER_TOOL_NAMES,
			"erpnext_run_report should NOT be in BUILDER_TOOL_NAMES"
		)

	def test_find_existing_agents_in_registry(self):
		"""find_existing_agents must exist in registry with correct function_path."""
		tools = registry_module.BUILDER_TOOLS
		find_agent = next(
			(t for t in tools if t.get("tool_name") == "find_existing_agents"),
			None
		)
		self.assertIsNotNone(
			find_agent,
			"find_existing_agents not found in BUILDER_TOOLS"
		)
		self.assertEqual(
			find_agent.get("function_path"),
			"huf.ai.tools.hub_triage.find_existing_agents",
			"find_existing_agents has wrong function_path"
		)
		self.assertEqual(
			find_agent.get("category"),
			"Builder",
			"find_existing_agents has wrong category"
		)

	def test_discover_site_capabilities_in_registry(self):
		"""discover_site_capabilities must exist in registry with correct function_path."""
		tools = registry_module.BUILDER_TOOLS
		discover = next(
			(t for t in tools if t.get("tool_name") == "discover_site_capabilities"),
			None
		)
		self.assertIsNotNone(
			discover,
			"discover_site_capabilities not found in BUILDER_TOOLS"
		)
		self.assertEqual(
			discover.get("function_path"),
			"huf.ai.tools.hub_triage.discover_site_capabilities",
			"discover_site_capabilities has wrong function_path"
		)
		self.assertEqual(
			discover.get("category"),
			"Builder",
			"discover_site_capabilities has wrong category"
		)

	def test_hub_orchestrator_instructions_contain_triage(self):
		"""Hub Orchestrator instructions must contain TRIAGE step."""
		seed_path = Path(frappe.get_app_path("huf")) / "huf" / "agents" / "hub-orchestrator.json"
		with open(seed_path, encoding="utf-8") as f:
			seed_data = json.load(f)

		instructions = seed_data.get("instructions", "")
		self.assertIn("0. TRIAGE", instructions, "Instructions must contain '0. TRIAGE'")
		self.assertIn("find_existing_agents", instructions, "Instructions must mention 'find_existing_agents'")

	def test_triage_step_before_gather(self):
		"""TRIAGE step must appear before GATHER step in instructions."""
		seed_path = Path(frappe.get_app_path("huf")) / "huf" / "agents" / "hub-orchestrator.json"
		with open(seed_path, encoding="utf-8") as f:
			seed_data = json.load(f)

		instructions = seed_data.get("instructions", "")
		triage_idx = instructions.find("0. TRIAGE")
		gather_idx = instructions.find("1. GATHER")

		self.assertGreaterEqual(
			triage_idx,
			0,
			"TRIAGE step not found in instructions"
		)
		self.assertGreaterEqual(
			gather_idx,
			0,
			"GATHER step not found in instructions"
		)
		self.assertLess(
			triage_idx,
			gather_idx,
			"TRIAGE step must appear before GATHER step"
		)

	def test_existing_agent_instructions_refreshed(self):
		"""An already-provisioned agent with the old prompt gets the seeded one."""
		old = "You are the Hub Orchestrator.\n1. GATHER: ask."
		with (
			patch("frappe.db.exists", return_value=True),
			patch("frappe.db.get_value", return_value=old),
			patch("frappe.db.set_value") as set_value,
		):
			changed = hub_orchestrator_module.ensure_hub_orchestrator_instructions()
		self.assertTrue(changed)
		args = set_value.call_args[0]
		self.assertEqual(args[:3], ("Agent", "Hub Orchestrator", "instructions"))
		self.assertIn("0. TRIAGE", args[3])

	def test_current_instructions_left_alone(self):
		with (
			patch("frappe.db.exists", return_value=True),
			patch("frappe.db.get_value", return_value="x 0. TRIAGE y"),
			patch("frappe.db.set_value") as set_value,
		):
			self.assertFalse(hub_orchestrator_module.ensure_hub_orchestrator_instructions())
		set_value.assert_not_called()
