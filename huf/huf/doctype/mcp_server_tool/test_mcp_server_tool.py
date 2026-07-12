# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestMCPServerTool(HufTestSuite):
	def _make_server(self, tools):
		return frappe.get_doc({
			"doctype": "MCP Server",
			"server_name": "_Test MCP Server",
			"transport_type": "http",
			"server_url": "https://mcp.example.com/mcp",
			"tools": tools,
		})

	def test_tool_row_created_with_parent(self):
		server = self._make_server([{
			"doctype": "MCP Server Tool",
			"tool_name": "send_email",
			"description": "Send an email via the MCP server",
			"parameters": '{"to": "string"}',
		}]).insert(ignore_permissions=True)

		self.assertEqual(len(server.tools), 1)
		row = server.tools[0]
		self.assertEqual(row.tool_name, "send_email")
		self.assertEqual(row.enabled, 1)
		self.assertEqual(row.description, "Send an email via the MCP server")
		self.assertEqual(row.parameters, '{"to": "string"}')

	def test_tool_name_required(self):
		server = self._make_server([{"doctype": "MCP Server Tool"}])

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_multiple_tools_persist_in_order(self):
		server = self._make_server([
			{"doctype": "MCP Server Tool", "tool_name": "list_issues"},
			{"doctype": "MCP Server Tool", "tool_name": "create_issue"},
		]).insert(ignore_permissions=True)

		reloaded = frappe.get_doc("MCP Server", server.name)
		self.assertEqual(len(reloaded.tools), 2)
		self.assertEqual(reloaded.tools[0].tool_name, "list_issues")
		self.assertEqual(reloaded.tools[1].tool_name, "create_issue")

	def test_tool_row_appended_on_parent_save(self):
		server = self._make_server([
			{"doctype": "MCP Server Tool", "tool_name": "list_issues"},
		]).insert(ignore_permissions=True)

		server.append("tools", {"doctype": "MCP Server Tool", "tool_name": "create_issue"})
		server.save(ignore_permissions=True)

		reloaded = frappe.get_doc("MCP Server", server.name)
		self.assertEqual(len(reloaded.tools), 2)

	def test_tool_rows_removed_with_parent(self):
		server = self._make_server([
			{"doctype": "MCP Server Tool", "tool_name": "list_issues"},
		]).insert(ignore_permissions=True)
		row_name = server.tools[0].name

		server.delete()

		self.assertFalse(frappe.db.exists("MCP Server Tool", row_name))
