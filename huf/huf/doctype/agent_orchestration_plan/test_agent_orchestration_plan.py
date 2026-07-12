# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentOrchestrationPlan(HufTestSuite):
	"""Agent Orchestration Plan is a child table (istable) on the
	`agent_orchestration_plan` field of Agent Orchestration — it cannot be
	inserted standalone, so tests exercise it as rows on a parent
	Agent Orchestration document."""

	def _make_orchestration(self, plan_rows):
		return frappe.get_doc({
			"doctype": "Agent Orchestration",
			"agent": self.bootstrap.agent.name,
			"status": "Planned",
			"agent_orchestration_plan": plan_rows,
		}).insert(ignore_permissions=True)

	def test_plan_rows_saved_with_parent(self):
		orchestration = self._make_orchestration([
			{"step_index": 0, "status": "pending", "instruction": "Collect inputs"},
			{"step_index": 1, "status": "in_progress", "instruction": "Generate draft"},
		])

		reloaded = frappe.get_doc("Agent Orchestration", orchestration.name)
		self.assertEqual(len(reloaded.agent_orchestration_plan), 2)

		first, second = reloaded.agent_orchestration_plan
		self.assertEqual(first.doctype, "Agent Orchestration Plan")
		self.assertEqual(first.step_index, 0)
		self.assertEqual(first.status, "pending")
		self.assertEqual(first.instruction, "Collect inputs")
		self.assertEqual(first.parent, orchestration.name)
		self.assertEqual(first.parentfield, "agent_orchestration_plan")
		self.assertEqual(second.step_index, 1)
		self.assertEqual(second.status, "in_progress")

	def test_plan_row_status_must_be_valid_select_option(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_orchestration([
				{"step_index": 0, "status": "bogus", "instruction": "Bad status"},
			])

	def test_plan_row_output_ref_persists(self):
		orchestration = self._make_orchestration([
			{
				"step_index": 0,
				"status": "done",
				"instruction": "Fetch customer",
				"output_ref": "CUST-0001",
			},
		])

		row = frappe.get_doc("Agent Orchestration", orchestration.name).agent_orchestration_plan[0]
		self.assertEqual(row.status, "done")
		self.assertEqual(row.output_ref, "CUST-0001")
