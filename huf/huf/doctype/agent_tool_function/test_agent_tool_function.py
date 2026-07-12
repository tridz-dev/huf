# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentToolFunction(HufTestSuite):
	def _make_tool_type(self, name="_Test Tool Type"):
		if frappe.db.exists("Agent Tool Type", name):
			return frappe.get_doc("Agent Tool Type", name)
		return frappe.get_doc({
			"doctype": "Agent Tool Type",
			"name1": name,
		}).insert(ignore_permissions=True)

	def _make_tool(self, **kwargs):
		tool_type = self._make_tool_type()
		doc = {
			"doctype": "Agent Tool Function",
			"tool_name": "_test_tool",
			"description": "A test tool function",
			"tool_type": tool_type.name,
		}
		doc.update(kwargs)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_get_document_tool(self):
		tool = self._make_tool(
			tool_name="_test_get_todo",
			types="Get Document",
			reference_doctype="ToDo",
		)

		# autoname is field:tool_name
		self.assertEqual(tool.name, "_test_get_todo")

		params = json.loads(tool.params)
		self.assertIn("document_id", params["properties"])

		definition = json.loads(tool.function_definition)
		self.assertEqual(definition["name"], "_test_get_todo")
		self.assertEqual(definition["parameters"], params)

	def test_tool_name_required(self):
		tool_type = self._make_tool_type()
		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({
				"doctype": "Agent Tool Function",
				"description": "Missing tool name",
				"tool_type": tool_type.name,
			}).insert(ignore_permissions=True)

	def test_reference_doctype_required_for_document_tools(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(
				tool_name="_test_missing_doctype",
				types="Get Document",
			)

	def test_invalid_tool_name_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(tool_name="invalid tool name with spaces")

	def test_core_function_name_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(tool_name="get_document")

	def test_custom_function_requires_function_path(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(
				tool_name="_test_custom",
				types="Custom Function",
			)

	def test_invalid_base_url_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(
				tool_name="_test_get_request",
				types="GET",
				base_url="ftp://example.com",
			)

	def test_reserved_http_parameter_name_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool(
				tool_name="_test_reserved_param",
				types="GET",
				parameters=[{
					"doctype": "Agent Function Params",
					"fieldname": "url",
					"label": "URL",
					"type": "string",
				}],
			)
