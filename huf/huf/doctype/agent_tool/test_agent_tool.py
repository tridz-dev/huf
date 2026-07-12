# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentTool(HufTestSuite):
	"""`Agent Tool` is a child table (istable=1) of the `agent_tool` field on
	the `Agent` doctype, so it is tested as rows on a parent Agent."""

	def _make_tool_function(self, tool_name="_test_child_tool"):
		if not frappe.db.exists("Agent Tool Type", "_Test Tool Type"):
			frappe.get_doc({
				"doctype": "Agent Tool Type",
				"name1": "_Test Tool Type",
			}).insert(ignore_permissions=True)

		return frappe.get_doc({
			"doctype": "Agent Tool Function",
			"tool_name": tool_name,
			"description": "A test tool function",
			"tool_type": "_Test Tool Type",
		}).insert(ignore_permissions=True)

	def _make_agent(self, agent_tool):
		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": "_Test Agent Tool Parent",
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test assistant.",
			"agent_tool": agent_tool,
		}).insert(ignore_permissions=True)

	def test_tool_row_saved_on_agent(self):
		tool_function = self._make_tool_function()

		agent = self._make_agent([{
			"doctype": "Agent Tool",
			"tool": tool_function.name,
		}])

		self.assertEqual(len(agent.agent_tool), 1)
		row = agent.agent_tool[0]
		self.assertEqual(row.tool, tool_function.name)
		self.assertEqual(row.parenttype, "Agent")
		self.assertEqual(row.parent, agent.name)

	def test_tool_link_required(self):
		with self.assertRaises(frappe.MandatoryError):
			self._make_agent([{
				"doctype": "Agent Tool",
			}])

	def test_invalid_tool_link_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			self._make_agent([{
				"doctype": "Agent Tool",
				"tool": "_Nonexistent Tool",
			}])

	def test_multiple_tool_rows_keep_order(self):
		first = self._make_tool_function("_test_child_tool_first")
		second = self._make_tool_function("_test_child_tool_second")

		agent = self._make_agent([
			{"doctype": "Agent Tool", "tool": first.name},
			{"doctype": "Agent Tool", "tool": second.name},
		])

		self.assertEqual(len(agent.agent_tool), 2)
		self.assertEqual(agent.agent_tool[0].tool, first.name)
		self.assertEqual(agent.agent_tool[1].tool, second.name)
		self.assertEqual(agent.agent_tool[0].idx, 1)
		self.assertEqual(agent.agent_tool[1].idx, 2)
