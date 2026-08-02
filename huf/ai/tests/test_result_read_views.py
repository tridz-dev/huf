# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for bounded result reads (huf.ai.results.views)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.results import policy
from huf.ai.results.store import persist_result
from huf.ai.results.views import result_index_for_conversation, result_read


class _ResultReadViewsTestCase(IntegrationTestCase):
    """Shared scaffolding for result-read view tests."""

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
            "instructions": "You are a test agent for result-read tests.",
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

    def _persist_table(self, row_count: int = 250):
        rows = [
            {"id": i, "status": "active" if i % 2 == 0 else "inactive", "value": i * 10}
            for i in range(row_count)
        ]
        result_doc, _ = persist_result(
            result_content=rows,
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
            source_tool="test_tool",
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))
        return result_doc


class TestResultReadViews(_ResultReadViewsTestCase):
    """Bounded view contract."""

    def test_summary_view_returns_envelope(self):
        result_doc = self._persist_table(row_count=10)
        data = result_read(result_doc.name, view="summary")

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["result_ref"], f"result://{result_doc.name}")
        self.assertIn("summary", data)
        self.assertIn("size", data)

    def test_schema_view_returns_columns(self):
        result_doc = self._persist_table(row_count=10)
        data = result_read(result_doc.name, view="schema")

        self.assertEqual(data["schema"]["columns"], ["id", "status", "value"])
        self.assertEqual(data["schema"]["row_count"], 10)

    def test_preview_view_returns_first_rows(self):
        result_doc = self._persist_table(row_count=10)
        data = result_read(result_doc.name, view="preview")

        self.assertEqual(len(data["preview"]["rows"]), min(10, policy.DEFAULT_PREVIEW_ROWS))

    def test_page_view_respects_server_side_page_size(self):
        result_doc = self._persist_table(row_count=250)
        data = result_read(result_doc.name, view="page", page=1, page_size=500)

        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], policy.HARD_MAX_PAGE_SIZE)
        self.assertEqual(len(data["rows"]), policy.HARD_MAX_PAGE_SIZE)
        self.assertEqual(data["total"], 250)

    def test_range_selector_works(self):
        result_doc = self._persist_table(row_count=50)
        data = result_read(result_doc.name, view="range", selector="rows[10:20]")

        self.assertEqual(data["start"], 10)
        self.assertEqual(data["end"], 20)
        self.assertEqual(len(data["rows"]), 10)
        self.assertEqual(data["rows"][0]["id"], 10)

    def test_filter_view_works(self):
        result_doc = self._persist_table(row_count=50)
        data = result_read(
            result_doc.name,
            view="filter",
            filter={"status": "active"},
            columns=["id", "status"],
        )

        self.assertTrue(data["matched"] > 0)
        for row in data["rows"]:
            self.assertEqual(row["status"], "active")
            self.assertNotIn("value", row)

    def test_row_view_selects_indices(self):
        result_doc = self._persist_table(row_count=50)
        data = result_read(result_doc.name, view="row", selector="5,10,15")

        self.assertEqual(data["indices"], [5, 10, 15])
        self.assertEqual(len(data["rows"]), 3)

    def test_path_view_works(self):
        result_doc, _ = persist_result(
            result_content={"orders": [{"items": ["a", "b"]}, {"items": ["c"]}]},
            run=self.run.name,
            tool_call=self.tool_call.name,
            conversation=self.conversation.name,
        )
        self._cleanup.append(("Agent Execution Result", result_doc.name))

        data = result_read(result_doc.name, view="path", selector="orders[0].items")
        self.assertEqual(data["value"], ["a", "b"])

    def test_unknown_view_returns_error(self):
        result_doc = self._persist_table(row_count=5)
        data = result_read(result_doc.name, view="invalid")
        self.assertEqual(data["status"], "error")

    def test_max_rows_cap_overrides_client_request(self):
        result_doc = self._persist_table(row_count=250)
        data = result_read(
            result_doc.name,
            view="filter",
            filter={"status": "active"},
            max_rows=500,
        )
        self.assertLessEqual(len(data["rows"]), policy.HARD_MAX_ROWS)


class TestResultReadPermissions(_ResultReadViewsTestCase):
    """Permission enforcement on result reads."""

    def test_unauthorized_read_rejected(self):
        result_doc = self._persist_table(row_count=10)

        # Create a second user who is not a conversation participant.
        other_user = f"test_other_{frappe.generate_hash(length=6)}@example.com"
        if not frappe.db.exists("User", other_user):
            user = frappe.get_doc({
                "doctype": "User",
                "email": other_user,
                "first_name": "Test",
                "enabled": 1,
            })
            user.insert(ignore_permissions=True)
            self._cleanup.append(("User", other_user))

        frappe.set_user(other_user)
        with self.assertRaises(frappe.PermissionError):
            result_read(result_doc.name, view="summary")


class TestResultIndex(_ResultReadViewsTestCase):
    """Conversation-level result index."""

    def test_index_lists_conversation_results(self):
        result_doc = self._persist_table(row_count=10)
        data = result_index_for_conversation(self.conversation.name)

        self.assertEqual(data["status"], "success")
        refs = [r["ref"] for r in data["results"]]
        self.assertIn(f"result://{result_doc.name}", refs)
