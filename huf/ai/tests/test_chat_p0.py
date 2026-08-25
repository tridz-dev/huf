# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration tests for the Chat / conversation
lifecycle described in ``docs/testing/CURRENT_STATE.md`` section 6
("Chat / conversation E2E").

Every test submits a run through the real whitelisted entrypoint
``huf.ai.agent_integration.run_agent_sync`` (never calling internal helpers
like ``ConversationManager.add_message``/``get_or_create_conversation``
directly), forcing synchronous direct execution with ``now=1`` -- the same
pattern already established and confirmed-working in
``huf/ai/tests/test_agent_runtime_p0.py`` (see that file's module docstring
for the full "routing to the test provider" / "queue-first vs. direct
execution" citation chain; not re-derived here).

Routing to the deterministic HUF Test Provider requires an ``AI Provider``
document whose ``name`` (== ``provider_name``, per
``ai_provider.json``'s ``autoname: field:provider_name``) is EXACTLY
"Test_Provider" (case-insensitively) -- ``litellm.py``'s routing check is
`provider.lower() == "test_provider"`, an exact match, not a prefix/substring
check. A prior Phase 3 test task hash-suffixed the name for uniqueness and
broke routing entirely (documented in test_agent_runtime_p0.py). This file
follows that same idempotent get-or-create pattern via
``frappe.db.exists("AI Provider", "Test_Provider")``.

Every fixture created by this file is prefixed "_Test P4CHAT" so it cannot
collide with fixtures created by another concurrent test file sharing the
same site/bench.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_chat_p0
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_chat import get_history
from huf.ai.agent_integration import run_agent_sync
from huf.ai.tests.factories import (
    make_agent,
    make_ai_model,
    make_ai_provider,
    make_user,
)

PREFIX = "_Test P4CHAT"


class TestChatP0(IntegrationTestCase):
    def setUp(self):
        self._names = {
            "Agent": [],
            "AI Model": [],
            "AI Provider": [],
            "Agent Conversation": [],
            "User": [],
        }

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype in ("Agent Conversation", "Agent", "AI Model", "AI Provider", "User"):
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

        Same idempotent get-or-create pattern as
        ``test_agent_runtime_p0.py::_make_test_provider_agent`` -- the AI
        Provider docname MUST be exactly "Test_Provider" (case-insensitive)
        for ``litellm.run()``'s exact-match routing check to fire.
        """
        if frappe.db.exists("AI Provider", "Test_Provider"):
            provider = frappe.get_doc("AI Provider", "Test_Provider")
        else:
            provider = make_ai_provider(provider_name="Test_Provider")
            self._track("AI Provider", provider.name)
        model = make_ai_model(
            provider=provider.name, model_name=f"test-model-{frappe.generate_hash(length=6)}"
        )
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
        process)."""
        prompt = f"__TEST_SCENARIO__:{scenario}"
        kwargs.setdefault("now", 1)
        return run_agent_sync(
            agent_name=agent.name,
            prompt=prompt,
            **kwargs,
        )

    # -- CHAT-001 -----------------------------------------------------------

    def test_chat_001_new_conversation_created_with_correct_agent_and_user(self):
        """Submitting a run with no existing ``Agent Conversation`` for this
        agent/user must create exactly one new ``Agent Conversation`` row,
        associated with the correct agent, and owned by the calling user.
        """
        agent = self._make_test_provider_agent()

        before = frappe.get_all("Agent Conversation", filters={"agent": agent.name})
        self.assertEqual(len(before), 0)

        result = self._submit(agent, "TEST_TEXT")
        self.assertTrue(result.get("success"))
        conversation_id = result["conversation_id"]
        self._track("Agent Conversation", conversation_id)

        after = frappe.get_all(
            "Agent Conversation",
            filters={"agent": agent.name},
            fields=["name", "agent", "owner"],
        )
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].name, conversation_id)
        self.assertEqual(after[0].agent, agent.name)
        self.assertEqual(after[0].owner, frappe.session.user)

    # -- CHAT-002 -----------------------------------------------------------

    def test_chat_002_existing_conversation_message_count_and_index_ordering(self):
        """Submitting a second run against the same conversation (by passing
        the first submission's ``conversation_id`` back in) must:

          - grow the persisted ``Agent Message`` count for that conversation
            by exactly 2 (one new user message, one new assistant message),
          - persist ``conversation_index`` values across BOTH submissions
            that are distinct (no duplicates) and monotonically increasing --
            this directly exercises the ordering concern flagged in
            CURRENT_STATE.md section 6: ``ConversationManager.add_message()``
            computes ``conversation_index`` via a non-atomic
            ``SELECT MAX(...)+1``, and the whitelisted ``add_message`` API
            does not visibly take the conversation lock before calling it.
            This test only proves the sequential (non-concurrent) case is
            correct; it does NOT exercise concurrent submission -- see
            CHAT-002 note below for what remains unverified.
        """
        agent = self._make_test_provider_agent()

        first = self._submit(agent, "TEST_TEXT")
        self.assertTrue(first.get("success"))
        conversation_id = first["conversation_id"]
        self._track("Agent Conversation", conversation_id)

        messages_after_first = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id},
            fields=["name", "conversation_index"],
            order_by="conversation_index asc",
        )
        self.assertEqual(len(messages_after_first), 2)

        second = self._submit(agent, "TEST_TEXT", conversation_id=conversation_id)
        self.assertTrue(second.get("success"))
        # Real API behavior, verified by reading run_agent_sync's persist-
        # conversation branch: the same conversation is reused when
        # conversation_id is passed back in.
        self.assertEqual(second["conversation_id"], conversation_id)

        messages_after_second = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id},
            fields=["name", "conversation_index"],
            order_by="conversation_index asc",
        )
        self.assertEqual(len(messages_after_second), 4)

        indices = [m.conversation_index for m in messages_after_second]
        # No duplicates.
        self.assertEqual(len(indices), len(set(indices)))
        # Strictly increasing, in persisted (insertion) order.
        self.assertEqual(indices, sorted(indices))
        for earlier, later in zip(indices, indices[1:]):
            self.assertLess(earlier, later)

        # UNVERIFIED - coordinator must confirm on real bench: this test
        # only exercises two SEQUENTIAL submissions in the same process/
        # transaction context. It does NOT prove the non-atomic
        # `SELECT MAX(...)+1` in `ConversationManager.add_message()` is safe
        # under genuinely concurrent submissions against the same
        # conversation (e.g. two parallel `add_message`/`run_agent_sync`
        # calls racing on the same `conversation_index`) -- that would
        # require two real concurrent DB connections/threads, which a single
        # `IntegrationTestCase` method run in-process cannot exercise
        # faithfully. The ordering finding in CURRENT_STATE.md section 6
        # remains a *potential* race, not disproven or proven here.

    # -- CHAT-003 -----------------------------------------------------------

    def test_chat_003_owner_or_system_manager_read_gate(self):
        """A conversation's history may be read by its owner or a System
        Manager -- and by nobody else, per the explicit gate in
        ``agent_chat.py::get_history`` (line ~293):
        ``if conv_doc.owner != frappe.session.user and "System Manager" not
        in frappe.get_roles(): frappe.throw(..., frappe.PermissionError)``.
        """
        agent = self._make_test_provider_agent()

        user_a = make_user(
            email=f"{PREFIX.lower().replace(' ', '-')}-a-{frappe.generate_hash(6)}@example.com"
        )
        self._track("User", user_a.name)
        user_b = make_user(
            email=f"{PREFIX.lower().replace(' ', '-')}-b-{frappe.generate_hash(6)}@example.com"
        )
        self._track("User", user_b.name)

        frappe.set_user(user_a.name)
        result = self._submit(agent, "TEST_TEXT")
        self.assertTrue(result.get("success"))
        conversation_id = result["conversation_id"]
        self._track("Agent Conversation", conversation_id)

        conv_doc = frappe.get_doc("Agent Conversation", conversation_id)
        self.assertEqual(conv_doc.owner, user_a.name)

        # User A (the owner) can read their own history.
        history_as_owner = get_history(conversation_id=conversation_id)
        self.assertTrue(len(history_as_owner) >= 1)

        # User B (unrelated, no special role) must be denied.
        frappe.set_user(user_b.name)
        with self.assertRaises(frappe.PermissionError):
            get_history(conversation_id=conversation_id)

        # A System Manager CAN read it regardless of ownership.
        frappe.set_user("Administrator")
        history_as_admin = get_history(conversation_id=conversation_id)
        self.assertEqual(len(history_as_admin), len(history_as_owner))

    # -- CHAT-004 -----------------------------------------------------------

    def test_chat_004_no_server_side_cancel_api_exists(self):
        """Prove the absence of a server-side cancel/stop API, per
        CURRENT_STATE.md section 3/6: "No server-side cancel/stop API exists
        anywhere" -- frontend "Stop" only aborts the client-side fetch for
        the SSE streaming path; the queue-first REST path has nothing to
        abort server-side.

        This introspects the actual whitelisted API surface of the two
        chat-related modules (``huf.ai.agent_chat``, ``huf.ai.chat_api``)
        plus ``huf.ai.agent_integration`` (where ``run_agent_sync``/
        ``get_agent_run_status`` live) for any ``@frappe.whitelist()``
        function whose name contains "cancel" or "stop" and appears to
        operate on a Conversation/Agent Run, rather than re-asserting the
        CURRENT_STATE.md claim blindly.
        """
        import huf.ai.agent_chat as agent_chat_module
        import huf.ai.chat_api as chat_api_module
        import huf.ai.agent_integration as agent_integration_module

        suspicious = []
        for module in (agent_chat_module, chat_api_module, agent_integration_module):
            for name in dir(module):
                if name.startswith("_"):
                    continue
                obj = getattr(module, name)
                if not callable(obj):
                    continue
                # Established repo pattern for checking whitelisted-ness of a
                # resolved function without invoking it -- see
                # huf/huf/doctype/agent_tool_function/agent_tool_function.py
                # ::get_function_metadata, which does exactly this
                # try/except around `frappe.is_whitelisted(func)` (there is
                # no simple boolean attribute on the function itself).
                try:
                    frappe.is_whitelisted(obj)
                except Exception:
                    continue
                lowered = name.lower()
                if "cancel" in lowered or "stop" in lowered:
                    suspicious.append(f"{module.__name__}.{name}")

        if suspicious:
            self.fail(
                "CURRENT_STATE.md is stale -- a cancel/stop-shaped whitelisted "
                "API now exists: " + ", ".join(suspicious) + ". Coordinator must "
                "re-audit docs/testing/CURRENT_STATE.md section 6 and, if this "
                "is a real cancel/stop endpoint operating on Conversation/Agent "
                "Run, replace this absence-test with a real behavioral test of "
                "it."
            )
        # No whitelisted cancel/stop-named function found -- matches
        # CURRENT_STATE.md's Phase 0 grep-based audit finding.

    # -- CHAT-005 -----------------------------------------------------------

    def test_chat_005_regenerate_never_mutates_existing_history(self):
        """Per CURRENT_STATE.md section 6: "Regeneration never mutates
        history in place -- always appends a new user+assistant turn."
        Submitting a second run on the same conversation must leave the
        ORIGINAL first user+assistant ``Agent Message`` rows completely
        unchanged (same name, same content, same conversation_index) and
        only append new rows.
        """
        agent = self._make_test_provider_agent()

        first = self._submit(agent, "TEST_TEXT")
        self.assertTrue(first.get("success"))
        conversation_id = first["conversation_id"]
        self._track("Agent Conversation", conversation_id)

        original_messages = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id},
            fields=["name", "role", "content", "conversation_index", "modified"],
            order_by="conversation_index asc",
        )
        self.assertEqual(len(original_messages), 2)
        original_snapshot = [dict(m) for m in original_messages]

        second = self._submit(agent, "TEST_TEXT", conversation_id=conversation_id)
        self.assertTrue(second.get("success"))

        all_messages_after = frappe.get_all(
            "Agent Message",
            filters={"conversation": conversation_id},
            fields=["name", "role", "content", "conversation_index", "modified"],
            order_by="conversation_index asc",
        )
        self.assertEqual(len(all_messages_after), 4)

        # The first two rows (by conversation_index) must be byte-identical
        # to the original snapshot -- same name, role, content, index.
        for original, current in zip(original_snapshot, all_messages_after[:2]):
            self.assertEqual(current["name"], original["name"])
            self.assertEqual(current["role"], original["role"])
            self.assertEqual(current["content"], original["content"])
            self.assertEqual(
                current["conversation_index"], original["conversation_index"]
            )

        # The new rows are genuinely new documents (different names), not
        # the same rows edited in place.
        original_names = {m["name"] for m in original_snapshot}
        new_names = {m["name"] for m in all_messages_after[2:]}
        self.assertEqual(len(original_names & new_names), 0)

    # -- CHAT-006 -----------------------------------------------------------

    def test_chat_006_no_duplicate_messages_per_submission(self):
        """P0 acceptance criterion (GOAL.md section 27): a single
        ``run_agent_sync`` submission must produce exactly one persisted
        user ``Agent Message`` and exactly one assistant ``Agent Message`` --
        never two of either, e.g. from a double-submission/retry bug.
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
