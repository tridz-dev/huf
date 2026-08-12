"""
Unit tests for the conversation ownership check in
huf.ai.conversation_manager.ConversationManager.get_or_create_conversation.

Pure unit tests against the method using unittest.mock — they do not require
a live Frappe site/bench. Only the specific frappe APIs the method calls are
mocked (frappe.get_doc, frappe.session, huf.permissions.has_capability).

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_conversation_manager_access
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai.conversation_manager import ConversationManager


def _make_conversation(agent="Test Agent", owner="owner@example.com", session_id="sess-1", is_active=1):
    return SimpleNamespace(
        agent=agent,
        owner=owner,
        session_id=session_id,
        is_active=is_active,
    )


class TestGetOrCreateConversationOwnership(unittest.TestCase):
    def setUp(self):
        self.conv_manager = ConversationManager(
            agent_name="Test Agent", session_id="sess-1"
        )

    def _get_conversation(self, conversation_id="CONV-0001", conversation=None, user="owner@example.com"):
        conversation = conversation if conversation is not None else _make_conversation()

        def get_doc(doctype, name=None, *a, **kw):
            if doctype == "Agent Conversation":
                return conversation
            raise AssertionError(f"unexpected frappe.get_doc call: {doctype}")

        with patch("huf.ai.conversation_manager.frappe.get_doc", side_effect=get_doc), \
             patch("huf.ai.conversation_manager.frappe.session") as mock_session, \
             patch("huf.ai.conversation_manager.has_capability", return_value=False):
            mock_session.user = user
            return self.conv_manager.get_or_create_conversation(conversation_id=conversation_id)

    def test_owner_can_access_their_own_conversation(self):
        conversation = _make_conversation(owner="owner@example.com")
        result = self._get_conversation(conversation=conversation, user="owner@example.com")
        self.assertIs(result, conversation)

    def test_session_id_match_allows_access_for_guest_channel(self):
        conversation = _make_conversation(owner="Guest", session_id="sess-1")
        result = self._get_conversation(conversation=conversation, user="Guest")
        self.assertIs(result, conversation)

    def test_other_user_denied_without_ownership_session_or_capability(self):
        conversation = _make_conversation(owner="owner@example.com", session_id="other-session")
        with self.assertRaises(frappe.PermissionError):
            self._get_conversation(conversation=conversation, user="someone-else@example.com")

    def test_mismatched_agent_denied_even_for_owner(self):
        conversation = _make_conversation(agent="Other Agent", owner="owner@example.com")
        with self.assertRaises(frappe.PermissionError):
            self._get_conversation(conversation=conversation, user="owner@example.com")

    def test_missing_conversation_id_raises_same_generic_error_as_inaccessible(self):
        def get_doc(doctype, name=None, *a, **kw):
            raise frappe.DoesNotExistError

        with patch("huf.ai.conversation_manager.frappe.get_doc", side_effect=get_doc), \
             patch("huf.ai.conversation_manager.frappe.session") as mock_session, \
             patch("huf.ai.conversation_manager.has_capability", return_value=False):
            mock_session.user = "someone@example.com"
            with self.assertRaises(frappe.PermissionError):
                self.conv_manager.get_or_create_conversation(conversation_id="NONEXISTENT")

    def test_view_all_capability_grants_access_to_others_conversation(self):
        conversation = _make_conversation(owner="owner@example.com", session_id="other-session")

        def get_doc(doctype, name=None, *a, **kw):
            return conversation

        with patch("huf.ai.conversation_manager.frappe.get_doc", side_effect=get_doc), \
             patch("huf.ai.conversation_manager.frappe.session") as mock_session, \
             patch("huf.ai.conversation_manager.has_capability", return_value=True) as mock_cap:
            mock_session.user = "support@example.com"
            result = self.conv_manager.get_or_create_conversation(conversation_id="CONV-0001")

        self.assertIs(result, conversation)
        mock_cap.assert_called_once_with("support@example.com", "chat.view_all")


if __name__ == "__main__":
    unittest.main()
