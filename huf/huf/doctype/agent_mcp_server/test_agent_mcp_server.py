# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentMCPServer(HufTestSuite):
	def _make_mcp_server(self, available_tools=None):
		return frappe.get_doc({
			"doctype": "MCP Server",
			"server_name": "_Test MCP Server",
			"transport_type": "http",
			"server_url": "https://mcp.example.com/mcp",
			"available_tools": available_tools,
		}).insert(ignore_permissions=True)

	def _link_server(self, mcp_server=None):
		# Reload rather than mutate self.bootstrap.agent directly: it's a
		# class-level object shared across every test method, and tearDown's
		# db.rollback() only undoes DB state — it doesn't undo in-memory
		# .append() calls on that shared instance, which would otherwise leak
		# rows (or a failed-validation partial row) into later tests.
		agent = frappe.get_doc("Agent", self.bootstrap.agent.name)
		row = {"doctype": "Agent MCP Server"}
		if mcp_server is not None:
			row["mcp_server"] = mcp_server
		agent.append("agent_mcp_server", row)
		agent.save(ignore_permissions=True)
		return agent

	def test_link_mcp_server_to_agent(self):
		server = self._make_mcp_server()
		agent = self._link_server(server.name)

		self.assertEqual(len(agent.agent_mcp_server), 1)
		row = agent.agent_mcp_server[0]
		self.assertEqual(row.mcp_server, server.name)
		self.assertEqual(row.enabled, 1)

	def test_mcp_server_required(self):
		with self.assertRaises(frappe.ValidationError):
			self._link_server()

	def test_tool_count_populated_from_available_tools(self):
		tools = [{"name": f"tool_{i}"} for i in range(3)]
		server = self._make_mcp_server(available_tools=json.dumps(tools))

		agent = self._link_server(server.name)

		self.assertEqual(agent.agent_mcp_server[0].tool_count, 3)

	def test_tool_count_zero_without_available_tools(self):
		server = self._make_mcp_server()
		agent = self._link_server(server.name)

		self.assertEqual(agent.agent_mcp_server[0].tool_count, 0)

	def test_invalid_mcp_server_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._link_server("_Nonexistent MCP Server")
