# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentToolType(HufTestSuite):
	def test_create_tool_type(self):
		tool_type = frappe.get_doc({
			"doctype": "Agent Tool Type",
			"name1": "_Test Tool Type",
		}).insert(ignore_permissions=True)

		# autoname is field:name1
		self.assertEqual(tool_type.name, "_Test Tool Type")

	def test_name_required(self):
		# autoname is "field:name1", so a missing name1 is rejected at the
		# naming stage (plain ValidationError) before mandatory-field
		# validation ever runs — not frappe.MandatoryError.
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Tool Type",
			}).insert(ignore_permissions=True)

	def test_duplicate_name_rejected(self):
		frappe.get_doc({
			"doctype": "Agent Tool Type",
			"name1": "_Test Unique Type",
		}).insert(ignore_permissions=True)

		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc({
				"doctype": "Agent Tool Type",
				"name1": "_Test Unique Type",
			}).insert(ignore_permissions=True)

	def test_tool_function_links_to_tool_type(self):
		tool_type = frappe.get_doc({
			"doctype": "Agent Tool Type",
			"name1": "_Test Linked Type",
		}).insert(ignore_permissions=True)

		tool = frappe.get_doc({
			"doctype": "Agent Tool Function",
			"tool_name": "_test_linked_tool",
			"description": "Tool linked to a tool type",
			"tool_type": tool_type.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(tool.tool_type, tool_type.name)
