"""Test record-level authorization for Agent Conversation doctype.

Tests the has_permission hook for Agent Conversation, verifying that
only the conversation owner, System Manager, or users with chat.view_all
can access a conversation.
"""

from unittest.mock import patch

import frappe
import pytest


def test_agent_conversation_owner_can_read():
	"""Owner of a conversation can read it."""
	# Create a test conversation owned by alice
	conv_doc = frappe.new_doc("Agent Conversation")
	conv_doc.agent = "Test Agent"
	conv_doc.owner = "alice@example.com"
	conv_doc.insert()

	try:
		# Verify alice can read it
		from huf.ai.record_access import user_can_read_conversation
		assert user_can_read_conversation(conv_doc, user="alice@example.com") is True
	finally:
		conv_doc.delete()


def test_agent_conversation_non_owner_cannot_read():
	"""Non-owner cannot read a conversation."""
	# Create a test conversation owned by alice
	conv_doc = frappe.new_doc("Agent Conversation")
	conv_doc.agent = "Test Agent"
	conv_doc.owner = "alice@example.com"
	conv_doc.insert()

	try:
		# Verify bob cannot read it
		from huf.ai.record_access import user_can_read_conversation
		assert user_can_read_conversation(conv_doc, user="bob@example.com") is False
	finally:
		conv_doc.delete()


def test_agent_conversation_system_manager_can_read():
	"""System Manager can read any conversation."""
	# Create a test conversation owned by alice
	conv_doc = frappe.new_doc("Agent Conversation")
	conv_doc.agent = "Test Agent"
	conv_doc.owner = "alice@example.com"
	conv_doc.insert()

	try:
		# Verify System Manager can read it
		from huf.ai.record_access import user_can_read_conversation
		assert user_can_read_conversation(conv_doc, user="Administrator") is True
	finally:
		conv_doc.delete()


def test_agent_conversation_chat_view_all_capability_can_read():
	"""A non-owner with the chat.view_all capability can read any conversation."""
	conv_doc = frappe.new_doc("Agent Conversation")
	conv_doc.agent = "Test Agent"
	conv_doc.owner = "alice@example.com"
	conv_doc.insert()

	try:
		from huf.ai.record_access import user_can_read_conversation

		with patch("huf.permissions.has_capability", return_value=True):
			assert user_can_read_conversation(conv_doc, user="carol@example.com") is True
	finally:
		conv_doc.delete()
