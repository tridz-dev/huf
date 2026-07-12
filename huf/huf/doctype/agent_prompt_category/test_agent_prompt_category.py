# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentPromptCategory(HufTestSuite):
	def test_name_set_from_category_name(self):
		category = frappe.get_doc({
			"doctype": "Agent Prompt Category",
			"category_name": "_Test Prompt Category",
		}).insert(ignore_permissions=True)

		self.assertEqual(category.name, "_Test Prompt Category")

	def test_category_name_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Prompt Category",
			}).insert(ignore_permissions=True)

	def test_category_cannot_be_its_own_parent(self):
		category = frappe.get_doc({
			"doctype": "Agent Prompt Category",
			"category_name": "_Test Self Parent Category",
		}).insert(ignore_permissions=True)

		category.parent_category = category.name
		with self.assertRaises(frappe.ValidationError):
			category.save(ignore_permissions=True)

	def test_parent_category_link(self):
		parent = frappe.get_doc({
			"doctype": "Agent Prompt Category",
			"category_name": "_Test Parent Category",
		}).insert(ignore_permissions=True)

		child = frappe.get_doc({
			"doctype": "Agent Prompt Category",
			"category_name": "_Test Child Category",
			"parent_category": parent.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(child.parent_category, parent.name)
