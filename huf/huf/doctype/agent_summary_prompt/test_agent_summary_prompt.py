# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestAgentSummaryPrompt(FrappeTestCase):
	def test_prompt_group_set_for_new_lineage(self):
		prompt = frappe.get_doc({
			"doctype": "Agent Summary Prompt",
			"title": "Test Summary Prompt",
			"prompt_body": "Summarize this: {summary_data}",
		}).insert(ignore_permissions=True)

		self.assertTrue(prompt.prompt_group)
		self.assertEqual(prompt.prompt_group, prompt.name)
		self.assertEqual(prompt.version, 1)
		self.assertEqual(prompt.is_latest, 1)

	def test_slug_generation(self):
		prompt = frappe.get_doc({
			"doctype": "Agent Summary Prompt",
			"title": "My Summary Prompt",
			"prompt_body": "Summarize this: {summary_data}",
		}).insert(ignore_permissions=True)

		self.assertTrue(prompt.slug)
		self.assertIn("my-summary-prompt", prompt.slug)

	def test_version_inheritance_on_new_version(self):
		first = frappe.get_doc({
			"doctype": "Agent Summary Prompt",
			"title": "Versioned Summary Prompt",
			"prompt_body": "Version 1",
		}).insert(ignore_permissions=True)

		first.is_latest = 0
		first.save(ignore_permissions=True)

		second = frappe.get_doc({
			"doctype": "Agent Summary Prompt",
			"title": "Versioned Summary Prompt",
			"prompt_body": "Version 2",
			"version": 2,
			"is_latest": 1,
			"previous_version": first.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(second.prompt_group, first.prompt_group)
		self.assertEqual(second.version, 2)

	def test_validate_requires_prompt_body(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Summary Prompt",
				"title": "Invalid Prompt",
			}).insert(ignore_permissions=True)
