# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentSummaryPromptCategory(HufTestSuite):
	"""Agent Summary Prompt Category has no custom controller logic — tests
	cover creation, required-field validation and the parent link."""

	def test_name_set_from_category_name(self):
		category = frappe.get_doc({
			"doctype": "Agent Summary Prompt Category",
			"category_name": "_Test Summary Prompt Category",
		}).insert(ignore_permissions=True)

		self.assertEqual(category.name, "_Test Summary Prompt Category")

	def test_category_name_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Summary Prompt Category",
			}).insert(ignore_permissions=True)

	def test_parent_category_link(self):
		parent = frappe.get_doc({
			"doctype": "Agent Summary Prompt Category",
			"category_name": "_Test Summary Parent Category",
		}).insert(ignore_permissions=True)

		child = frappe.get_doc({
			"doctype": "Agent Summary Prompt Category",
			"category_name": "_Test Summary Child Category",
			"parent_category": parent.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(child.parent_category, parent.name)
