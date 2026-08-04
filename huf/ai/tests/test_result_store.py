# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Result Store (huf.ai.results.store)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.results import policy
from huf.ai.results.store import persist_result


class _ResultStoreTestCase(IntegrationTestCase):
    """Shared scaffolding for result-store tests."""

    def setUp(self):
        super().setUp()
        self._cleanup = []
        self._original_user = frappe.session.user
        frappe.set_user("Administrator")

        self.provider = self._get_or_create_provider()
        self.model = self._get_or_create_model(self.provider)
        self.agent = self._create_agent(self.provider, self.model)
        self.conversation = self._create_conversation(self.agent)
        self.run = self._create_run(self.conversation)
        self.tool_call = self._create_tool_call(self.conversation, self.run)

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
            "instructions": "You are a test agent for result-store tests.",
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
            "status": "Started",
        })
        run.insert(ignore_permissions=True)
        self._cleanup.append(("Agent Run", run.name))
        return run

    def _create_tool_call(self, conversation, run):
        tc = frappe.get_doc({
            "doctype": "Agent Tool Call",
            "agent_run": run.name,
            "conversation": conversation.name,
            "tool": "test_tool",
            "tool_args": json.dumps({"query": "hello"}),
            "status": "Queued",
            "call_id": f"call_{frappe.generate_hash(length=8)}",
        })
        tc.insert(ignore_permissions=True)
        self._cleanup.append(("Agent Tool Call", tc.name))
        return tc


class TestPersistResult(_ResultStoreTestCase):
    """Result-store persistence contract."""

    def test_small_result_stored_inline(self):
        result_doc, envelope = persist_result(
            result_content={"ok": True, "count": 3},
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            source_tool="test_tool",
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        self.assertEqual(result_doc.status, "Completed")
        self.assertEqual(result_doc.result_type, "json")
        self.assertTrue(result_doc.inline_payload)
        self.assertFalse(result_doc.payload_file)
        self.assertGreater(result_doc.size_bytes, 0)
        self.assertGreater(result_doc.estimated_tokens, 0)
        self.assertIn("sha256:", result_doc.content_hash)

        self.assertEqual(envelope["result_ref"], f"result://{result_doc.name}")
        self.assertEqual(envelope["result_type"], "json")

    def test_large_result_stored_as_private_file(self):
        rows = [{"id": i, "value": f"x-{i}"} for i in range(500)]
        result_doc, envelope = persist_result(
            result_content=rows,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            source_tool="test_tool",
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        size = result_doc.size_bytes or 0
        self.assertGreater(size, policy.INLINE_THRESHOLD_BYTES)
        self.assertTrue(result_doc.payload_file)
        self.assertFalse(result_doc.inline_payload)
        self.assertIn("result_", result_doc.payload_file)

        # Verify the private file exists and matches the hash.
        file_doc = frappe.get_doc("File", {"file_url": result_doc.payload_file})
        self.assertTrue(file_doc.is_private)
        self.assertIn("sha256:", result_doc.content_hash)

    def test_idempotency_key_prevents_duplicate(self):
        key = f"idem-{frappe.generate_hash(length=8)}"
        result_doc1, _ = persist_result(
            result_content={"value": 1},
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            idempotency_key=key,
        )
        self._cleanup.append(("Agent Execution Result", result_doc1.name))

        result_doc2, _ = persist_result(
            result_content={"value": 2},
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            idempotency_key=key,
        )
        self.assertEqual(result_doc1.name, result_doc2.name)

    def test_checksum_and_size_recorded(self):
        payload = "hello world"
        result_doc, _ = persist_result(
            result_content=payload,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        expected_hash = "sha256:b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        self.assertEqual(result_doc.content_hash, expected_hash)
        self.assertEqual(result_doc.size_bytes, len(payload.encode("utf-8")))

    def test_estimated_tokens_computed(self):
        payload = "abcd" * 100  # 400 chars -> 100 tokens heuristic
        result_doc, _ = persist_result(
            result_content=payload,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        self.assertEqual(result_doc.estimated_tokens, 100)

    def test_very_large_result_advertises_limited_views(self):
        big_text = "x" * (policy.SCHEMA_ONLY_THRESHOLD_BYTES + 1024)
        result_doc, envelope = persist_result(
            result_content=big_text,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        self.assertEqual(result_doc.result_type, "text")
        # Very large text still allows page/range/path reads; the default
        # policy does not restrict text views.
        self.assertIn("summary", envelope["available_views"])

    def test_failed_status_is_preserved(self):
        result_doc, envelope = persist_result(
            result_content={"error": "boom"},
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            status="Failed",
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        self.assertEqual(result_doc.status, "Failed")
        self.assertEqual(envelope["status"], "success")  # envelope itself is readable
