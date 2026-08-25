"""
Regression test for the ``process_tool_call`` tool_args double-encoding bug.

Per the OpenAI/litellm tool-call convention, ``raw_call.arguments`` (the
``args`` parameter passed into ``process_tool_call``) arrives already
JSON-encoded as a string, e.g. '{"city": "Bengaluru"}'. Prior to the fix,
both call sites in ``process_tool_call`` called ``json.dumps(args)`` on this
value unconditionally, wrapping it in a second layer of JSON encoding and
persisting a value like '"{\\"city\\": \\"Bengaluru\\"}"' into
``Agent Tool Call.tool_args`` -- a JSON string containing an escaped JSON
string, rather than a clean JSON object. ``_normalize_tool_args_json``
special-cases the "already valid JSON string" case so the value round-trips
through exactly one ``json.loads`` to a dict.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_process_tool_call_args_encoding
"""
import json
import unittest

import frappe

from huf.ai.agent_integration import process_tool_call


class TestProcessToolCallArgsEncoding(unittest.TestCase):
    """``Agent Tool Call.tool_args`` must be single-JSON-encoded, not double."""

    def setUp(self):
        self._agents = []
        self._conversations = []
        self._runs = []
        self._calls = []
        self.provider = self._ensure_provider()
        self.model = self._ensure_model(self.provider)

    def tearDown(self):
        frappe.set_user("Administrator")
        for name in self._calls:
            self._delete("Agent Tool Call", name)
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
                "agent_name": f"test-tool-args-agent-{frappe.generate_hash(length=8)}",
                "provider": self.provider,
                "model": self.model,
                "instructions": "You are a test agent used only for tool_args encoding regression tests.",
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
                "title": f"tool-args-test-{frappe.generate_hash(length=6)}",
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
                "status": "Running",
            }
        )
        agent_run.insert(ignore_permissions=True)
        frappe.db.commit()
        self._runs.append(agent_run.name)
        return agent_run

    def test_tool_args_is_single_json_encoded_not_double(self):
        """``args`` arriving as an already-JSON-encoded string (the real
        litellm/OpenAI tool-call shape) must be stored as-is, not re-wrapped
        in a second layer of json.dumps."""
        agent = self._make_agent()
        conversation = self._make_conversation(agent)
        agent_run = self._make_agent_run(agent, conversation)

        raw_args_str = json.dumps({"city": "Bengaluru"})
        call_id = f"call_{frappe.generate_hash(length=10)}"

        doc_name = process_tool_call(
            agent_run.name,
            conversation.name,
            name="get_weather",
            args=raw_args_str,
            tool_call_id=call_id,
        )
        self._calls.append(doc_name)

        call_doc = frappe.get_doc("Agent Tool Call", doc_name)
        persisted = call_doc.tool_args

        # Exactly one json.loads() must yield the real dict directly.
        parsed = json.loads(persisted)
        self.assertIsInstance(
            parsed,
            dict,
            f"tool_args did not decode to a dict in one json.loads() pass "
            f"(double-encoded?); got {type(parsed).__name__} from {persisted!r}",
        )
        self.assertEqual(parsed, {"city": "Bengaluru"})

    def test_tool_args_dict_input_still_gets_single_encoded(self):
        """A caller that legitimately passes a dict/list (not a pre-encoded
        string) must still get exactly one layer of JSON encoding."""
        agent = self._make_agent()
        conversation = self._make_conversation(agent)
        agent_run = self._make_agent_run(agent, conversation)

        call_id = f"call_{frappe.generate_hash(length=10)}"

        doc_name = process_tool_call(
            agent_run.name,
            conversation.name,
            name="get_weather",
            args={"city": "Chennai"},
            tool_call_id=call_id,
        )
        self._calls.append(doc_name)

        call_doc = frappe.get_doc("Agent Tool Call", doc_name)
        parsed = json.loads(call_doc.tool_args)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed, {"city": "Chennai"})


if __name__ == "__main__":
    unittest.main()
