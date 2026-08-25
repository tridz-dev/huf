# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration tests for the Agent Run execution
lifecycle described in ``docs/testing/CURRENT_STATE.md`` section 3 ("Agent
runtime / execution lifecycle").

Every test submits a run through the real whitelisted entrypoint
``huf.ai.agent_integration.run_agent_sync`` (never calling internal
functions like ``_execute_agent_run`` directly), then asserts against real
DB rows (``Agent Run`` / ``Agent Message`` / ``Agent Tool Call``). Provider
behavior is made fully deterministic by routing the Agent through the HUF
Test Provider (``huf/ai/providers/test_provider.py``), not a real LLM.

Routing to the test provider
-----------------------------
``huf.ai.providers.litellm.run()`` special-cases ``provider.lower() ==
"test_provider"`` near the top of its body (before any real network/DB
work), delegating to ``huf.ai.providers.test_provider.run()``. The
``provider`` value that reaches that check is the ``AI Provider`` document's
own ``name`` (NOT ``provider_brand``) -- verified by reading:

  - ``huf/ai/agent_integration.py::_resolve_effective_model`` -- returns
    ``agent_doc.provider`` (a Link value, i.e. the AI Provider doc's
    ``name``) as ``effective_provider``.
  - ``huf/ai/agent_integration.py:1620`` -- ``await RunProvider.run(agent,
    enhanced_prompt, resolved_provider, resolved_model_name, context)``,
    where ``resolved_provider`` is exactly that ``effective_provider``.
  - ``huf/huf/doctype/ai_provider/ai_provider.json`` -- ``"autoname":
    "field:provider_name"`` / ``"naming_rule": "By fieldname"``, so the AI
    Provider document's ``name`` IS its ``provider_name`` field value
    verbatim.

So: creating an ``AI Provider`` with ``provider_name="Test_Provider"`` (via
``make_ai_provider(provider_name="Test_Provider")``) gives it ``name =
"Test_Provider"``, and ``"Test_Provider".lower() == "test_provider"``
matches the routing check exactly. ``provider_brand`` is irrelevant to this
routing decision (left at the factory's default, "openai") -- only the
document's ``name`` matters here.

Scenario selection
-------------------
A scenario is chosen by embedding ``__TEST_SCENARIO__:<NAME>`` anywhere in
the ``prompt`` argument to ``run_agent_sync`` -- ``test_provider.py``'s
``_extract_scenario`` scans the whole (wrapped) prompt, not just a prefix.

Queue-first vs. direct execution
----------------------------------
``run_agent_sync``'s default path is queue-first: it inserts the ``Agent
Run`` as ``Queued`` and returns immediately without persisting a user
message or executing anything inline
(``huf/ai/agent_integration.py::run_agent_sync``, the
``is_queued = not agent_doc.run_immediately and not _is_truthy(now)`` branch).
A test process has no running ``bench worker`` draining the queue, so a
queued run would sit at status "Queued" forever and no assertions about a
terminal status would ever be reachable.

UNVERIFIED - coordinator must confirm on real bench: passing ``now=1`` to
``run_agent_sync`` sets ``is_queued = False`` (confirmed by reading the
source: ``not _is_truthy(now)`` becomes ``not True == False`` when
``now=1``, and ``_is_truthy`` treats ``1`` as truthy), which takes the
direct-execution branch: it acquires the per-conversation Redis lock
in-process, persists the user message, and calls ``_execute_agent_run(...)``
synchronously in the same call stack as ``run_agent_sync`` -- meaning the
whitelisted call returns only after the run has already reached its
terminal status. This is read from source, not verified by actually running
it (no bench available in this environment); the coordinator must confirm
on the real bench that ``now=1`` is sufficient (as opposed to e.g. requiring
``agent.run_immediately=1`` as well, or the Redis lock/heartbeat machinery
behaving unexpectedly in a test process).

Every fixture created by this file is prefixed "_Test P0RT " (Runtime) so it
cannot collide with fixtures created by another concurrent test file sharing
the same site/bench.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_agent_runtime_p0
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import run_agent_sync
from huf.ai.tests.factories import (
    make_agent,
    make_ai_model,
    make_ai_provider,
)

PREFIX = "_Test P0RT"


class TestAgentRuntimeP0(IntegrationTestCase):
    def setUp(self):
        self._names = {
            "Agent": [],
            "AI Model": [],
            "AI Provider": [],
            "Agent Conversation": [],
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        # Delete in dependency order: Agent Run/Message/Tool Call cascade is
        # not modeled here (they reference Agent Conversation/Agent, not the
        # other way round) -- delete conversations (which cascades their
        # runs/messages via Frappe's own on_trash, if any) then Agent, then
        # AI Model/Provider last.
        for doctype in ("Agent Conversation", "Agent", "AI Model", "AI Provider"):
            for name in self._names.get(doctype, []):
                self._delete(doctype, name)
        frappe.db.commit()

    def _delete(self, doctype, name):
        try:
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
        except Exception:
            pass

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)
        return name

    def _make_test_provider_agent(self, **agent_overrides):
        """Create an Agent wired to the HUF Test Provider.

        The AI Provider document's ``name`` (== ``provider_name``, per
        ``autoname: field:provider_name``) must lowercase to
        "test_provider" for ``litellm.run()``'s routing check to fire --
        see this module's docstring for the full citation chain.
        """
        # MUST be exactly "Test_Provider" (case-insensitively) -- litellm.py's
        # routing check is `provider.lower() == "test_provider"`, an EXACT
        # match, not a prefix/substring check. A hash-suffixed unique name
        # (e.g. "Test_Provider_c0121c") never matches, silently falls
        # through to a REAL litellm completion attempt against a
        # non-existent provider, and fails closed -- found by running this
        # suite against a real bench (litellm's own "unrecognized provider"
        # error was logged to stderr, not raised where these tests looked).
        # Idempotent get-or-create + reuse across test methods, since the
        # docname is fixed and AI Provider enforces a unique provider_name.
        if frappe.db.exists("AI Provider", "Test_Provider"):
            provider = frappe.get_doc("AI Provider", "Test_Provider")
        else:
            provider = make_ai_provider(provider_name="Test_Provider")
            self._track("AI Provider", provider.name)
        model = make_ai_model(provider=provider.name, model_name=f"test-model-{frappe.generate_hash(length=6)}")
        self._track("AI Model", model.name)

        agent_overrides.setdefault(
            "agent_name", f"{PREFIX} Agent {frappe.generate_hash(length=8)}"
        )
        agent = make_agent(provider=provider.name, model=model.name, **agent_overrides)
        self._track("Agent", agent.name)
        return agent

    def _submit(self, agent, scenario, **kwargs):
        """Submit a run through the real whitelisted entrypoint, forced to
        execute synchronously in-process (no queue worker exists in a test
        process -- see module docstring's "Queue-first vs. direct execution"
        section)."""
        prompt = f"__TEST_SCENARIO__:{scenario}"
        kwargs.setdefault("now", 1)
        return run_agent_sync(
            agent_name=agent.name,
            prompt=prompt,
            **kwargs,
        )

    def _latest_conversation_for_agent(self, agent_name):
        rows = frappe.get_all(
            "Agent Conversation",
            filters={"agent": agent_name},
            fields=["name"],
            order_by="creation desc",
            limit=1,
        )
        return rows[0].name if rows else None

    # -- AGENT-RUN-001 ----------------------------------------------------

    def test_agent_run_001_text_scenario_creates_success_run_and_assistant_message(self):
        """TEST_TEXT: a real Agent Run reaches terminal status "Success"
        (per ``agent_run.json``'s status Select options:
        ``"\\nStarted\\nQueued\\nSuccess\\nFailed"`` -- there is no
        "Completed"/"Done" option, "Success" is the actual terminal string),
        and a corresponding assistant ``Agent Message`` is persisted with
        the deterministic TEST_TEXT content.

        Role convention verified against ``agent_message.json``: the
        ``role`` Select options are ``"user\\ntool\\nagent\\nsystem"`` --
        there is no "assistant" option; the assistant's own message is
        persisted with ``role="agent"`` (confirmed at the real call site,
        ``agent_integration.py``: ``conv_manager.add_message(conversation,
        "agent", final_output, ...)`` in the success path).
        """
        agent = self._make_test_provider_agent()

        result = self._submit(agent, "TEST_TEXT")

        self.assertTrue(result.get("success"))
        run_id = result["agent_run_id"]
        self._track("Agent Conversation", result["conversation_id"])

        run = frappe.get_doc("Agent Run", run_id)
        self.assertEqual(run.status, "Success")
        self.assertEqual(
            run.response,
            "This is a deterministic TEST_TEXT response from the HUF test provider.",
        )

        assistant_messages = frappe.get_all(
            "Agent Message",
            filters={"agent_run": run_id, "role": "agent", "kind": "Message"},
            fields=["name", "content"],
        )
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(
            assistant_messages[0].content,
            "This is a deterministic TEST_TEXT response from the HUF test provider.",
        )

    # -- AGENT-RUN-002 ----------------------------------------------------

    def test_agent_run_002_tool_single_scenario_persists_tool_call_and_message(self):
        """TEST_TOOL_SINGLE: the provider returns an already-executed
        tool_call_item/tool_call_output_item pair (per
        ``test_provider.py``'s "Tool-call scenario contract" -- HUF's own
        loop in ``litellm.py::run()`` executes tools itself; there is no
        outer-loop tool invocation to fake). ``agent_integration.py``'s
        replay code (~line 1628-1780, ``process_tool_call``/``log_tool_call``)
        must persist a real ``Agent Tool Call`` row plus an ``Agent Message``
        (kind="Tool Call") from that replay, with the deterministic tool
        name/args/result the test provider fabricates
        (``_TOOL_NAME="get_weather"``, ``_TOOL_ARGS='{"city":
        "Bengaluru"}'``, ``_TOOL_RESULT='{"city": "Bengaluru", "condition":
        "Sunny", "temp_c": 29}'``).
        """
        agent = self._make_test_provider_agent()

        result = self._submit(agent, "TEST_TOOL_SINGLE")

        self.assertTrue(result.get("success"))
        run_id = result["agent_run_id"]
        self._track("Agent Conversation", result["conversation_id"])

        run = frappe.get_doc("Agent Run", run_id)
        self.assertEqual(run.status, "Success")
        self.assertEqual(
            run.response,
            "Based on the tool result, it is currently Sunny at 29C in Bengaluru.",
        )

        tool_calls = frappe.get_all(
            "Agent Tool Call",
            filters={"agent_run": run_id},
            fields=["name", "tool", "tool_args", "tool_result", "status", "call_id"],
        )
        self.assertEqual(len(tool_calls), 1)
        tc = tool_calls[0]
        self.assertEqual(tc.tool, "get_weather")
        self.assertEqual(tc.call_id, "test-tool-call-1")
        self.assertEqual(tc.status, "Completed")
        self.assertEqual(json.loads(tc.tool_args), {"city": "Bengaluru"})
        # ``process_tool_call`` stores dict/list JSON results verbatim (not
        # wrapped in {"output": ...} -- that wrapping only applies to
        # non-dict/list results, see agent_integration.py::process_tool_call).
        stored_result = tc.tool_result
        if isinstance(stored_result, str):
            stored_result = json.loads(stored_result)
        self.assertEqual(
            stored_result,
            {"city": "Bengaluru", "condition": "Sunny", "temp_c": 29},
        )

        tool_call_messages = frappe.get_all(
            "Agent Message",
            filters={"agent_run": run_id, "kind": "Tool Call"},
            fields=["name", "tool_call", "role"],
        )
        self.assertEqual(len(tool_call_messages), 1)
        self.assertEqual(tool_call_messages[0].role, "agent")
        self.assertEqual(tool_call_messages[0].tool_call, tc.name)

    # -- AGENT-RUN-003 ------------------------------------------------------

    def test_agent_run_003_provider_timeout_ends_run_failed_without_crashing(self):
        """TEST_PROVIDER_TIMEOUT: the test provider raises
        ``ProviderUnavailableError`` (the exact class/shape a real litellm
        timeout produces -- see ``test_provider.py``'s docstring). The real
        ``except ProviderUnavailableError as e:`` boundary handler in
        ``_execute_agent_run`` (``agent_integration.py`` ~line 2058) must
        catch it, set the ``Agent Run`` to status "Failed" with a persisted
        ``error_message``, and return a structured
        ``{"success": False, "error": ...}`` result rather than letting the
        exception propagate out of ``run_agent_sync`` and crash the calling
        test process.
        """
        agent = self._make_test_provider_agent()

        result = self._submit(agent, "TEST_PROVIDER_TIMEOUT")

        self.assertFalse(result.get("success"))
        self.assertTrue(result.get("error"))
        run_id = result["agent_run_id"]
        self._track("Agent Conversation", result["conversation_id"])

        run = frappe.get_doc("Agent Run", run_id)
        self.assertEqual(run.status, "Failed")
        self.assertTrue(run.error_message)
        # The persisted message includes the "<provider>/<model>" routing
        # prefix (e.g. "for Test_Provider/test-model-<hash>."), not just the
        # bare model name -- assert the stable substring only.
        self.assertIn("The AI provider could not complete this request for", run.error_message)
        self.assertIn("test-model", run.error_message)

    # -- AGENT-RUN-004 ------------------------------------------------------

    def test_agent_run_004_now_flag_forces_synchronous_direct_execution(self):
        """Queue-first is the documented default execution path
        (CURRENT_STATE.md section 3: "default execution path enqueues").
        Without a live ``bench worker`` draining the queue in this test
        process, a queued run would never reach a terminal status. This
        test pins down (and documents) that passing ``now=1`` is what makes
        ``run_agent_sync`` execute inline and return only once the run has
        already completed -- proven by asserting the run is ALREADY in a
        terminal status and the response is ALREADY populated by the time
        ``run_agent_sync`` returns, with no polling/sleeping involved.

        UNVERIFIED - coordinator must confirm on real bench: this reasoning
        is derived from reading ``run_agent_sync``'s source
        (``is_queued = not agent_doc.run_immediately and not
        _is_truthy(now)``) rather than from an actual bench run. If this
        assertion fails on the real bench, the most likely cause is that
        direct execution additionally requires ``agent_doc.run_immediately``
        to be truthy (in which case the fix is to also set
        ``run_immediately=1`` on the Agent fixture), or that the Redis
        lock/heartbeat machinery (``_RunHeartbeat``, ``agent_run_conv_{id}``
        key) needs a live Redis connection this test process does not have
        (in which case this test would need `frappe.cache()` verified
        reachable, not merely importable).
        """
        agent = self._make_test_provider_agent()

        result = self._submit(agent, "TEST_TEXT", now=1)

        self.assertTrue(result.get("success"))
        self.assertNotIn("queued", result)  # direct-path response has no "queued" key
        self.assertEqual(result.get("response"), (
            "This is a deterministic TEST_TEXT response from the HUF test provider."
        ))

        run_id = result["agent_run_id"]
        self._track("Agent Conversation", result["conversation_id"])
        run = frappe.get_doc("Agent Run", run_id)
        self.assertIn(run.status, ("Success", "Failed"))  # terminal, not "Queued"/"Started"

    # -- Conversation persistence (exactly one user + one assistant msg) ----

    def test_conversation_persistence_exactly_one_user_and_one_assistant_message(self):
        """A single ``run_agent_sync`` submission on a brand-new conversation
        must persist exactly one ``role="user"`` ``Agent Message`` and
        exactly one ``role="agent"`` ``Agent Message`` -- no duplicates.

        The direct-execution path persists the user message itself
        (``agent_integration.py``: ``conv_manager.add_message(conversation,
        "user", prompt, ...)`` immediately before calling
        ``_execute_agent_run``) and the success path persists exactly one
        assistant message (``conv_manager.add_message(conversation, "agent",
        final_output, ...)``) -- this test pins that 1-to-1 invariant down
        as a regression guard against any future double-submission/retry
        bug duplicating either row.
        """
        agent = self._make_test_provider_agent()

        result = self._submit(agent, "TEST_TEXT")

        self.assertTrue(result.get("success"))
        conversation_id = result["conversation_id"]
        self._track("Agent Conversation", conversation_id)

        user_messages = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id, "role": "user"},
            fields=["name"],
        )
        assistant_messages = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id, "role": "agent", "kind": "Message"},
            fields=["name"],
        )
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(len(assistant_messages), 1)
