"""Tests for conversation forking."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.conversation_fork import (
    FORK_MODES,
    _default_fork_title,
    fork_conversation_impl,
)


class TestConversationFork(unittest.TestCase):
    def _make_source_conv(self, **overrides):
        source = MagicMock()
        source.name = overrides.get("name", "CONV-SOURCE-001")
        source.title = overrides.get("title", "Original Chat")
        source.agent = overrides.get("agent", "AGENT-001")
        source.model = overrides.get("model", "gpt-4o")
        source.owner = overrides.get("owner", "user@example.com")
        source.session_id = overrides.get("session_id", "Chat:user@example.com")
        source.channel = overrides.get("channel", "Chat")
        return source

    def _make_target_conv(self, **overrides):
        target = MagicMock()
        target.name = overrides.get("name", "CONV-TARGET-001")
        target.title = overrides.get("title", "Original Chat (Fork)")
        target.agent = overrides.get("agent", "AGENT-001")
        target.model = overrides.get("model", "gpt-4o")
        target.session_id = overrides.get("session_id", "Chat:user@example.com")
        target.channel = overrides.get("channel", "Chat")
        return target

    def _make_message(self, **overrides):
        msg = MagicMock()
        msg.name = overrides.get("name", "MSG-001")
        msg.role = overrides.get("role", "user")
        msg.content = overrides.get("content", "Hello")
        msg.conversation_index = overrides.get("conversation_index", 1)
        msg.kind = overrides.get("kind", "Message")
        msg.is_agent_message = overrides.get("is_agent_message", 0)
        msg.agent = overrides.get("agent", "AGENT-001")
        msg.provider = overrides.get("provider", "OpenAI")
        msg.model = overrides.get("model", "gpt-4o")
        msg.user = overrides.get("user", "user@example.com")
        msg.session_id = overrides.get("session_id", "Chat:user@example.com")
        msg.agent_run = overrides.get("agent_run", None)
        msg.tool_call = overrides.get("tool_call", None)
        msg.tool_call_id = overrides.get("tool_call_id", None)
        msg.tool_calls = overrides.get("tool_calls", None)
        msg.tool_name = overrides.get("tool_name", None)
        msg.tool_args = overrides.get("tool_args", None)
        msg.tool_status = overrides.get("tool_status", None)
        msg.generated_image = overrides.get("generated_image", None)
        msg.generated_audio = overrides.get("generated_audio", None)
        msg.generated_video = overrides.get("generated_video", None)
        msg.voice_message = overrides.get("voice_message", None)
        msg.stt_model = overrides.get("stt_model", None)
        msg.status = overrides.get("status", None)
        msg.content_type = overrides.get("content_type", None)
        msg.context_policy = overrides.get("context_policy", None)
        msg.context_summary = overrides.get("context_summary", None)
        msg.record_kind = overrides.get("record_kind", None)
        msg.reference_doctype = overrides.get("reference_doctype", None)
        msg.reference_name = overrides.get("reference_name", None)
        msg.visibility = overrides.get("visibility", None)
        msg.token_estimate = overrides.get("token_estimate", None)
        msg.raw_payload = overrides.get("raw_payload", None)
        return msg

    @patch("huf.ai.conversation_fork.frappe.get_roles")
    @patch("huf.ai.conversation_fork.frappe.has_permission")
    @patch("huf.ai.conversation_fork.frappe.get_doc")
    def test_fork_requires_owner_or_system_manager(
        self, mock_get_doc, mock_has_permission, mock_get_roles
    ):
        source = self._make_source_conv(owner="other@example.com")
        mock_get_doc.return_value = source
        mock_has_permission.return_value = True
        mock_get_roles.return_value = ["All", "Huf User"]

        with self.assertRaises(Exception):
            fork_conversation_impl("CONV-SOURCE-001", "full_history")

    @patch("huf.ai.conversation_fork.frappe.has_permission")
    @patch("huf.ai.conversation_fork.frappe.get_doc")
    def test_fork_rejects_unknown_conversation(self, mock_get_doc, mock_has_permission):
        mock_get_doc.side_effect = frappe.DoesNotExistError
        mock_has_permission.return_value = True

        with self.assertRaises(Exception):
            fork_conversation_impl("CONV-MISSING", "full_history")

    @patch("huf.ai.conversation_fork.frappe.get_doc")
    def test_fork_rejects_invalid_mode(self, mock_get_doc):
        source = self._make_source_conv()
        mock_get_doc.return_value = source

        with self.assertRaises(Exception):
            fork_conversation_impl("CONV-SOURCE-001", "invalid_mode")

    @patch("huf.ai.conversation_fork.frappe.session")
    @patch("huf.ai.conversation_fork._update_total_messages")
    @patch("huf.ai.conversation_fork.frappe.get_doc")
    @patch("huf.ai.conversation_fork.frappe.get_all")
    @patch("huf.ai.conversation_fork.frappe.has_permission")
    @patch("huf.ai.conversation_manager.ConversationManager.create_new_conversation")
    @patch("huf.ai.conversation_fork.frappe.get_roles")
    def test_full_history_copies_messages(
        self,
        mock_get_roles,
        mock_create_conv,
        mock_has_permission,
        mock_get_all,
        mock_get_doc,
        mock_update_total,
        mock_session,
    ):
        mock_session.user = "user@example.com"
        source = self._make_source_conv()
        target = self._make_target_conv()
        user_msg = self._make_message(name="MSG-001", role="user", conversation_index=1)
        agent_msg = self._make_message(
            name="MSG-002",
            role="agent",
            is_agent_message=1,
            conversation_index=2,
            agent_run="RUN-001",
            tool_call="TC-001",
        )

        agent_doc = MagicMock()
        agent_doc.name = "AGENT-001"
        agent_doc.provider = "OpenAI"
        agent_doc.model = "gpt-4o"

        mock_get_roles.return_value = ["All"]
        mock_has_permission.return_value = True
        mock_create_conv.return_value = target
        # Source + agent doc + 2 source messages + 2 newly-created message docs.
        mock_get_doc.side_effect = [source, agent_doc, user_msg, agent_msg, MagicMock(), MagicMock()]
        mock_get_all.return_value = [{"name": "MSG-001"}, {"name": "MSG-002"}]

        result = fork_conversation_impl("CONV-SOURCE-001", "full_history")

        self.assertTrue(result["success"])
        self.assertEqual(result["conversation_id"], target.name)
        mock_create_conv.assert_called_once()
        # Source conversation + agent doc + two source messages + two new message docs.
        self.assertEqual(mock_get_doc.call_count, 6)
        mock_update_total.assert_called_once_with(target, 2)

    @patch("huf.ai.conversation_fork.frappe.session")
    @patch("huf.ai.conversation_fork._run_async_safely")
    @patch("huf.ai.conversation_fork._update_total_messages")
    @patch("huf.ai.conversation_fork.frappe.get_doc")
    @patch("huf.ai.conversation_fork.frappe.get_all")
    @patch("huf.ai.conversation_fork.frappe.has_permission")
    @patch("huf.ai.conversation_manager.ConversationManager.create_new_conversation")
    @patch("huf.ai.conversation_manager.ConversationManager.get_conversation_history")
    @patch("huf.ai.conversation_manager.ConversationManager.add_message")
    @patch("huf.ai.conversation_fork.frappe.get_roles")
    def test_summary_generates_summary(
        self,
        mock_get_roles,
        mock_add_message,
        mock_get_history,
        mock_create_conv,
        mock_has_permission,
        mock_get_all,
        mock_get_doc,
        mock_update_total,
        mock_run_async,
        mock_session,
    ):
        mock_session.user = "user@example.com"
        source = self._make_source_conv()
        target = self._make_target_conv()
        agent_doc = MagicMock()
        agent_doc.name = "AGENT-001"
        agent_doc.provider = "OpenAI"
        agent_doc.model = "gpt-4o"
        summary_msg = MagicMock()
        summary_msg.content = "Summary text"

        mock_get_roles.return_value = ["All"]
        mock_has_permission.return_value = True
        mock_create_conv.return_value = target
        mock_get_history.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        mock_run_async.return_value = "Generated summary"
        mock_add_message.return_value = summary_msg
        # No last user/assistant exchange in this scenario.
        mock_get_all.return_value = []
        mock_get_doc.side_effect = [source, agent_doc]

        result = fork_conversation_impl("CONV-SOURCE-001", "summary")

        self.assertTrue(result["success"])
        mock_run_async.assert_called_once()
        mock_add_message.assert_called_once()
        args, kwargs = mock_add_message.call_args
        self.assertEqual(kwargs["role"], "system")
        self.assertEqual(kwargs["record_kind"], "summary")
        mock_update_total.assert_called_once_with(target, 1)

    @patch("huf.ai.conversation_fork.frappe.session")
    @patch("huf.ai.conversation_fork._update_total_messages")
    @patch("huf.ai.conversation_fork.frappe.get_doc")
    @patch("huf.ai.conversation_fork.frappe.get_all")
    @patch("huf.ai.conversation_fork.frappe.has_permission")
    @patch("huf.ai.conversation_manager.ConversationManager.create_new_conversation")
    @patch("huf.ai.conversation_fork.frappe.get_roles")
    def test_last_output_copies_only_last_assistant(
        self,
        mock_get_roles,
        mock_create_conv,
        mock_has_permission,
        mock_get_all,
        mock_get_doc,
        mock_update_total,
        mock_session,
    ):
        mock_session.user = "user@example.com"
        source = self._make_source_conv()
        target = self._make_target_conv()
        agent_doc = MagicMock()
        agent_doc.name = "AGENT-001"
        agent_doc.provider = "OpenAI"
        agent_doc.model = "gpt-4o"
        agent_msg = self._make_message(
            name="MSG-002", role="agent", is_agent_message=1, conversation_index=2
        )

        mock_get_roles.return_value = ["All"]
        mock_has_permission.return_value = True
        mock_create_conv.return_value = target
        mock_get_all.return_value = [{"name": "MSG-002"}]
        # Source + agent doc + source message + newly-created message doc.
        mock_get_doc.side_effect = [source, agent_doc, agent_msg, MagicMock()]

        result = fork_conversation_impl("CONV-SOURCE-001", "last_output")

        self.assertTrue(result["success"])
        mock_update_total.assert_called_once_with(target, 1)

    def test_default_title(self):
        self.assertEqual(
            _default_fork_title(None, "Original Chat"),
            "Original Chat (Fork)",
        )

    def test_default_title_long_truncation(self):
        long_title = "x" * 200
        result = _default_fork_title(None, long_title)
        self.assertLessEqual(len(result), 140)
        self.assertTrue(result.endswith("…"))

    def test_custom_title_override(self):
        self.assertEqual(_default_fork_title("Custom Title", "Original"), "Custom Title")


if __name__ == "__main__":
    unittest.main()
