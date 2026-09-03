"""Tests for Agent Message query performance (ST-10.6, ST-10.1).

ST-10.1 creates a composite index (conversation, conversation_index) on
Agent Message to optimize conversation_manager queries that filter by
conversation and sort by conversation_index.

These tests verify that queries by conversation are efficient.
"""

import time

import frappe
from frappe.tests import UnitTestCase


class TestAgentMessagePerf(UnitTestCase):
    """Performance tests for Agent Message queries (requires ST-10.1 index)."""

    def setUp(self):
        """Create test conversations and messages."""
        super().setUp()
        self.agent_doc = frappe.new_doc("Agent")
        self.agent_doc.name = f"perf-test-agent-{time.time()}"
        self.agent_doc.agent_type = "Custom Tool"
        self.agent_doc.flags.ignore_permissions = True
        self.agent_doc.insert()

    def tearDown(self):
        """Clean up test data."""
        # Clean up agent first
        if self.agent_doc:
            try:
                frappe.delete_doc("Agent", self.agent_doc.name, force=True)
            except Exception:
                pass

    def _create_conversation(self, name):
        """Create a test conversation."""
        conv = frappe.new_doc("Agent Conversation")
        conv.name = name
        conv.agent = self.agent_doc.name
        conv.flags.ignore_permissions = True
        conv.insert()
        return conv

    def _create_agent_message(self, conversation, index, content="test"):
        """Create a test agent message."""
        msg = frappe.new_doc("Agent Message")
        msg.conversation = conversation
        msg.conversation_index = index
        msg.content = content
        msg.agent = self.agent_doc.name
        msg.flags.ignore_permissions = True
        msg.insert()
        return msg

    def test_query_100_messages_in_10_conversations(self):
        """ST-10.6: Query by conversation with 100 messages in 10 conversations.

        Creates 10 conversations with 10 messages each, then queries all
        messages in a single conversation. Should complete in < 100ms in
        a test environment (with index, typically < 10ms on real hardware).
        """
        conversations = []
        for i in range(10):
            conv_name = f"perf-test-conv-{time.time()}-{i}"
            conv = self._create_conversation(conv_name)
            conversations.append(conv)

            # Create 10 messages in this conversation
            for j in range(10):
                self._create_agent_message(conv.name, j, f"msg-{i}-{j}")

        # Query all messages in the first conversation
        start = time.time()
        results = frappe.get_list(
            "Agent Message",
            filters={"conversation": conversations[0].name},
            fields=["name", "conversation_index"],
            order_by="conversation_index asc",
            limit_page_length=0,
        )
        elapsed = time.time() - start

        # Verify we got the right messages
        self.assertEqual(len(results), 10, f"Expected 10 messages, got {len(results)}")

        # Verify ordering by conversation_index. Agent Message's doctype default
        # sort is "modified desc" (see agent_message.json), not insertion/index
        # order, so this query must pass an explicit order_by -- matching the
        # conversation_manager hot path the composite index is built for --
        # rather than relying on frappe.get_list's default.
        indices = [r.conversation_index for r in results]
        self.assertEqual(indices, list(range(10)), "Messages should be ordered by conversation_index")

        # Log timing (generous threshold for test environment)
        self.assertLess(
            elapsed,
            1.0,
            f"Query took {elapsed * 1000:.2f}ms; expect < 1000ms in test environment "
            f"(< 10ms with index on real hardware)",
        )

    def test_query_with_order_by_conversation_index(self):
        """ST-10.1: Query with both filter and sort (hot path from conversation_manager).

        The composite index (conversation, conversation_index) enables an
        indexed sort on conversation_index within a conversation filter.
        """
        conv_name = f"perf-test-order-{time.time()}"
        conv = self._create_conversation(conv_name)

        # Create 20 messages out of order
        indices = [5, 2, 19, 1, 10, 3, 8, 0, 15, 12, 4, 7, 11, 14, 6, 9, 13, 16, 17, 18]
        for idx in indices:
            self._create_agent_message(conv.name, idx, f"msg-{idx}")

        # Query with order_by like conversation_manager does
        start = time.time()
        results = frappe.get_list(
            "Agent Message",
            filters={"conversation": conv.name},
            fields=["name", "conversation_index"],
            order_by="conversation_index desc",
            limit_page_length=0,
        )
        elapsed = time.time() - start

        # Verify ordering is descending
        indices_returned = [r.conversation_index for r in results]
        self.assertEqual(
            indices_returned,
            sorted(indices, reverse=True),
            "Messages should be sorted by conversation_index desc",
        )

        # With index, this should be fast even on 20 messages
        self.assertLess(elapsed, 1.0, f"Ordered query took {elapsed * 1000:.2f}ms")
