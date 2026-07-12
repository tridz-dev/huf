# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestMCPServerHeader(HufTestSuite):
	def _make_server(self, headers):
		return frappe.get_doc({
			"doctype": "MCP Server",
			"server_name": "_Test MCP Server",
			"transport_type": "http",
			"server_url": "https://mcp.example.com/mcp",
			"custom_headers": headers,
		})

	def test_header_row_created_with_parent(self):
		server = self._make_server([{
			"doctype": "MCP Server Header",
			"header_name": "X-Tenant-ID",
			"header_value": "tenant-123",
		}]).insert(ignore_permissions=True)

		self.assertEqual(len(server.custom_headers), 1)
		row = server.custom_headers[0]
		self.assertEqual(row.header_name, "X-Tenant-ID")
		self.assertEqual(row.header_value, "tenant-123")

	def test_header_name_required(self):
		server = self._make_server([{
			"doctype": "MCP Server Header",
			"header_value": "tenant-123",
		}])

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_header_value_required(self):
		server = self._make_server([{
			"doctype": "MCP Server Header",
			"header_name": "X-Tenant-ID",
		}])

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_multiple_headers_persist_in_order(self):
		server = self._make_server([
			{"doctype": "MCP Server Header", "header_name": "X-Tenant-ID", "header_value": "tenant-123"},
			{"doctype": "MCP Server Header", "header_name": "X-Trace-ID", "header_value": "trace-456"},
		]).insert(ignore_permissions=True)

		reloaded = frappe.get_doc("MCP Server", server.name)
		self.assertEqual(len(reloaded.custom_headers), 2)
		self.assertEqual(reloaded.custom_headers[0].header_name, "X-Tenant-ID")
		self.assertEqual(reloaded.custom_headers[1].header_name, "X-Trace-ID")

	def test_header_rows_removed_with_parent(self):
		server = self._make_server([{
			"doctype": "MCP Server Header",
			"header_name": "X-Tenant-ID",
			"header_value": "tenant-123",
		}]).insert(ignore_permissions=True)
		row_name = server.custom_headers[0].name

		server.delete()

		self.assertFalse(frappe.db.exists("MCP Server Header", row_name))
