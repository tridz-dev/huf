# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentConsole(HufTestSuite):
	"""Agent Console is a Single doctype with no custom controller logic —
	tests mutate and restore the single instance via self.change_settings."""

	def test_console_persists_agent_and_prompt(self):
		with self.change_settings(
			"Agent Console",
			agent_name=self.bootstrap.agent.name,
			prompt="Summarize today's sales",
		):
			console = frappe.get_single("Agent Console")

			self.assertEqual(console.agent_name, self.bootstrap.agent.name)
			self.assertEqual(console.prompt, "Summarize today's sales")

	def test_change_settings_restores_previous_values(self):
		before = frappe.get_single("Agent Console")
		original_agent = before.agent_name
		original_prompt = before.prompt

		with self.change_settings(
			"Agent Console",
			agent_name=self.bootstrap.agent.name,
			prompt="Temporary prompt",
		):
			console = frappe.get_single("Agent Console")
			self.assertEqual(console.prompt, "Temporary prompt")

		after = frappe.get_single("Agent Console")
		self.assertEqual(after.agent_name, original_agent)
		self.assertEqual(after.prompt, original_prompt)

	def test_agent_link_must_be_valid(self):
		with self.assertRaises(frappe.ValidationError):
			with self.change_settings("Agent Console", agent_name="Nonexistent Agent"):
				pass
