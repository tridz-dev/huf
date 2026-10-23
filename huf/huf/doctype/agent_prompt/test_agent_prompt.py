# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.prompt_api import create_new_version, get_version_history


class TestAgentPrompt(IntegrationTestCase):
	def _create_prompt(self, prompt_body):
		return frappe.get_doc({
			"doctype": "Agent Prompt",
			"title": "Versioned Test Prompt",
			"prompt_body": prompt_body,
		}).insert(ignore_permissions=True)

	@patch("huf.ai.prompt_api._require")
	def test_saves_create_sequential_versions_and_keep_history(self, _require):
		first = self._create_prompt("Version 1")

		second_result = create_new_version(first.name, "Version 2")
		third_result = create_new_version(first.name, "Version 3")
		history = get_version_history(third_result["name"])

		self.assertEqual(second_result["version"], 2)
		self.assertEqual(third_result["version"], 3)
		self.assertEqual(
			frappe.db.get_value("Agent Prompt", third_result["name"], "previous_version"),
			second_result["name"],
		)
		self.assertEqual(
			[(item["version"], item["is_latest"]) for item in history],
			[(3, 1), (2, 0), (1, 0)],
		)
		self.assertEqual(
			[
				frappe.db.get_value("Agent Prompt", item["name"], "prompt_body")
				for item in reversed(history)
			],
			["Version 1", "Version 2", "Version 3"],
		)

	@patch("huf.ai.prompt_api._require")
	def test_repeated_version_save_does_not_create_duplicate(self, _require):
		first = self._create_prompt("Version 1")

		second_result = create_new_version(first.name, "Version 2")
		repeated_result = create_new_version(first.name, "Version 2")
		history = get_version_history(second_result["name"])

		self.assertTrue(second_result["created"])
		self.assertFalse(repeated_result["created"])
		self.assertEqual(repeated_result["name"], second_result["name"])
		self.assertEqual([item["version"] for item in history], [2, 1])
