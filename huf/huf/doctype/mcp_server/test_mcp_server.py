# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestMCPServer(HufTestSuite):
	def _make_server(self, **overrides):
		doc = {
			"doctype": "MCP Server",
			"server_name": "_Test MCP Server",
			"transport_type": "http",
			"server_url": "https://mcp.example.com/mcp",
		}
		doc.update(overrides)
		return frappe.get_doc(doc)

	def test_create_minimal_server(self):
		server = self._make_server().insert(ignore_permissions=True)

		self.assertEqual(server.name, "_Test MCP Server")
		self.assertEqual(server.transport_type, "http")
		self.assertEqual(server.enabled, 1)

	def test_server_name_required(self):
		server = self._make_server(server_name=None)

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_server_url_required(self):
		server = self._make_server(server_url=None)

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_auth_header_name_required_when_auth_enabled(self):
		server = self._make_server(auth_type="api_key", auth_header_name=None)

		with self.assertRaises(frappe.ValidationError):
			server.insert(ignore_permissions=True)

	def test_auth_none_and_oauth_skip_header_requirement(self):
		server_none = self._make_server(
			server_name="_Test MCP No Auth",
			auth_type="none",
			auth_header_name=None,
		).insert(ignore_permissions=True)
		self.assertEqual(server_none.auth_type, "none")

		server_oauth = self._make_server(
			server_name="_Test MCP OAuth",
			auth_type="oauth",
			auth_header_name=None,
		).insert(ignore_permissions=True)
		self.assertEqual(server_oauth.auth_type, "oauth")

	def test_duplicate_server_name_rejected(self):
		self._make_server().insert(ignore_permissions=True)

		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_server().insert(ignore_permissions=True)
