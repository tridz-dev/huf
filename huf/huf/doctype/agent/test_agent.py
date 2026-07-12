# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.tests.utils import HufTestSuite


class TestAgent(HufTestSuite):
	def _make_agent(self, **overrides):
		doc = {
			"doctype": "Agent",
			"agent_name": "_Test Agent Alpha",
			"provider": self.bootstrap.provider.name,
			"model": self.bootstrap.model.name,
			"instructions": "You are a test assistant.",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_agent_with_required_fields(self):
		agent = self._make_agent()

		# autoname is "field:agent_name"
		self.assertEqual(agent.name, "_Test Agent Alpha")
		self.assertEqual(agent.provider, self.bootstrap.provider.name)
		self.assertEqual(agent.model, self.bootstrap.model.name)
		self.assertEqual(agent.prompt_mode, "Local")

	def test_agent_color_assigned_on_insert(self):
		agent = self._make_agent(agent_name="_Test Agent Colored")
		agent.reload()

		self.assertTrue(agent.agent_color)
		self.assertTrue(agent.agent_color.startswith("#"))

	def test_missing_instructions_rejected_in_local_mode(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "_Test Agent No Instructions",
				"provider": self.bootstrap.provider.name,
				"model": self.bootstrap.model.name,
			}).insert(ignore_permissions=True)

	def test_missing_provider_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "_Test Agent No Provider",
				"model": self.bootstrap.model.name,
				"instructions": "You are a test assistant.",
			}).insert(ignore_permissions=True)

	def test_allow_chat_requires_persist_conversation(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_agent(
				agent_name="_Test Agent Chat Misconfigured",
				allow_chat=1,
				persist_conversation=0,
			)

	def test_template_mode_requires_agent_prompt(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_agent(
				agent_name="_Test Agent Template Missing",
				prompt_mode="Template",
			)
