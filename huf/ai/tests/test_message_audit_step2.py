# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Step 2 MessageAudit correctness/security fixes (MA-08/09/10/11).

These tests cover the critical fixes that must land before the larger
Result/Context Foundation V1 work in Step 3.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import log_tool_call, process_tool_call
from huf.ai.conversation_manager import ConversationManager, sync_tool_status_to_message
from huf.ai.providers.litellm import _merge_stream_usage


class _MessageAuditStep2TestCase(IntegrationTestCase):
    """Shared scaffolding for Step 2 tests."""

    def setUp(self):
        super().setUp()
        self._cleanup = []
        self._original_user = frappe.session.user
        frappe.set_user("Administrator")

        self.provider = self._get_or_create_provider()
        self.model = self._get_or_create_model(self.provider)
        self.agent = self._create_agent(self.provider, self.model)
        self.conversation = self._create_conversation(self.agent)

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype, name in reversed(self._cleanup):
            try:
                frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
            except Exception:
                pass
        frappe.set_user(self._original_user)
        super().tearDown()

    def _get_or_create_provider(self):
        existing = frappe.db.get_value("AI Provider", {"provider_name": "openai"}, "name")
        if existing:
            return existing
        provider = frappe.get_doc({
            "doctype": "AI Provider",
            "provider_name": "openai",
            "provider_type": "OpenAI Compatible",
        })
        provider.insert(ignore_permissions=True)
        self._cleanup.append(("AI Provider", provider.name))
        return provider.name

    def _get_or_create_model(self, provider):
        existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
        if existing:
            return existing
        model = frappe.get_doc({
            "doctype": "AI Model",
            "model_name": "gpt-4o-mini",
            "provider": provider,
        })
        model.insert(ignore_permissions=True)
        self._cleanup.append(("AI Model", model.name))
        return model.name

    def _create_agent(self, provider, model):
        agent = frappe.get_doc({
            "doctype": "Agent",
            "agent_name": f"test-agent-{frappe.generate_hash(length=8)}",
            "provider": provider,
            "model": model,
            "instructions": "You are a test agent for MessageAudit Step 2 tests.",
        })
        agent.insert(ignore_permissions=True)
        self._cleanup.append(("Agent", agent.name))
        return agent

    def _create_conversation(self, agent):
        conversation = frappe.get_doc({
            "doctype": "Agent Conversation",
            "agent": agent.name,
            "title": f"test-conv-{frappe.generate_hash(length=6)}",
            "session_id": f"test-session-{frappe.generate_hash(length=10)}",
            "is_active": 1,
        })
        conversation.insert(ignore_permissions=True)
        self._cleanup.append(("Agent Conversation", conversation.name))
        return conversation

    def _create_run(self, conversation):
        run = frappe.get_doc({
            "doctype": "Agent Run",
            "agent": self.agent.name,
            "conversation": conversation.name,
            "status": "Queued",
        })
        run.insert(ignore_permissions=True)
        self._cleanup.append(("Agent Run", run.name))
        return run

    def _create_tool_call_message(self, run, conversation, tool_call_name=None, call_id="call_1"):
        """Create a Queued Agent Tool Call and a linked Tool Call Agent Message."""
        process_tool_call(
            agent_run=run.name,
            conversation=conversation.name,
            name="test_tool",
            args={"query": "hello"},
            tool_call_id=call_id,
            is_output=False,
        )
        tc_name = frappe.db.get_value(
            "Agent Tool Call",
            {"agent_run": run.name, "call_id": call_id},
            "name",
        )
        self.assertTrue(tc_name)

        cm = ConversationManager(agent_name=self.agent.name, session_id=conversation.session_id)
        message = cm.add_message(
            conversation=conversation,
            role="agent",
            content="Requesting Tool: test_tool",
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
            run_name=run.name,
            kind="Tool Call",
            tool_call=tc_name,
            tool_call_id=call_id,
        )
        self._cleanup.append(("Agent Message", message.name))
        return tc_name, message.name


class TestFailedToolCalls(_MessageAuditStep2TestCase):
    """MA-08: failed tool calls must be recorded as Failed, not Completed."""

    def test_process_tool_call_marks_failed_with_error(self):
        run = self._create_run(self.conversation)
        tc_name, msg_name = self._create_tool_call_message(run, self.conversation)

        returned = process_tool_call(
            agent_run=run.name,
            conversation=self.conversation.name,
            result="something went wrong",
            error="boom",
            is_output=True,
            tool_call_id="call_1",
        )
        self.assertEqual(returned, tc_name)

        tc_doc = frappe.get_doc("Agent Tool Call", tc_name)
        self.assertEqual(tc_doc.status, "Failed")
        self.assertEqual(tc_doc.error_message, "boom")

        msg_doc = frappe.get_doc("Agent Message", msg_name)
        self.assertEqual(msg_doc.tool_status, "Failed")

    def test_process_tool_call_marks_success_completed(self):
        run = self._create_run(self.conversation)
        tc_name, msg_name = self._create_tool_call_message(run, self.conversation)

        process_tool_call(
            agent_run=run.name,
            conversation=self.conversation.name,
            result={"ok": True},
            is_output=True,
            tool_call_id="call_1",
        )

        tc_doc = frappe.get_doc("Agent Tool Call", tc_name)
        self.assertEqual(tc_doc.status, "Completed")
        self.assertFalse(tc_doc.error_message)

        msg_doc = frappe.get_doc("Agent Message", msg_name)
        self.assertEqual(msg_doc.tool_status, "Completed")

    def test_log_tool_call_propagates_failed_marker(self):
        run = self._create_run(self.conversation)
        tc_name, _msg_name = self._create_tool_call_message(run, self.conversation)

        returned = log_tool_call(
            run_doc=run,
            conversation=self.conversation,
            raw_call={
                "name": "test_tool",
                "id": "call_1",
                "output": "bad",
                "failed": True,
                "error_message": "marker error",
            },
            tool_result={"output": "bad"},
            is_output=True,
        )
        self.assertEqual(returned, tc_name)

        tc_doc = frappe.get_doc("Agent Tool Call", tc_name)
        self.assertEqual(tc_doc.status, "Failed")
        self.assertEqual(tc_doc.error_message, "marker error")


