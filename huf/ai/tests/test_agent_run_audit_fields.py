# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Integration tests for ST-R5.1: Agent Run audit-completeness fields.

Covers:
  - ``audit_incomplete`` gets populated on the Agent Run when tool-call
    persistence (``process_tool_call``) raises inside the try/except
    boundary.
  - ``AgentManager._setup_tools`` records a failure reason on
    ``self.tool_setup_warnings`` when a tool-setup step raises one of the
    caught exception types, so callers can flush it onto the run doc.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_run_audit_fields
"""
import unittest
from unittest.mock import patch

import frappe

from huf.ai.agent_integration import AgentManager, process_tool_call


class TestAuditIncompleteOnToolCallFailure(unittest.TestCase):
    """``Agent Run.audit_incomplete`` must record tool-call persistence failures."""

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

    def _make_agent(self):
        agent = frappe.get_doc(
            {
                "doctype": "Agent",
                "agent_name": f"test-audit-agent-{frappe.generate_hash(length=8)}",
                "provider": self.provider,
                "model": self.model,
                "instructions": "You are a test agent used only for audit_incomplete regression tests.",
            }
        )
        agent.insert(ignore_permissions=True)
        frappe.db.commit()
        self._agents.append(agent.name)
        return agent

    def _make_conversation(self, agent):
        conversation = frappe.get_doc(
            {
                "doctype": "Agent Conversation",
                "agent": agent.name,
                "title": f"audit-test-{frappe.generate_hash(length=6)}",
                "session_id": f"test-session-{frappe.generate_hash(length=10)}",
                "is_active": 1,
            }
        )
        conversation.insert(ignore_permissions=True)
        frappe.db.commit()
        self._conversations.append(conversation.name)
        return conversation

    def _make_agent_run(self, agent, conversation):
        agent_run = frappe.get_doc(
            {
                "doctype": "Agent Run",
                "agent": agent.name,
                "conversation": conversation.name,
                "status": "Started",
            }
        )
        agent_run.insert(ignore_permissions=True)
        frappe.db.commit()
        self._runs.append(agent_run.name)
        return agent_run

    def test_audit_incomplete_set_when_persistence_raises(self):
        agent = self._make_agent()
        conversation = self._make_conversation(agent)
        agent_run = self._make_agent_run(agent, conversation)

        with patch(
            "huf.ai.agent_integration.frappe.get_doc",
            side_effect=RuntimeError("boom: simulated persistence failure"),
        ):
            result = process_tool_call(
                agent_run.name,
                conversation.name,
                name="get_weather",
                args={"city": "Chennai"},
                tool_call_id=f"call_{frappe.generate_hash(length=10)}",
            )

        # The existing contract: on failure, process_tool_call swallows the
        # exception and returns None rather than propagating it.
        self.assertIsNone(result)

        audit_incomplete = frappe.db.get_value("Agent Run", agent_run.name, "audit_incomplete")
        self.assertIsNotNone(audit_incomplete)
        self.assertIn("boom: simulated persistence failure", audit_incomplete)


class TestToolSetupWarnings(unittest.TestCase):
    """``AgentManager.tool_setup_warnings`` must record tool-setup failures."""

    def _bare_manager(self):
        # Bypass __init__ (which needs a real Agent/AI Provider doc chain);
        # exercise _setup_tools() directly against the attributes it touches.
        manager = object.__new__(AgentManager)
        manager.tools = []
        manager.tool_sources = {}
        manager.tool_setup_warnings = []
        manager.agent_doc = frappe._dict(
            {
                "name": "test-agent",
                "agent_name": "test-agent",
                "agent_mcp_server": [],
            }
        )
        manager.effective_model = "gpt-4o-mini"
        manager.conversation_id = None
        return manager

    def test_agent_tools_failure_recorded(self):
        manager = self._bare_manager()
        with patch(
            "huf.ai.sdk_tools.create_agent_tools",
            side_effect=ValueError("agent tools blew up"),
        ):
            manager._setup_tools()

        self.assertTrue(
            any("agent tools blew up" in w for w in manager.tool_setup_warnings),
            manager.tool_setup_warnings,
        )


if __name__ == "__main__":
    unittest.main()
