# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.tests.utils import HufTestSuite


class TestAgentConversation(HufTestSuite):
	def _make_conversation(self, **overrides):
		doc = {
			"doctype": "Agent Conversation",
			"title": "Test Conversation",
			"agent": self.bootstrap.agent.name,
			"model": self.bootstrap.model.name,
			"session_id": "test:session-1",
			"channel": "test",
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_conversation_for_agent(self):
		conversation = self._make_conversation()

		self.assertTrue(conversation.name)
		self.assertEqual(conversation.agent, self.bootstrap.agent.name)
		self.assertEqual(conversation.model, self.bootstrap.model.name)
		self.assertEqual(conversation.session_id, "test:session-1")
		self.assertEqual(conversation.is_active, 1)

	def test_session_id_required(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Conversation",
				"title": "No Session",
				"agent": self.bootstrap.agent.name,
			}).insert(ignore_permissions=True)

	def test_invalid_agent_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_conversation(agent="_Nonexistent Agent")

	def test_conversation_data_default(self):
		conversation = self._make_conversation(session_id="test:session-data")

		data = json.loads(conversation.conversation_data)
		self.assertEqual(data, {"version": 1, "items": []})

	def test_token_metrics_default_to_zero(self):
		conversation = self._make_conversation(session_id="test:session-metrics")

		self.assertEqual(conversation.total_input_tokens, 0)
		self.assertEqual(conversation.total_output_tokens, 0)
		self.assertEqual(conversation.total_tokens, 0)
		self.assertEqual(conversation.total_cost, 0)