class TestStreamingTokenAggregation(_MessageAuditStep2TestCase):
    """MA-09: streaming token usage must be aggregated across tool rounds."""

    def test_merge_stream_usage_sums_dicts(self):
        totals = {}
        usage_a = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cached_tokens": 2,
            "cache_creation_tokens": 1,
        }
        usage_b = {
            "prompt_tokens": 20,
            "completion_tokens": 8,
            "cached_tokens": 3,
        }

        totals = _merge_stream_usage(totals, usage_a)
        totals = _merge_stream_usage(totals, usage_b)

        self.assertEqual(totals["prompt_tokens"], 30)
        self.assertEqual(totals["completion_tokens"], 13)
        self.assertEqual(totals["cached_tokens"], 5)
        self.assertEqual(totals["cache_creation_tokens"], 1)

    def test_merge_stream_usage_ignores_none_and_non_dict(self):
        totals = {"prompt_tokens": 5}
        self.assertEqual(_merge_stream_usage(totals, None), totals)
        self.assertEqual(_merge_stream_usage(totals, "not-a-dict"), totals)

    def test_merge_stream_usage_sums_across_object_like_usage(self):
        """Usage may arrive as a LiteLLM object; ensure dict()/model_dump() path works."""

        class _FakeUsage:
            def dict(self):
                return {
                    "prompt_tokens": 7,
                    "completion_tokens": 4,
                }

        totals = _merge_stream_usage({}, _FakeUsage())
        self.assertEqual(totals["prompt_tokens"], 7)
        self.assertEqual(totals["completion_tokens"], 4)


class TestToolStatusSync(_MessageAuditStep2TestCase):
    """MA-10: linked Agent Message tool fields stay in sync with Agent Tool Call."""

    def test_sync_tool_status_updates_message(self):
        run = self._create_run(self.conversation)
        tc_name, msg_name = self._create_tool_call_message(run, self.conversation)

        # Force the ATC to a terminal failed state without going through the
        # normal output path, then explicitly re-sync.
        tc_doc = frappe.get_doc("Agent Tool Call", tc_name)
        tc_doc.status = "Failed"
        tc_doc.error_message = "sync test error"
        tc_doc.tool = "renamed_tool"
        tc_doc.tool_args = json.dumps({"x": 1})
        tc_doc.save(ignore_permissions=True)

        sync_tool_status_to_message(tc_name)

        msg_doc = frappe.get_doc("Agent Message", msg_name)
        self.assertEqual(msg_doc.tool_status, "Failed")
        self.assertEqual(msg_doc.tool_name, "renamed_tool")
        self.assertEqual(msg_doc.tool_args, json.dumps({"x": 1}))

    def test_sync_tool_status_noop_for_missing_args(self):
        # Should not raise.
        sync_tool_status_to_message(None)
        sync_tool_status_to_message("nonexistent-tool-call-name")


class TestConversationIndexRace(_MessageAuditStep2TestCase):
    """MA-11: conversation_index must be unique and monotonically increasing."""

    def test_add_message_assigns_monotonic_indices(self):
        cm = ConversationManager(agent_name=self.agent.name, session_id=self.conversation.session_id)

        msg1 = cm.add_message(
            conversation=self.conversation,
            role="user",
            content="first",
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
        )
        msg2 = cm.add_message(
            conversation=self.conversation,
            role="user",
            content="second",
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
        )

        self.assertEqual(msg1.conversation_index, 1)
        self.assertEqual(msg2.conversation_index, 2)
        self.assertNotEqual(msg1.conversation_index, msg2.conversation_index)

    def test_duplicate_conversation_index_is_rejected(self):
        """The unique constraint added by the MA-11 patch rejects duplicates."""
        cm = ConversationManager(agent_name=self.agent.name, session_id=self.conversation.session_id)
        first = cm.add_message(
            conversation=self.conversation,
            role="user",
            content="first",
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
        )

        with self.assertRaises(frappe.UniqueValidationError):
            duplicate = frappe.get_doc({
                "doctype": "Agent Message",
                "conversation": self.conversation.name,
                "role": "user",
                "content": "duplicate index",
                "conversation_index": first.conversation_index,
                "user": frappe.session.user,
            })
            duplicate.insert(ignore_permissions=True)

    def test_retry_loop_recovers_after_transient_duplicate(self):
        """Simulate a transient duplicate by pre-allocating index 1; add_message
        should discover it and allocate index 2 on its retry."""
        cm = ConversationManager(agent_name=self.agent.name, session_id=self.conversation.session_id)

        # Pre-create a message at index 1.
        frappe.get_doc({
            "doctype": "Agent Message",
            "conversation": self.conversation.name,
            "role": "user",
            "content": "preallocated",
            "conversation_index": 1,
            "user": frappe.session.user,
        }).insert(ignore_permissions=True)

        # The first add_message attempt will read MAX=1, try index 2 and succeed.
        msg = cm.add_message(
            conversation=self.conversation,
            role="user",
            content="recovered",
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
        )
        self.assertEqual(msg.conversation_index, 2)
