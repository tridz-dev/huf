# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentToolCall(HufTestSuite):
	def _make_agent_run(self):
		return frappe.get_doc({
			"doctype": "Agent Run",
			"agent": self.bootstrap.agent.name,
			"prompt": "Test prompt",
			"status": "Success",
		}).insert(ignore_permissions=True)

	def test_create_tool_call(self):
		tool_call = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"tool": "_test_tool",
			"status": "Completed",
			"call_id": "call_123",
		}).insert(ignore_permissions=True)

		self.assertTrue(tool_call.name)
		self.assertEqual(tool_call.tool, "_test_tool")
		self.assertEqual(tool_call.status, "Completed")
		self.assertEqual(tool_call.call_id, "call_123")

	def test_link_to_agent_run(self):
		run = self._make_agent_run()

		tool_call = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"agent_run": run.name,
			"tool": "_test_tool",
			"status": "Completed",
		}).insert(ignore_permissions=True)

		self.assertEqual(tool_call.agent_run, run.name)

	def test_invalid_agent_run_link_rejected(self):
		with self.assertRaises(frappe.LinkValidationError):
			frappe.get_doc({
				"doctype": "Agent Tool Call",
				"agent_run": "_Nonexistent Run",
				"tool": "_test_tool",
			}).insert(ignore_permissions=True)

	def test_tool_args_and_result_stored_as_json(self):
		tool_call = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"tool": "_test_tool",
			"status": "Completed",
			"tool_args": {"document_id": "TODO-0001"},
			"tool_result": {"success": True},
		}).insert(ignore_permissions=True)

		self.assertEqual(tool_call.tool_args, {"document_id": "TODO-0001"})
		self.assertEqual(tool_call.tool_result, {"success": True})

	def test_failed_status_with_error_message(self):
		tool_call = frappe.get_doc({
			"doctype": "Agent Tool Call",
			"tool": "_test_tool",
			"status": "Failed",
			"error_message": "Something went wrong",
		}).insert(ignore_permissions=True)

		self.assertEqual(tool_call.status, "Failed")
		self.assertEqual(tool_call.error_message, "Something went wrong")
