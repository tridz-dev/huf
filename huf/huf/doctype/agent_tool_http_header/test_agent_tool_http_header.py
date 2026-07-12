# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentToolHTTPHeader(HufTestSuite):
	"""`Agent Tool HTTP Header` is a child table (istable=1) of the
	`http_headers` field on `Agent Tool Function`, so it is tested as rows on
	a parent Agent Tool Function."""

	def _make_tool_function(self, http_headers=None):
		if not frappe.db.exists("Agent Tool Type", "_Test Tool Type"):
			frappe.get_doc({
				"doctype": "Agent Tool Type",
				"name1": "_Test Tool Type",
			}).insert(ignore_permissions=True)

		return frappe.get_doc({
			"doctype": "Agent Tool Function",
			"tool_name": "_test_http_tool",
			"description": "A test HTTP tool",
			"types": "GET",
			"tool_type": "_Test Tool Type",
			"http_headers": http_headers or [],
		}).insert(ignore_permissions=True)

	def test_headers_saved_with_tool(self):
		tool = self._make_tool_function([
			{"doctype": "Agent Tool HTTP Header", "key": "Authorization", "value": "Bearer token"},
			{"doctype": "Agent Tool HTTP Header", "key": "X-Custom", "value": "custom-value"},
		])

		self.assertEqual(len(tool.http_headers), 2)
		self.assertEqual(tool.http_headers[0].key, "Authorization")
		self.assertEqual(tool.http_headers[0].value, "Bearer token")
		self.assertEqual(tool.http_headers[0].parenttype, "Agent Tool Function")
		self.assertEqual(tool.http_headers[1].key, "X-Custom")
		self.assertEqual(tool.http_headers[1].idx, 2)

	def test_crlf_in_header_key_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool_function([
				{"doctype": "Agent Tool HTTP Header", "key": "X-Key\nInjected", "value": "safe"},
			])

	def test_crlf_in_header_value_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool_function([
				{"doctype": "Agent Tool HTTP Header", "key": "X-Key", "value": "value\r\nInjected: evil"},
			])
