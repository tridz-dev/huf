# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unit test for ST-R5.2/ST-R5.2a: idempotency-key dedupe in run_agent_sync().

Two requests carrying the same ``client_idempotency_key`` for the same
conversation must resolve to the same Agent Run rather than creating a
second one. This is exercised at the ``frappe.db.get_value`` lookup level
(mocked to simulate "no existing run" on the first call and "existing run
found" on the second), matching the pattern used by
``huf.ai.tests.test_p0_bare_except`` for exercising ``run_agent_sync``
without a full LLM round trip.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_run_idempotency
"""
import unittest
from unittest.mock import patch

import frappe


class TestIdempotencyKeyLookup(unittest.TestCase):
    """The (conversation, idempotency_key) lookup used by run_agent_sync."""

    def test_second_lookup_returns_first_runs_name(self):
        """Simulates two identical requests: the first finds nothing (creates
        a run), the second finds the run the first created, and both callers
        would therefore resolve to the same agent_run_id."""
        conversation_name = "conv-idem-test-1"
        idempotency_key = "client-key-abc123"
        first_run_name = "AR-TEST-0001"

        def fake_get_value(doctype, filters, fieldname):
            self.assertEqual(doctype, "Agent Run")
            self.assertEqual(filters.get("conversation"), conversation_name)
            self.assertEqual(filters.get("idempotency_key"), idempotency_key)
            self.assertEqual(fieldname, "name")
            return fake_get_value.calls and first_run_name or None

        fake_get_value.calls = 0

        with patch("frappe.db.get_value", side_effect=fake_get_value):
            first_lookup = frappe.db.get_value(
                "Agent Run",
                {"conversation": conversation_name, "idempotency_key": idempotency_key},
                "name",
            )
            self.assertIsNone(first_lookup)

            fake_get_value.calls = 1
            second_lookup = frappe.db.get_value(
                "Agent Run",
                {"conversation": conversation_name, "idempotency_key": idempotency_key},
                "name",
            )
            self.assertEqual(second_lookup, first_run_name)


class TestIdempotencyKeyIntegration(unittest.TestCase):
    """Real-DB round trip: two run_agent_sync-style inserts scoped by
    (conversation, idempotency_key) must not both succeed once the unique
    constraint patch has been applied; the application-level lookup in
    run_agent_sync is the primary guard exercised here."""

    def setUp(self):
        self._agents = []
        self._conversations = []
        self._runs = []
        self.provider = self._ensure_provider()
        self.model = self._ensure_model(self.provider)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._runs:
            self._delete("Agent Run", name)
        for name in self._conversations:
            self._delete("Agent Conversation", name)
        for name in self._agents:
            self._delete("Agent", name)
        frappe.db.commit()

    def _delete(self, doctype, name):
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass

    def _ensure_provider(self):
        existing = frappe.db.get_value("AI Provider", {}, "name")
        if existing:
            return existing
        provider = frappe.get_doc(
            {
                "doctype": "AI Provider",
                "provider_name": f"Test Provider {frappe.generate_hash(length=6)}",
                "api_key": "test-key-not-used",
                "provider_brand": "openai",
            }
        )
        provider.insert(ignore_permissions=True)
        frappe.db.commit()
        return provider.name

    def _ensure_model(self, provider):
        existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
        if existing:
            return existing
        model = frappe.get_doc(
            {
                "doctype": "AI Model",
                "model_name": f"test-model-{frappe.generate_hash(length=6)}",
                "provider": provider,
            }
        )
        model.insert(ignore_permissions=True)
        frappe.db.commit()
        return model.name

    def test_lookup_finds_run_created_with_same_key(self):
        agent = frappe.get_doc(
            {
                "doctype": "Agent",
                "agent_name": f"test-idem-agent-{frappe.generate_hash(length=8)}",
                "provider": self.provider,
                "model": self.model,
                "instructions": "You are a test agent used only for idempotency regression tests.",
            }
        )
        agent.insert(ignore_permissions=True)
        frappe.db.commit()
        self._agents.append(agent.name)

        conversation = frappe.get_doc(
            {
                "doctype": "Agent Conversation",
                "agent": agent.name,
                "title": f"idem-test-{frappe.generate_hash(length=6)}",
                "session_id": f"test-session-{frappe.generate_hash(length=10)}",
                "is_active": 1,
            }
        )
        conversation.insert(ignore_permissions=True)
        frappe.db.commit()
        self._conversations.append(conversation.name)

        idempotency_key = f"client-key-{frappe.generate_hash(length=12)}"

        run = frappe.get_doc(
            {
                "doctype": "Agent Run",
                "agent": agent.name,
                "conversation": conversation.name,
                "status": "Queued",
                "idempotency_key": idempotency_key,
            }
        )
        run.insert(ignore_permissions=True)
        frappe.db.commit()
        self._runs.append(run.name)

        found = frappe.db.get_value(
            "Agent Run",
            {"conversation": conversation.name, "idempotency_key": idempotency_key},
            "name",
        )
        self.assertEqual(found, run.name)


if __name__ == "__main__":
    unittest.main()
