# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Large-result context exclusion regression tests (Step 3)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.conversation_manager import ConversationManager
from huf.ai.results import policy
from huf.ai.results.store import persist_result
from huf.ai.results.views import result_read


class TestResultContextExclusion(IntegrationTestCase):
    """Result payloads must stay outside Agent Message and model context."""

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
        self.cm = ConversationManager(agent_name=self.agent.name, session_id=self.conversation.session_id)

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
            "instructions": "You are a test agent for result-context tests.",
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

    def _persist_large_result(self, row_count: int = 100_000):
        rows = [{"id": i, "value": f"row-{i}"} for i in range(row_count)]
        result_doc, _ = persist_result(
            result_content=rows,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            source_tool="test_tool",
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))
        return result_doc, rows

    def test_large_result_stored_outside_message_content(self):
        """A 100k-row result is stored as a file; the message content is an envelope."""
        result_doc, _ = self._persist_large_result(row_count=100_000)

        # Simulate the message that update_tool_call_message would create.
        message = self.cm.add_message(
            conversation=self.conversation,
            role="tool",
            content=json.dumps({"result_ref": f"result://{result_doc.name}"}),
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
            run_name=self.run.name,
            kind="Tool Result",
            tool_call=self.tool_call.name,
            record_kind="result_snapshot",
            context_policy="include_reference",
            context_summary=result_doc.summary,
            reference_doctype="Agent Execution Result",
            reference_name=result_doc.name,
        )
        self._cleanup.append(("Agent Message", message.name))

        self.assertTrue(result_doc.payload_file)
        self.assertIsInstance(message.content, str)
        self.assertIn("result_ref", message.content)
        self.assertNotIn("row-99999", message.content)
        self.assertLess(len(message.content), 1000)
        self.assertEqual(message.reference_doctype, "Agent Execution Result")
        self.assertEqual(message.reference_name, result_doc.name)

    def test_include_reference_does_not_return_full_payload(self):
        """get_conversation_history returns a compact handle, not the raw payload."""
        result_doc, _ = self._persist_large_result(row_count=100_000)

        self.cm.add_message(
            conversation=self.conversation,
            role="tool",
            content=json.dumps({"result_ref": f"result://{result_doc.name}"}),
            provider=self.provider,
            model=self.model,
            agent=self.agent.name,
            run_name=self.run.name,
            kind="Tool Result",
            tool_call=self.tool_call.name,
            record_kind="result_snapshot",
            context_policy="include_reference",
            context_summary=result_doc.summary,
            reference_doctype="Agent Execution Result",
            reference_name=result_doc.name,
        )

        history = self.cm.get_conversation_history(self.conversation.name, limit=10)
        tool_messages = [m for m in history if m.get("role") == "tool"]
        self.assertTrue(tool_messages)

        for msg in tool_messages:
            content = msg.get("content") or ""
            self.assertNotIn("row-99999", content)
            self.assertIn("Agent Execution Result", content)
            self.assertLess(len(content), 2000)

    def test_envelope_is_below_token_limit(self):
        """The envelope itself stays within a small token budget."""
        result_doc, _ = self._persist_large_result(row_count=100_000)
        envelope_text = json.dumps({
            "result_ref": f"result://{result_doc.name}",
            "summary": result_doc.summary,
        })
        # Heuristic: envelope text must be far below the hard token limit.
        self.assertLess(len(envelope_text) / 4, policy.HARD_MAX_TOKENS)

    def test_result_read_can_retrieve_bounded_pages(self):
        """The model can read bounded pages of a large result."""
        result_doc, rows = self._persist_large_result(row_count=100_000)

        data = result_read(result_doc.name, view="page", page=1, page_size=50)
        # Client requested 50 rows; server hard cap is 100, so the request is honored.
        self.assertEqual(len(data["rows"]), 50)
        self.assertLessEqual(len(data["rows"]), policy.HARD_MAX_PAGE_SIZE)
        self.assertEqual(data["total"], 100_000)
        self.assertEqual(data["rows"][0]["id"], 0)

        data2 = result_read(result_doc.name, view="row", selector="99999")
        self.assertEqual(data2["rows"][0]["id"], 99999)

    def test_expired_result_is_handled_explicitly(self):
        """Expired results return an explicit error envelope."""
        result_doc, _ = self._persist_large_result(row_count=10)
        result_doc.expires_on = "2020-01-01 00:00:00"
        result_doc.status = "Expired"
        result_doc.save(ignore_permissions=True)

        data = result_read(result_doc.name, view="summary")
        self.assertEqual(data["status"], "error")
        self.assertIn("expired", data["error"].lower())


