# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import frappe

from huf.ai.agent_chat import get_history, render_markdown
from huf.tests.utils import HufTestSuite


class TestAgentChat(HufTestSuite):
	def _make_conversation(self, session_id="test:chat-session"):
		return frappe.get_doc({
			"doctype": "Agent Conversation",
			"title": "Chat Test Conversation",
			"agent": self.bootstrap.agent.name,
			"model": self.bootstrap.model.name,
			"session_id": session_id,
			"channel": "Chat",
		}).insert(ignore_permissions=True)

	def test_create_agent_chat_for_agent(self):
		chat = frappe.get_doc({
			"doctype": "Agent Chat",
			"agent": self.bootstrap.agent.name,
		}).insert(ignore_permissions=True)

		self.assertTrue(chat.name)
		self.assertEqual(chat.agent, self.bootstrap.agent.name)

	def test_invalid_agent_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Chat",
				"agent": "_Nonexistent Agent",
			}).insert(ignore_permissions=True)

	def test_get_history_returns_ordered_messages(self):
		conversation = self._make_conversation()
		for index, (role, content) in enumerate([
			("user", "Hello"),
			("agent", "Hi there!"),
		], start=1):
			frappe.get_doc({
				"doctype": "Agent Message",
				"conversation": conversation.name,
				"role": role,
				"kind": "Message",
				"content": content,
				"conversation_index": index,
			}).insert(ignore_permissions=True)

		history = get_history(conversation_id=conversation.name)

		self.assertEqual(len(history), 2)
		self.assertEqual(history[0]["role"], "user")
		self.assertEqual(history[0]["content"], "Hello")
		self.assertEqual(history[1]["role"], "agent")
		self.assertEqual(history[1]["conversation_index"], 2)

	def test_get_history_empty_without_conversation_id(self):
		self.assertEqual(get_history(), [])

	def test_render_markdown(self):
		html = render_markdown("**bold**")

		self.assertIn("<strong>bold</strong>", html)
