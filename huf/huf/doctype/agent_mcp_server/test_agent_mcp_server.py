# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import unittest
import json

import frappe
from frappe.tests import IntegrationTestCase


@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
class TestAgentMCPServer(IntegrationTestCase):
	def _make_provider_and_model(self):
		# Shared fixture: same provider/model can be reused across test
		# methods, so get-or-create instead of a bare insert.
		if frappe.db.exists("AI Provider", "_Test Provider"):
			provider = frappe.get_doc("AI Provider", "_Test Provider")
		else:
			provider = frappe.get_doc({
				"doctype": "AI Provider",
				"provider_name": "_Test Provider",
				"api_key": "sk-test",
				"provider_brand": "openai",
			}).insert(ignore_permissions=True)

		if frappe.db.exists("AI Model", {"provider": provider.name, "model_name": "_test-model"}):
			model = frappe.get_doc("AI Model", {"provider": provider.name, "model_name": "_test-model"})
		else:
			model = frappe.get_doc({
				"doctype": "AI Model",
				"provider": provider.name,
				"model_name": "_test-model",
			}).insert(ignore_permissions=True)
		return provider, model

	def _make_agent(self, agent_name="_Test Agent MCP"):
		_, model = self._make_provider_and_model()
		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": agent_name,
			"provider": model.provider,
			"model": model.name,
			"instructions": "You are a test agent.",
		}).insert(ignore_permissions=True)

	def _make_mcp_server(self, server_name="_Test MCP Server", available_tools=None):
		return frappe.get_doc({
			"doctype": "MCP Server",
			"server_name": server_name,
			"transport_type": "http",
			"server_url": "https://mcp.example.com/mcp",
			"available_tools": available_tools,
		}).insert(ignore_permissions=True)

	def test_tool_count_populated_from_available_tools(self):
		# Regression test: tool_count used to be populated by
		# AgentMCPServer.before_insert()/before_save(), which never fire on
		# Frappe v16 for child-table rows. Now populated by Agent.validate().
		agent = self._make_agent(agent_name="_Test Agent MCP Populated")
		tools = [{"name": f"tool_{i}"} for i in range(3)]
		server = self._make_mcp_server(server_name="_Test MCP Server Populated", available_tools=json.dumps(tools))

		agent.append("agent_mcp_server", {"doctype": "Agent MCP Server", "mcp_server": server.name})
		agent.save(ignore_permissions=True)

		self.assertEqual(agent.agent_mcp_server[0].tool_count, 3)

	def test_tool_count_zero_without_available_tools(self):
		agent = self._make_agent(agent_name="_Test Agent MCP Zero")
		server = self._make_mcp_server(server_name="_Test MCP Server Zero")

		agent.append("agent_mcp_server", {"doctype": "Agent MCP Server", "mcp_server": server.name})
		agent.save(ignore_permissions=True)

		self.assertEqual(agent.agent_mcp_server[0].tool_count, 0)
