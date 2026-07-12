# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentPrompt(HufTestSuite):
	def test_prompt_group_set_for_new_lineage(self):
		prompt = frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "Test Agent Prompt",
			"prompt_body": "You are a helpful assistant.",
		}).insert(ignore_permissions=True)

		self.assertTrue(prompt.prompt_group)
		self.assertEqual(prompt.prompt_group, prompt.name)
		self.assertEqual(prompt.version, 1)
		self.assertEqual(prompt.is_latest, 1)

	def test_slug_generation(self):
		prompt = frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "My Agent Prompt",
			"prompt_body": "You are a helpful assistant.",
		}).insert(ignore_permissions=True)

		self.assertTrue(prompt.slug)
		self.assertIn("my-agent-prompt", prompt.slug)

	def test_version_inherits_prompt_group_from_previous_version(self):
		first = frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "Versioned Agent Prompt",
			"prompt_body": "Version 1",
		}).insert(ignore_permissions=True)

		second = frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "Versioned Agent Prompt",
			"prompt_body": "Version 2",
			"version": 2,
			"is_latest": 1,
			"previous_version": first.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(second.prompt_group, first.prompt_group)
		self.assertEqual(second.version, 2)
		self.assertNotEqual(second.slug, first.slug)

	def test_validate_requires_prompt_body(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Prompt",
				"title": "Invalid Prompt",
			}).insert(ignore_permissions=True)

	def test_validate_requires_title(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Prompt",
				"prompt_body": "You are a helpful assistant.",
			}).insert(ignore_permissions=True)

	def test_category_link(self):
		category = frappe.get_doc({
			"doctype": "Agent Prompt Category",
			"category_name": "_Test Prompt Link Category",
		}).insert(ignore_permissions=True)

		prompt = frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "Categorized Prompt",
			"prompt_body": "You are a helpful assistant.",
			"category": category.name,
		}).insert(ignore_permissions=True)

		self.assertEqual(prompt.category, category.name)
