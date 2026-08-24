# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) unit tests for `huf/ai/tests/factories.py`.

These do NOT exercise real Frappe validation (no bench is available in this
environment — see that module's docstring). Instead they mock
`frappe.get_doc`/`.insert()` and assert on the call arguments passed to
`frappe.get_doc`, proving each factory:
  - targets the correct doctype name, and
  - supplies a complete required-field set (per the real doctype JSON,
    verified separately — see factories.py's per-function docstrings for
    citations).

This catches the most common factory bug class ("forgot a required field")
without needing a real DB, matching the pattern this repo already uses in
`huf/ai/tests/test_test_provider.py` (mock the external dependency, assert
on call shape).

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_factories.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

# huf/ai/tests/conftest.py stubs sys.modules['frappe'] with a MagicMock when
# frappe isn't importable (no bench available). Do the same defensively here
# so this file can also be run outside that conftest's collection scope -
# same pattern as test_test_provider.py.
if "frappe" not in sys.modules:
    frappe_mock = MagicMock()
    frappe_mock._ = lambda x: x
    sys.modules["frappe"] = frappe_mock

from huf.ai.tests import factories  # noqa: E402


def _mock_inserted_doc(get_doc_mock):
    """Configure `frappe.get_doc` to return a MagicMock whose `.insert()` is
    a no-op and whose `.name` is a fixed sentinel string - enough for
    factories that chain `.name` off a just-created linked doc (e.g.
    `make_ai_provider_and_model`, `make_agent`'s auto-provider path).
    """
    doc = MagicMock()
    doc.name = "TEST-DOC-NAME"
    get_doc_mock.return_value = doc
    return doc


class FactoriesTestCase(unittest.TestCase):
    """Base: fresh `frappe.get_doc`/`frappe.new_doc`/`frappe.generate_hash`
    mocks per test, isolated from other test classes' call history."""

    def setUp(self):
        patcher_get_doc = patch.object(factories.frappe, "get_doc")
        patcher_hash = patch.object(
            factories.frappe, "generate_hash", return_value="abc123"
        )
        self.get_doc = patcher_get_doc.start()
        patcher_hash.start()
        self.addCleanup(patcher_get_doc.stop)
        self.addCleanup(patcher_hash.stop)
        _mock_inserted_doc(self.get_doc)

    def _fields_from_call(self, call_index=0):
        """Return the dict passed as frappe.get_doc's positional arg."""
        args, _kwargs = self.get_doc.call_args_list[call_index]
        return args[0]


class TestMakeUser(FactoriesTestCase):
    def test_calls_get_doc_with_user_doctype_and_required_fields(self):
        factories.make_user()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "User")
        self.assertIn("email", fields)
        self.assertTrue(fields["email"])
        self.assertIn("first_name", fields)
        # send_welcome_email must be explicitly suppressed - a missing/1
        # value here would send a real email in a live bench.
        self.assertEqual(fields["send_welcome_email"], 0)

    def test_default_role_is_appended(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_user()

        doc.append.assert_any_call("roles", {"role": "Huf User"})

    def test_custom_roles_are_appended(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_user(roles=("System Manager", "Huf User"))

        doc.append.assert_any_call("roles", {"role": "System Manager"})
        doc.append.assert_any_call("roles", {"role": "Huf User"})

    def test_insert_called_with_ignore_permissions(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_user()
        doc.insert.assert_called_once_with(ignore_permissions=True)


class TestMakeRole(FactoriesTestCase):
    def test_calls_get_doc_with_role_doctype_and_role_name(self):
        factories.make_role()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Role")
        self.assertIn("role_name", fields)
        self.assertTrue(fields["role_name"])


class TestMakeAIProviderAndModel(FactoriesTestCase):
    def test_provider_call_has_required_fields(self):
        factories.make_ai_provider()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "AI Provider")
        self.assertIn("provider_name", fields)
        self.assertTrue(fields["provider_name"])
        self.assertIn("provider_brand", fields)
        self.assertTrue(fields["provider_brand"])

    def test_model_call_has_required_fields_and_provider_link(self):
        factories.make_ai_model(provider="Some Provider")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "AI Model")
        self.assertEqual(fields["provider"], "Some Provider")
        self.assertIn("model_name", fields)
        self.assertTrue(fields["model_name"])

    def test_model_creates_provider_when_not_supplied(self):
        # get_doc is called twice: once for the auto-created AI Provider,
        # once for the AI Model itself.
        factories.make_ai_model()

        self.assertEqual(self.get_doc.call_count, 2)
        provider_fields = self._fields_from_call(0)
        model_fields = self._fields_from_call(1)
        self.assertEqual(provider_fields["doctype"], "AI Provider")
        self.assertEqual(model_fields["doctype"], "AI Model")
        # The model's provider link must be the auto-created provider's name.
        self.assertEqual(model_fields["provider"], "TEST-DOC-NAME")

    def test_make_ai_provider_and_model_returns_name_pair(self):
        provider_name, model_name = factories.make_ai_provider_and_model()
        self.assertEqual(provider_name, "TEST-DOC-NAME")
        self.assertEqual(model_name, "TEST-DOC-NAME")
        self.assertEqual(self.get_doc.call_count, 2)


class TestMakeAgent(FactoriesTestCase):
    def test_minimal_agent_has_required_and_load_bearing_fields(self):
        factories.make_agent(provider="Prov", model="Mod")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent")
        self.assertIn("agent_name", fields)
        self.assertTrue(fields["agent_name"])
        self.assertEqual(fields["provider"], "Prov")
        self.assertEqual(fields["model"], "Mod")
        self.assertIn("instructions", fields)
        self.assertTrue(fields["instructions"])

    def test_agent_auto_creates_provider_and_model_when_missing(self):
        # Auto-provider, auto-model, then the Agent itself = 3 get_doc calls.
        factories.make_agent()

        self.assertEqual(self.get_doc.call_count, 3)
        agent_fields = self._fields_from_call(2)
        self.assertEqual(agent_fields["doctype"], "Agent")
        self.assertEqual(agent_fields["provider"], "TEST-DOC-NAME")
        self.assertEqual(agent_fields["model"], "TEST-DOC-NAME")

    def test_overrides_win_over_defaults(self):
        factories.make_agent(
            provider="Prov", model="Mod", instructions="custom instructions"
        )
        fields = self._fields_from_call()
        self.assertEqual(fields["instructions"], "custom instructions")

    def test_insert_called_with_ignore_permissions(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_agent(provider="Prov", model="Mod")
        doc.insert.assert_called_once_with(ignore_permissions=True)


class TestMakeAgentWithToolsAndPrompt(FactoriesTestCase):
    def test_appends_tool_mcp_and_sets_template_prompt_mode(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_agent_with_tools_and_prompt(
            provider="Prov",
            model="Mod",
            tool_functions=["ToolFn-1"],
            agent_prompt="Prompt-1",
            mcp_servers=["MCP-1"],
        )

        doc.append.assert_any_call("agent_tool", {"tool": "ToolFn-1"})
        doc.append.assert_any_call("agent_mcp_server", {"mcp_server": "MCP-1"})

        agent_fields = self._fields_from_call()
        self.assertEqual(agent_fields["doctype"], "Agent")
        self.assertEqual(agent_fields["prompt_mode"], "Template")
        self.assertEqual(agent_fields["agent_prompt"], "Prompt-1")


class TestMakeAgentConversation(FactoriesTestCase):
    def test_calls_get_doc_with_required_session_id_and_agent(self):
        factories.make_agent_conversation(agent="Agent-1")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent Conversation")
        self.assertEqual(fields["agent"], "Agent-1")
        self.assertIn("session_id", fields)
        self.assertTrue(fields["session_id"])

    def test_creates_agent_when_missing(self):
        # Auto-provider, auto-model, auto-agent, then the conversation itself.
        factories.make_agent_conversation()
        self.assertEqual(self.get_doc.call_count, 4)
        convo_fields = self._fields_from_call(3)
        self.assertEqual(convo_fields["doctype"], "Agent Conversation")
        self.assertEqual(convo_fields["agent"], "TEST-DOC-NAME")


class TestMakeAgentRun(FactoriesTestCase):
    def test_calls_get_doc_with_agent_run_doctype_and_links(self):
        factories.make_agent_run(
            conversation="Conv-1", agent="Agent-1", provider="Prov-1", model="Mod-1"
        )
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent Run")
        self.assertEqual(fields["agent"], "Agent-1")
        self.assertEqual(fields["conversation"], "Conv-1")
        self.assertEqual(fields["provider"], "Prov-1")
        self.assertEqual(fields["model"], "Mod-1")

    def test_does_not_set_reference_doctype_by_default(self):
        """Regression guard: leaving reference_doctype/reference_name unset
        avoids the controller's conditional validate() throw path
        (agent_run.py::validate_reference) - a run with a bad/missing
        reference_doctype would fail to insert on a real bench."""
        factories.make_agent_run(
            conversation="Conv-1", agent="Agent-1", provider="Prov-1", model="Mod-1"
        )
        fields = self._fields_from_call()
        self.assertNotIn("reference_doctype", fields)
        self.assertNotIn("reference_name", fields)

    def test_creates_agent_and_conversation_when_missing(self):
        factories.make_agent_run()
        # auto-provider, auto-model, auto-agent, auto-conversation, then run.
        self.assertEqual(self.get_doc.call_count, 5)
        run_fields = self._fields_from_call(4)
        self.assertEqual(run_fields["doctype"], "Agent Run")
        self.assertEqual(run_fields["agent"], "TEST-DOC-NAME")
        self.assertEqual(run_fields["conversation"], "TEST-DOC-NAME")

    def test_insert_called_with_ignore_permissions(self):
        doc = _mock_inserted_doc(self.get_doc)
        factories.make_agent_run(
            conversation="Conv-1", agent="Agent-1", provider="Prov-1", model="Mod-1"
        )
        doc.insert.assert_called_once_with(ignore_permissions=True)


class TestMakeAgentToolFunction(FactoriesTestCase):
    def test_calls_get_doc_with_required_fields(self):
        factories.make_agent_tool_function(tool_type="TT-1")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent Tool Function")
        self.assertIn("tool_name", fields)
        self.assertTrue(fields["tool_name"])
        self.assertIn("description", fields)
        self.assertTrue(fields["description"])
        self.assertEqual(fields["tool_type"], "TT-1")


class TestMakeMcpServer(FactoriesTestCase):
    def test_calls_get_doc_with_required_fields(self):
        factories.make_mcp_server()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "MCP Server")
        self.assertIn("server_name", fields)
        self.assertTrue(fields["server_name"])
        self.assertIn("transport_type", fields)
        self.assertTrue(fields["transport_type"])
        self.assertIn("server_url", fields)
        self.assertTrue(fields["server_url"])


class TestMakeAgentPrompt(FactoriesTestCase):
    def test_calls_get_doc_with_agent_prompt_doctype_not_prompt_template(self):
        """Regression guard: the prompt-template doctype is literally named
        "Agent Prompt", not "Prompt Template" or "Prompt" - see
        huf/ai/prompt_resolver.py."""
        factories.make_agent_prompt()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent Prompt")
        self.assertIn("title", fields)
        self.assertTrue(fields["title"])
        self.assertIn("prompt_body", fields)
        self.assertTrue(fields["prompt_body"])


class TestMakeAutomationAndTriggers(FactoriesTestCase):
    def test_make_automation_required_fields(self):
        factories.make_automation(agent="Agent-1")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Automation")
        self.assertIn("automation_name", fields)
        self.assertTrue(fields["automation_name"])
        self.assertEqual(fields["agent"], "Agent-1")
        self.assertIn("instruction", fields)
        self.assertTrue(fields["instruction"])

    def test_make_automation_trigger_required_fields(self):
        factories.make_automation_trigger(automation="Auto-1")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Automation Trigger")
        self.assertIn("trigger_name", fields)
        self.assertTrue(fields["trigger_name"])
        self.assertEqual(fields["automation"], "Auto-1")
        self.assertIn("trigger_type", fields)

    def test_make_agent_trigger_is_the_legacy_doctype(self):
        """Both Automation Trigger (new) and Agent Trigger (legacy) must be
        supported per docs/testing/CURRENT_STATE.md section 7's dual-runtime
        finding - this asserts the legacy factory targets the distinct
        "Agent Trigger" doctype, not "Automation Trigger"."""
        factories.make_agent_trigger(agent="Agent-1")
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Agent Trigger")
        self.assertIn("trigger_name", fields)
        self.assertTrue(fields["trigger_name"])
        self.assertEqual(fields["agent"], "Agent-1")


class TestMakeKnowledgeSource(FactoriesTestCase):
    def test_calls_get_doc_with_required_fields(self):
        factories.make_knowledge_source()
        fields = self._fields_from_call()

        self.assertEqual(fields["doctype"], "Knowledge Source")
        self.assertIn("source_name", fields)
        self.assertTrue(fields["source_name"])
        self.assertIn("knowledge_type", fields)
        self.assertTrue(fields["knowledge_type"])


if __name__ == "__main__":
    unittest.main()
