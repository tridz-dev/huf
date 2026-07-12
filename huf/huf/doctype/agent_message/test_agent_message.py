# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

import json

import frappe

from huf.ai.agent_chat import add_message
from huf.tests.utils import HufTestSuite


class TestAgentMessage(HufTestSuite):
	def _make_conversation(self, session_id="test:message-session"):
		return frappe.get_doc({
			"doctype": "Agent Conversation",
			"title": "Message Test Conversation",
			"agent": self.bootstrap.agent.name,
			"model": self.bootstrap.model.name,
			"session_id": session_id,
			"channel": "test",
		}).insert(ignore_permissions=True)

	def _make_message(self, conversation, **overrides):
		doc = {
			"doctype": "Agent Message",
			"conversation": conversation.name,
			"role": "user",
			"kind": "Message",
			"content": "Hello, agent.",
			"user": frappe.session.user,
		}
		doc.update(overrides)
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def test_create_message_in_conversation(self):
		conversation = self._make_conversation()
		message = self._make_message(conversation)

		self.assertTrue(message.name)
		self.assertEqual(message.conversation, conversation.name)
		self.assertEqual(message.role, "user")
		self.assertEqual(message.content, "Hello, agent.")

	def test_message_defaults(self):
		conversation = self._make_conversation(session_id="test:defaults-session")
		message = frappe.get_doc({
			"doctype": "Agent Message",
			"conversation": conversation.name,
			"content": "Minimal message",
		}).insert(ignore_permissions=True)

		self.assertEqual(message.role, "user")
		self.assertEqual(message.visibility, "user_visible")
		self.assertEqual(message.is_agent_message, 0)

	def test_messages_belong_to_conversation(self):
		conversation = self._make_conversation(session_id="test:linked-session")
		self._make_message(conversation, content="First", conversation_index=1)
		self._make_message(conversation, content="Second", conversation_index=2)

		messages = frappe.get_all(
			"Agent Message",
			filters={"conversation": conversation.name},
			fields=["content"],
			order_by="conversation_index asc",
		)

		self.assertEqual([m.content for m in messages], ["First", "Second"])

	def test_invalid_conversation_link_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "Agent Message",
				"conversation": "_Nonexistent Conversation",
				"content": "Orphan message",
			}).insert(ignore_permissions=True)

	def test_tool_call_pairing_stored(self):
		conversation = self._make_conversation(session_id="test:toolcall-session")
		tool_call_id = "call_test_123"
		tool_calls = [{
			"id": tool_call_id,
			"type": "function",
			"function": {"name": "get_document", "arguments": "{}"},
		}]

		call_message = self._make_message(
			conversation,
			role="agent",
			kind="Tool Call",
			content="",
			tool_call_id=tool_call_id,
			tool_calls=json.dumps(tool_calls),
			conversation_index=1,
		)
		result_message = self._make_message(
			conversation,
			role="tool",
			kind="Tool Result",
			content='{"status": "ok"}',
			tool_call_id=tool_call_id,
			conversation_index=2,
		)

		self.assertEqual(call_message.tool_call_id, result_message.tool_call_id)
		self.assertEqual(json.loads(call_message.tool_calls)[0]["id"], tool_call_id)
		self.assertEqual(result_message.role, "tool")

	def test_add_message_api_assigns_index_and_links(self):
		conversation = self._make_conversation(session_id="test:api-session")

		first = add_message(conversation_id=conversation.name, role="user", content="Hi")
		second = add_message(conversation_id=conversation.name, role="agent", content="Hello!")

		self.assertTrue(first["success"])
		first_message = frappe.get_doc("Agent Message", first["message_id"])
		second_message = frappe.get_doc("Agent Message", second["message_id"])

		self.assertEqual(first_message.conversation, conversation.name)
		self.assertEqual(first_message.conversation_index, 1)
		self.assertEqual(second_message.conversation_index, 2)
		self.assertEqual(first_message.agent, self.bootstrap.agent.name)
		self.assertEqual(second_message.is_agent_message, 1)
