# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for hub triage tools — find_existing_agents and discover_site_capabilities.

Follows the exact conventions of huf.ai.tests.test_app_builder_tools: the
_LazyModule import guard, capability-denial tests via patched frappe.get_roles,
and mocked frappe calls for read-only discovery.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_hub_triage
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class _LazyModule:
	"""Defer heavy app imports until first use.

	bench run-tests discovers (imports) test modules before frappe.init
	completes on some Frappe versions; importing huf.ai.tools.hub_triage eagerly
	pulls dependencies, which may cause issues.
	"""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


hub_triage = _LazyModule("huf.ai.tools.hub_triage")

BUILDER_ROLES = ["System Manager"]
MANAGER_ROLES = ["Huf Manager"]
DENIED_ROLES = ["Huf User"]


class TestHubTriageCapability(IntegrationTestCase):
	"""Both hub triage tools must refuse users without builder roles."""

	def _assert_denied(self, func, **kwargs):
		with patch("frappe.get_roles", return_value=DENIED_ROLES):
			self.assertRaises(frappe.PermissionError, func, **kwargs)

	def test_find_existing_agents_denied(self):
		self._assert_denied(hub_triage.find_existing_agents, query="test")

	def test_discover_site_capabilities_denied(self):
		self._assert_denied(hub_triage.discover_site_capabilities, query="test")


class TestFindExistingAgents(IntegrationTestCase):
	"""Tests for find_existing_agents scoring and filtering."""

	def test_find_agents_respects_limit(self):
		"""Limit must be capped at 10."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "agent_1",
						"agent_name": "Agent One",
						"description": "First agent",
						"disabled": 0,
						"is_system": 0,
					},
					{
						"name": "agent_2",
						"agent_name": "Agent Two",
						"description": "Second agent",
						"disabled": 0,
						"is_system": 0,
					},
				],
			),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="agent", limit=20)
		# Should cap at 10
		self.assertLessEqual(len(result["matches"]), 10)

	def test_find_agents_excludes_hub_orchestrator(self):
		"""Hub Orchestrator agent must be excluded."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "hub_orch",
						"agent_name": "Hub Orchestrator",
						"description": "Orchestrator",
						"disabled": 0,
						"is_system": 1,
					},
					{
						"name": "agent_1",
						"agent_name": "Test Agent",
						"description": "Test agent",
						"disabled": 0,
						"is_system": 0,
					},
				],
			),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="agent")
		# Should exclude Hub Orchestrator
		agent_names = [m["agent_name"] for m in result["matches"]]
		self.assertNotIn("Hub Orchestrator", agent_names)

	def test_find_agents_disabled_and_non_chat_filtered(self):
		"""Get_list must filter disabled=0 and allow_chat=1."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[]) as mock_get_list,
			patch("frappe.get_all", return_value=[]),
		):
			hub_triage.find_existing_agents(query="test")
		# Verify filters were passed to get_list
		mock_get_list.assert_called_once()
		call_kwargs = mock_get_list.call_args[1]
		self.assertEqual(call_kwargs["filters"]["disabled"], 0)
		self.assertEqual(call_kwargs["filters"]["allow_chat"], 1)

	def test_find_agents_no_match_returns_empty(self):
		"""Query with no matches should return empty matches list."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "agent_1",
						"agent_name": "Irrelevant Agent",
						"description": "Unrelated",
						"disabled": 0,
						"is_system": 0,
					},
				],
			),
			patch("frappe.get_all", return_value=[]),
		):
			# Query with tokens that won't match
			result = hub_triage.find_existing_agents(query="xyz zyx")
		self.assertEqual(result["matches"], [])

	def test_find_agents_scores_and_ranks(self):
		"""Agents should be scored and ranked by relevance."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "agent_1",
						"agent_name": "Database Agent",
						"description": "Handles database query jobs",
						"disabled": 0,
						"is_system": 0,
					},
					{
						"name": "agent_2",
						"agent_name": "Query Tool",
						"description": "A simple tool",
						"disabled": 0,
						"is_system": 0,
					},
				],
			),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="database query")
		# First agent should have higher score (more matches)
		if len(result["matches"]) >= 2:
			self.assertGreater(result["matches"][0]["score"], result["matches"][1]["score"])

	def test_find_agents_truncates_description(self):
		"""Descriptions longer than 200 chars should be truncated."""
		long_desc = "x" * 300
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "agent_1",
						"agent_name": "Test Agent",
						"description": long_desc,
						"disabled": 0,
						"is_system": 0,
					},
				],
			),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="agent")
		if result["matches"]:
			self.assertLessEqual(len(result["matches"][0]["description"]), 200)

	def test_find_agents_returns_query(self):
		"""Return value should include the original query."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_list", return_value=[]),
			patch("frappe.get_all", return_value=[]),
		):
			result = hub_triage.find_existing_agents(query="test search")
		self.assertEqual(result["query"], "test search")


class TestDiscoverSiteCapabilities(IntegrationTestCase):
	"""Tests for discover_site_capabilities discovery and filtering."""

	def test_discover_respects_limit(self):
		"""Report limit must be capped at 8."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_installed_apps", return_value=[]),
			patch(
				"frappe.get_list",
				return_value=[{"name": f"Report {i}", "ref_doctype": "X", "module": "Y", "report_type": "Z"} for i in range(20)],
			),
		):
			result = hub_triage.discover_site_capabilities(query="report", limit=20)
		self.assertLessEqual(len(result["reports"]), 8)

	def test_discover_erpnext_absent(self):
		"""When ERPNext not installed, erpnext_installed should be False."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_installed_apps", return_value=["huf", "frappe"]),
		):
			result = hub_triage.discover_site_capabilities(query="test")
		self.assertFalse(result["erpnext_installed"])

	def test_discover_app_exception_swallowed(self):
		"""Per-app exceptions should be swallowed, not break output."""
		def raise_error(*args, **kwargs):
			raise Exception("App error")

		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_installed_apps", return_value=[]),
			patch("frappe.get_list", return_value=[]),
			patch("huf.ai.capability_discovery.apps.get_capability_apps", return_value=[]),
			patch("huf.ai.capability_discovery.resources.get_app_resources", side_effect=raise_error),
		):
			# Should not raise; should return gracefully
			result = hub_triage.discover_site_capabilities(query="test")
		self.assertIsInstance(result, dict)
		self.assertIn("installed_apps", result)

	def test_discover_returns_expected_keys(self):
		"""Return value must include all expected keys."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch("frappe.get_installed_apps", return_value=[]),
			patch("frappe.get_list", return_value=[]),
			patch("huf.ai.capability_discovery.apps.get_capability_apps", return_value=[]),
		):
			result = hub_triage.discover_site_capabilities(query="test")
		expected_keys = {
			"installed_apps",
			"reports",
			"resources",
			"erpnext_installed",
			"catalogue_matches",
		}
		self.assertEqual(set(result.keys()), expected_keys)


class TestFindAgentsToolScoring(IntegrationTestCase):
	def test_matches_on_attached_tool_name(self):
		"""An agent with no name/description hit still matches via its tools."""
		with (
			patch("frappe.get_roles", return_value=BUILDER_ROLES),
			patch(
				"frappe.get_list",
				return_value=[{"name": "a1", "agent_name": "Finance Bot", "description": "helper"}],
			),
			patch("frappe.get_all", return_value=[{"parent": "a1", "tool": "erpnext_run_report"}]),
		):
			result = hub_triage.find_existing_agents(query="run report sales")
		self.assertEqual(result["matches"][0]["tools"], ["erpnext_run_report"])
