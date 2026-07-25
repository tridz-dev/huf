"""Tests for conversation title autonaming realtime events."""

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.agent_integration import _emit_conversation_title_updated, generate_conversation_title


class TestConversationTitleAutonaming(unittest.TestCase):
	@patch("huf.ai.agent_integration.frappe.publish_realtime")
	@patch("huf.ai.agent_integration.frappe.db.get_value")
	def test_emit_conversation_title_updated_publishes_event(self, mock_get_value, mock_publish):
		mock_get_value.return_value = "user@example.com"

		_emit_conversation_title_updated("CONV-0001", "Invoice follow-up")

		mock_publish.assert_called_once_with(
			event="conversation:CONV-0001",
			message={
				"type": "conversation_title_updated",
				"conversation_id": "CONV-0001",
				"title": "Invoice follow-up",
			},
			user="user@example.com",
		)

	@patch("huf.ai.agent_integration._emit_conversation_title_updated")
	@patch("huf.ai.agent_integration._run_async_safely")
	@patch("huf.ai.agent_integration.frappe.db.commit")
	@patch("huf.ai.agent_integration.frappe.db.set_value")
	@patch("huf.ai.agent_integration.frappe.get_doc")
	@patch("huf.ai.agent_integration.ConversationManager")
	@patch("huf.ai.agent_integration.frappe.db.get_value")
	def test_generate_conversation_title_emits_realtime_event(
		self,
		mock_get_value,
		mock_conv_manager_cls,
		mock_get_doc,
		mock_set_value,
		mock_commit,
		mock_run_async,
		mock_emit,
	):
		mock_get_value.return_value = "Chat with Demo Agent"
		mock_conv_manager_cls.return_value.get_conversation_history.return_value = [
			{"role": "user", "content": "Help with invoices"}
		]
		mock_get_doc.return_value = MagicMock(provider="OpenAI", model="gpt-4o")
		mock_run_async.return_value = "Invoice help"

		generate_conversation_title("CONV-0001", "Demo Agent")

		mock_set_value.assert_called_once_with("Agent Conversation", "CONV-0001", "title", "Invoice help")
		mock_commit.assert_called_once()
		mock_emit.assert_called_once_with("CONV-0001", "Invoice help")

	@patch("huf.ai.agent_integration._emit_conversation_title_updated")
	@patch("huf.ai.agent_integration.frappe.db.get_value")
	def test_generate_conversation_title_skips_custom_titles(self, mock_get_value, mock_emit):
		mock_get_value.return_value = "Already renamed"

		generate_conversation_title("CONV-0001", "Demo Agent")

		mock_emit.assert_not_called()
