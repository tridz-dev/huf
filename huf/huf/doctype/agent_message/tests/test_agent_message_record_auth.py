"""Test record-level authorization for Agent Message doctype.

Tests the has_permission hook for Agent Message, verifying that only
users who own the message's conversation, System Manager, or users with
chat.view_all can access a message.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


class TestAgentMessageRecordAuth(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Agent", "Test Agent"):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": "Test Agent",
				"agent_modality": "Both",
				"instructions": "Test agent fixture for automated tests.",
			}).insert(ignore_permissions=True)

	def test_agent_message_conversation_owner_can_read(self):
		"""Owner of the message's conversation can read it."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test message in that conversation
		msg_doc = frappe.new_doc("Agent Message")
		msg_doc.conversation = conv_doc.name
		msg_doc.role = "user"
		msg_doc.content = "Test message"
		msg_doc.insert()

		try:
			# Verify alice can read it
			from huf.ai.record_access import user_can_read_message
			assert user_can_read_message(msg_doc, user="alice@example.com") is True
		finally:
			msg_doc.delete()
			conv_doc.delete()

	def test_agent_message_non_conversation_owner_cannot_read(self):
		"""Non-owner of the conversation cannot read its messages."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test message in that conversation
		msg_doc = frappe.new_doc("Agent Message")
		msg_doc.conversation = conv_doc.name
		msg_doc.role = "user"
		msg_doc.content = "Test message"
		msg_doc.insert()

		try:
			# Verify bob cannot read it
			from huf.ai.record_access import user_can_read_message
			assert user_can_read_message(msg_doc, user="bob@example.com") is False
		finally:
			msg_doc.delete()
			conv_doc.delete()

	def test_agent_message_system_manager_can_read(self):
		"""System Manager can read any message."""
		# Create a test conversation owned by alice
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		# Create a test message in that conversation
		msg_doc = frappe.new_doc("Agent Message")
		msg_doc.conversation = conv_doc.name
		msg_doc.role = "user"
		msg_doc.content = "Test message"
		msg_doc.insert()

		try:
			# Verify System Manager can read it
			from huf.ai.record_access import user_can_read_message
			assert user_can_read_message(msg_doc, user="Administrator") is True
		finally:
			msg_doc.delete()
			conv_doc.delete()

	def test_agent_message_chat_view_all_capability_can_read(self):
		"""A non-owner with the chat.view_all capability can read any message."""
		conv_doc = frappe.new_doc("Agent Conversation")
		conv_doc.agent = "Test Agent"
		conv_doc.owner = "alice@example.com"
		conv_doc.insert()

		msg_doc = frappe.new_doc("Agent Message")
		msg_doc.conversation = conv_doc.name
		msg_doc.role = "user"
		msg_doc.content = "Test message"
		msg_doc.insert()

		try:
			from huf.ai.record_access import user_can_read_message

			with patch("huf.permissions.has_capability", return_value=True):
				assert user_can_read_message(msg_doc, user="carol@example.com") is True
		finally:
			msg_doc.delete()
			conv_doc.delete()
