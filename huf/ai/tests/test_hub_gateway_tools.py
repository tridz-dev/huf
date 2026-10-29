# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Hub gateway setup tools (BE-HUBTOOLS, PLAN 4.3 P0a).

Verifies:
1. test_gateway_health, list_pairing_requests and approve_pairing_code are registered
   as integration tools; setup_gateway is NOT registered (it is P0b, BE-HUBSETUP).
2. The three tools are in BUILDER_TOOL_NAMES.
3. provision/seed of Hub Orchestrator attaches the three tools and the CHANNEL SETUP playbook.
4. A non-admin user is denied by all three handlers (system.integrations.manage).
5. An admin call returns the expected result shape.

Run with: run_tests.sh be-hubtools py huf.ai.tests.test_hub_gateway_tools
"""

import frappe
from frappe.tests import IntegrationTestCase

GATEWAY_TOOLS = {
	"test_gateway_health": "huf.ai.tools.gateway_pairing_tools.test_gateway_health",
	"list_pairing_requests": "huf.ai.tools.gateway_pairing_tools.list_pairing_requests",
	"approve_pairing_code": "huf.ai.tools.gateway_pairing_tools.approve_pairing_code",
}
NON_ADMIN_USER = "hub-gateway-nonadmin@example.com"


class _LazyModule:
	"""Defer heavy app imports until first use (bench discovers test modules before init)."""

	def __init__(self, module_path):
		self._module_path = module_path

	def __getattr__(self, name):
		import importlib

		return getattr(importlib.import_module(self._module_path), name)


hub_orchestrator_module = _LazyModule("huf.ai.app_seeding.hub_orchestrator")
registry_module = _LazyModule("huf.ai.tools._registry")
pairing_module = _LazyModule("huf.ai.tools.gateway_pairing_tools")


class TestHubGatewayTools(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		if frappe.db.exists("User", NON_ADMIN_USER):
			frappe.delete_doc("User", NON_ADMIN_USER, ignore_permissions=True, force=True)

	def _create_non_admin_user(self):
		if not frappe.db.exists("User", NON_ADMIN_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": NON_ADMIN_USER,
					"first_name": "Non",
					"last_name": "Admin",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		frappe.set_user(NON_ADMIN_USER)

	def test_gateway_tools_registered(self):
		entries = {t["tool_name"]: t for t in registry_module.ALL_INTEGRATION_TOOLS}
		for tool_name, function_path in GATEWAY_TOOLS.items():
			self.assertIn(tool_name, entries, f"{tool_name} not registered")
			self.assertEqual(entries[tool_name]["function_path"], function_path)

	def test_setup_gateway_not_registered(self):
		names = {t["tool_name"] for t in registry_module.ALL_INTEGRATION_TOOLS}
		self.assertNotIn("setup_gateway", names)

	def test_gateway_tools_in_builder_tool_names(self):
		for tool_name in GATEWAY_TOOLS:
			self.assertIn(tool_name, hub_orchestrator_module.BUILDER_TOOL_NAMES)
		self.assertNotIn("setup_gateway", hub_orchestrator_module.BUILDER_TOOL_NAMES)

	def test_provisioned_hub_agent_has_tools_and_playbook(self):
		hub_orchestrator_module.create_hub_orchestrator_agent()
		hub_orchestrator_module.provision_hub_orchestrator()

		agent = frappe.get_doc("Agent", hub_orchestrator_module.HUB_AGENT_NAME)
		attached = {row.tool for row in agent.get("agent_tool") or []}
		for tool_name in GATEWAY_TOOLS:
			self.assertIn(tool_name, attached, f"{tool_name} not attached to Hub Orchestrator")
		self.assertNotIn("setup_gateway", attached)

		instructions = agent.instructions or ""
		self.assertIn("CHANNEL SETUP", instructions)
		self.assertIn("/huf/channels/whatsapp/setup", instructions)
		self.assertIn("test_gateway_health", instructions)
		self.assertIn("approve_pairing_code", instructions)

	def test_non_admin_denied(self):
		self._create_non_admin_user()
		with self.assertRaises(frappe.PermissionError):
			pairing_module.test_gateway_health("Any Gateway")
		with self.assertRaises(frappe.PermissionError):
			pairing_module.list_pairing_requests()
		with self.assertRaises(frappe.PermissionError):
			pairing_module.approve_pairing_code("PAIR-ABCD2345", gateway_name="Any Gateway")

	def test_admin_calls_return_expected_shape(self):
		frappe.set_user("Administrator")

		health = pairing_module.test_gateway_health("Hub Test Missing Gateway")
		self.assertFalse(health["success"])
		self.assertIn("does not exist", health["error"])

		pending = pairing_module.list_pairing_requests("Hub Test Missing Gateway")
		self.assertIsInstance(pending, list)
		self.assertEqual(pending, [])

		approval = pairing_module.approve_pairing_code("")
		self.assertFalse(approval["success"])
		self.assertIn("required", approval["error"])
