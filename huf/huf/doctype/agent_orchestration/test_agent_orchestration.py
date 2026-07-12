# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentOrchestration(HufTestSuite):
	"""Agent Orchestration has no custom controller logic — tests cover
	creation, the agent link and select-field validation."""

	def test_creation_with_agent_link(self):
		orchestration = frappe.get_doc({
			"doctype": "Agent Orchestration",
			"agent": self.bootstrap.agent.name,
			"status": "Planned",
		}).insert(ignore_permissions=True)

		self.assertTrue(orchestration.name)
		self.assertEqual(orchestration.agent, self.bootstrap.agent.name)
		self.assertEqual(orchestration.status, "Planned")

	def test_creation_without_agent(self):
		orchestration = frappe.get_doc({
			"doctype": "Agent Orchestration",
			"status": "Running",
			"current_step": 1,
			"scratchpad": "working notes",
		}).insert(ignore_permissions=True)

		self.assertTrue(orchestration.name)
		self.assertEqual(orchestration.status, "Running")
		self.assertEqual(orchestration.current_step, 1)
		self.assertEqual(orchestration.scratchpad, "working notes")

	def test_invalid_status_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Orchestration",
				"agent": self.bootstrap.agent.name,
				"status": "Bogus",
			}).insert(ignore_permissions=True)

	def test_agent_link_must_be_valid(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Orchestration",
				"agent": "Nonexistent Agent",
			}).insert(ignore_permissions=True)
