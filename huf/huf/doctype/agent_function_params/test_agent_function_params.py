# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentFunctionParams(HufTestSuite):
	"""Agent Function Params is a child table (istable) on the `parameters`
	field of Agent Tool Function — it cannot be inserted standalone, so tests
	exercise it as rows on a parent Agent Tool Function document."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Agent Tool Type", "_Test Params Tool Type"):
			frappe.get_doc({
				"doctype": "Agent Tool Type",
				"name1": "_Test Params Tool Type",
			}).insert(ignore_permissions=True)
			frappe.db.commit()

	def _make_tool_function(self, tool_name, parameters):
		return frappe.get_doc({
			"doctype": "Agent Tool Function",
			"tool_name": tool_name,
			"description": "Test tool function for param rows",
			"tool_type": "_Test Params Tool Type",
			"parameters": parameters,
		}).insert(ignore_permissions=True)

	def test_param_rows_saved_with_parent(self):
		tool = self._make_tool_function(
			"_test_params_tool",
			[
				{"label": "Customer", "fieldname": "customer", "type": "string", "required": 1},
				{"label": "Limit", "fieldname": "limit", "type": "integer"},
			],
		)

		reloaded = frappe.get_doc("Agent Tool Function", tool.name)
		self.assertEqual(len(reloaded.parameters), 2)

		first, second = reloaded.parameters
		self.assertEqual(first.doctype, "Agent Function Params")
		self.assertEqual(first.fieldname, "customer")
		self.assertEqual(first.type, "string")
		self.assertEqual(first.required, 1)
		self.assertEqual(first.parent, tool.name)
		self.assertEqual(first.parentfield, "parameters")
		self.assertEqual(second.fieldname, "limit")
		self.assertEqual(second.type, "integer")

	def test_param_row_requires_label_fieldname_and_type(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool_function(
				"_test_params_missing_fields",
				[{"label": "Only Label"}],
			)

	def test_param_row_type_must_be_valid_select_option(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_tool_function(
				"_test_params_bad_type",
				[{"label": "Bad", "fieldname": "bad", "type": "not_a_type"}],
			)

	def test_tool_type_link_is_required_on_parent(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Tool Function",
				"tool_name": "_test_params_no_tool_type",
				"description": "Missing tool type",
				"parameters": [
					{"label": "Customer", "fieldname": "customer", "type": "string"},
				],
			}).insert(ignore_permissions=True)
