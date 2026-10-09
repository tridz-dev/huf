# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase


class TestAgentToolFunction(IntegrationTestCase):
	def _make_tool(self, types, parameters):
		return frappe.get_doc(
			{
				"doctype": "Agent Tool Function",
				"tool_name": f"test_{frappe.generate_hash(length=8)}",
				"types": types,
				"description": "Test tool",
				"reference_doctype": "Lead",
				"parameters": parameters,
			}
		)

	def _param(self, fieldname, type_="string", required=1):
		return {
			"label": fieldname,
			"fieldname": fieldname,
			"type": type_,
			"required": required,
			"description": fieldname,
		}

	def test_reserved_identifier_parameter_validates(self):
		tool = self._make_tool("Update Document", [self._param("document_id")])
		tool.validate_fields_for_doctype()

		tool = self._make_tool("Delete Multiple Documents", [self._param("document_ids", "array")])
		tool.validate_fields_for_doctype()

	def test_reserved_identifier_not_duplicated_in_schema(self):
		tool = self._make_tool("Update Document", [self._param("document_id")])
		schema = tool.build_params_json_from_table()
		self.assertEqual(schema["required"].count("document_id"), 1)
		self.assertEqual(list(schema["properties"]).count("document_id"), 1)
		json.dumps(schema)

	def test_unknown_fieldname_still_throws(self):
		tool = self._make_tool("Update Document", [self._param("not_a_real_field")])
		with self.assertRaises(frappe.ValidationError):
			tool.validate_fields_for_doctype()

	def test_identifier_not_reserved_for_other_types(self):
		tool = self._make_tool("Create Document", [self._param("document_id")])
		with self.assertRaises(frappe.ValidationError):
			tool.validate_fields_for_doctype()
