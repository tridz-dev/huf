# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration tests for the Automation Decide runtime
(PLAN.md §3.7, T6.02): ``huf.ai.automation_runner._execute``'s Decision
branch (``_execute_decision``) and the recursion guard in
``huf.ai.automation_hooks.run_hooked_automations``.

Exercised through ``huf.ai.automation_runner.run_automation`` directly with a
hand-built ``trigger_context`` carrying ``reference_doctype``/``reference_name``
-- the same two keys ``huf.ai.automation_hooks.run_automation_for_doc`` would
supply for a real Doc Event trigger. This is the same shortcut
``huf/ai/tests/test_automation_p0.py``'s "AUTO-007" note documents taking:
the actual doc-event dispatch (``run_hooked_automations`` -> ``frappe.db.after_commit``
-> ``enqueue`` -> a real RQ "long" queue) has no deterministic synchronous
in-process call this test could invoke; what matters for T6.02's acceptance is
what ``_execute_decision`` does once it has a reference document, which this
tests directly.

Decision Policy fixtures use the zero-network, zero-config ``local_rules``
backend adapter (``huf.ai.decision.backends.local.LocalRulesBackend``,
registered as ``huf_decision_backends["local_rules"]`` in ``huf/hooks.py``)
via a ``Decision Model Family`` with ``adapter_id = "local_rules"`` --
mirroring the fixture-building pattern in
``huf/ai/decision/tests/test_service.py`` (Provider -> AI Model -> Model
Class -> Model Family -> Decision Model -> Decision Deployment -> Decision
Policy -> published version), swapping only the family's ``adapter_id`` and
the policy's question shape. ``LocalRulesBackend()`` with no configured
rules always answers a ``select`` question with its first option's id
(``huf/ai/decision/backends/local.py:24-30``: ``self.rules.get(question.id)``
is ``None``, so it falls back to ``question.options[0].id``) -- deterministic
with no mocking needed. Skip / Mark Error / Set Fallback Value are exercised
by giving ``decision_output_map`` a key that does NOT match that first
option's id, which is exactly the "answer produced but unmapped" failure path
``_map_decision_answer`` documents, not a Decision Runtime failure -- the
runtime's own low-confidence/error statuses are already covered by
``huf/ai/decision/tests/test_service.py`` and are not re-tested here.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_automation_decide
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import IntegrationTestCase

from huf.ai import automation_hooks
from huf.ai.automation_runner import run_automation
from huf.ai.tests.factories import make_agent, make_automation

PREFIX = "_Test Automation Decide Exec"


class TestAutomationDecisionExecute(IntegrationTestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]

        self._prev_kill_switch = frappe.db.get_single_value(
            "Agent Settings", "decision_runtime_enabled"
        )
        frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

        self.provider = frappe.get_doc(
            {
                "doctype": "AI Provider",
                "provider_name": f"TestDecideProvider{self.suffix}",
                "provider_brand": "other",
                "api_base_url": "https://example.test",
                "api_key": "test-secret-key",
            }
        ).insert(ignore_permissions=True)

        self.ai_model = frappe.get_doc(
            {
                "doctype": "AI Model",
                "model_name": f"test-decide-model-{self.suffix}",
                "provider": self.provider.name,
                "modalities": "Decision",
            }
        ).insert(ignore_permissions=True)

        self.model_class = frappe.get_doc(
            {
                "doctype": "Decision Model Class",
                "class_key": f"test_decide_class_{self.suffix}",
                "class_name": "Test Decide Class",
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        self.family = frappe.get_doc(
            {
                "doctype": "Decision Model Family",
                "family_key": f"test_decide_family_{self.suffix}",
                "family_name": "Test Decide Family",
                "adapter_id": "local_rules",
                "model_class": self.model_class.name,
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        # model_key must be exactly "Local Rules v1": LocalRulesBackend
        # (huf/ai/decision/backends/local.py) hard-codes its DecisionIdentity's
        # canonical_model to that literal (resolve_backend() instantiates it
        # with the zero-arg constructor -- it defines no from_deployment, so
        # nothing about this specific deployment/model ever reaches it), and
        # huf.ai.decision.persistence's telemetry sink writes
        # `identity.canonical_model` straight into Decision Call.decision_model
        # (a Link to Decision Model). Any other model_key here makes doc.insert()
        # fail Frappe's Link-target validation for every local_rules call,
        # silently swallowed by DecisionRuntime._emit -- ServiceResult.decision_call
        # stays None even though the decision itself succeeded. Not a T6.02 bug;
        # flagged in this task's report as a pre-existing local_rules/persistence
        # gap. Scoped to setUp/tearDown of this one test method, serialized with
        # every other bench command on this site via `drb`'s flock.
        self.decision_model = frappe.get_doc(
            {
                "doctype": "Decision Model",
                "model_key": "Local Rules v1",
                "model_name": "Local Rules v1",
                "family": self.family.name,
                "canonical_version": "1.0",
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

        self.deployment = frappe.get_doc(
            {
                "doctype": "Decision Deployment",
                "deployment_key": f"dep-decide-{self.suffix}",
                "deployment_name": "Test Decide Deployment",
                "decision_model": self.decision_model.name,
                "ai_model": self.ai_model.name,
                "provider": self.provider.name,
                "provider_model_id": self.ai_model.name,
                "wire_protocol": "systemone",
                "priority": 100,
                "enabled": 1,
                "is_default_for_model": 1,
            }
        ).insert(ignore_permissions=True)

        self.policy = frappe.get_doc(
            {
                "doctype": "Decision Policy",
                "policy_name": f"Test Decide Policy {self.suffix}",
                "purpose": "Tool Selection",
                "default_model": self.decision_model.name,
                "enabled": 1,
                "definition_json": frappe.as_json(self._definition()),
            }
        ).insert(ignore_permissions=True)
        self.published_version = self.policy.publish_version()

        self.todo = frappe.get_doc(
            {
                "doctype": "ToDo",
                "description": f"{PREFIX} target {self.suffix}",
            }
        ).insert(ignore_permissions=True)

        self.automation = frappe.get_doc(
            {
                "doctype": "Automation",
                "automation_name": f"{PREFIX} {self.suffix}",
                "action_type": "Decision",
                "decision_policy": self.policy.name,
                "decision_output_field": "priority",
                # "p0" is the first option's id -- LocalRulesBackend's
                # deterministic default answer (see module docstring).
                "decision_output_map": json.dumps({"p0": "High"}),
                "decision_on_failure": "Skip",
                "status": "Draft",
            }
        ).insert(ignore_permissions=True)

    def tearDown(self):
        frappe.set_user("Administrator")
        # Decision Call rows link to this test's Decision Model / Decision
        # Policy Version / Decision Deployment; those must go first, same
        # ordering rationale as huf/ai/decision/tests/test_service.py.
        for call_name in frappe.get_all(
            "Decision Call", filters={"decision_model": self.decision_model.name}, pluck="name"
        ):
            frappe.delete_doc(
                "Decision Call", call_name, ignore_permissions=True, ignore_missing=True, force=True
            )
        frappe.delete_doc("Automation", self.automation.name, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc("ToDo", self.todo.name, ignore_permissions=True, ignore_missing=True)
        frappe.db.set_value(
            "Decision Policy", self.policy.name, "current_version", None, update_modified=False
        )
        frappe.delete_doc(
            "Decision Policy Version", self.published_version, ignore_permissions=True, ignore_missing=True
        )
        frappe.delete_doc("Decision Policy", self.policy.name, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc(
            "Decision Deployment", self.deployment.name, ignore_permissions=True, ignore_missing=True
        )
        frappe.delete_doc("Decision Model", self.decision_model.name, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc(
            "Decision Model Family", self.family.name, ignore_permissions=True, ignore_missing=True
        )
        frappe.delete_doc(
            "Decision Model Class", self.model_class.name, ignore_permissions=True, ignore_missing=True
        )
        frappe.delete_doc("AI Model", self.ai_model.name, ignore_permissions=True, ignore_missing=True)
        frappe.delete_doc("AI Provider", self.provider.name, ignore_permissions=True, ignore_missing=True)
        frappe.db.set_single_value(
            "Agent Settings", "decision_runtime_enabled", self._prev_kill_switch
        )
        frappe.db.commit()

    @staticmethod
    def _definition():
        return {
            "policy_id": "automation-priority-classify",
            "fallback_action": "fallback_default",
            "state_bindings": [{"name": "state", "path": "$"}],
            "questions": [
                {
                    "id": "priority",
                    "kind": "select",
                    "instructions": "What priority should this ToDo have?",
                    "options": [
                        {"id": "p0", "description": "Urgent"},
                        {"id": "p1", "description": "Normal"},
                    ],
                }
            ],
        }

    def _trigger_context(self):
        return {
            "type": "doc_event",
            "event_name": "on_update",
            "reference_doctype": "ToDo",
            "reference_name": self.todo.name,
        }

    def _run(self):
        return run_automation(
            self.automation.name,
            trigger_context=self._trigger_context(),
            initiating_user="Administrator",
            commit=False,
        )

    # -- Success --------------------------------------------------------------------

    def test_success_writes_mapped_field_and_bookkeeping(self):
        result = self._run()

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "success")
        self.assertIsNotNone(result["decision_call"])
        self.assertTrue(result["wrote"])

        self.todo.reload()
        self.assertEqual(self.todo.priority, "High")

        self.automation.reload()
        self.assertEqual(self.automation.last_decision_call, result["decision_call"])
        self.assertEqual(self.automation.last_status, "Active")
        self.assertEqual(self.automation.last_error, "")
        self.assertEqual(self.automation.total_runs, 1)

        call = frappe.get_doc("Decision Call", result["decision_call"])
        self.assertEqual(call.origin_type, "Automation")
        self.assertEqual(call.automation, self.automation.name)
        self.assertEqual(call.mode, "Enforce")

    # -- Skip (decision_on_failure default) ------------------------------------------

    def test_skip_on_unmapped_answer_leaves_field_untouched(self):
        self.automation.db_set("decision_output_map", json.dumps({"not-p0": "Low"}), update_modified=False)

        result = self._run()

        self.assertTrue(result["success"])
        self.assertFalse(result["wrote"])

        self.todo.reload()
        self.assertNotEqual(self.todo.priority, "Low")

        self.automation.reload()
        self.assertEqual(self.automation.last_status, "Active")
        self.assertEqual(self.automation.last_error, "")

    # -- Mark Error ---------------------------------------------------------------

    def test_mark_error_on_unmapped_answer(self):
        self.automation.db_set("decision_output_map", json.dumps({"not-p0": "Low"}), update_modified=False)
        self.automation.db_set("decision_on_failure", "Mark Error", update_modified=False)

        result = self._run()

        self.assertFalse(result["success"])
        self.assertFalse(result["wrote"])

        self.todo.reload()
        self.assertNotEqual(self.todo.priority, "Low")

        self.automation.reload()
        self.assertEqual(self.automation.last_status, "Error")
        self.assertTrue(self.automation.last_error)

    # -- Set Fallback Value --------------------------------------------------------

    def test_fallback_value_written_on_unmapped_answer(self):
        self.automation.db_set("decision_output_map", json.dumps({"not-p0": "Low"}), update_modified=False)
        self.automation.db_set("decision_on_failure", "Set Fallback Value", update_modified=False)
        self.automation.db_set("decision_fallback_value", "Medium", update_modified=False)

        result = self._run()

        self.assertTrue(result["success"])
        self.assertTrue(result["wrote"])

        self.todo.reload()
        self.assertEqual(self.todo.priority, "Medium")

        self.automation.reload()
        self.assertEqual(self.automation.last_status, "Active")
        self.assertEqual(self.automation.last_error, "")

    # -- No target document (Manual/Schedule/Webhook/App Event) ---------------------

    def test_no_reference_document_marks_error_not_silent_skip(self):
        result = run_automation(
            self.automation.name,
            trigger_context=None,
            initiating_user="Administrator",
            commit=False,
        )

        self.assertFalse(result["success"])
        self.automation.reload()
        self.assertEqual(self.automation.last_status, "Error")
        self.assertTrue(self.automation.last_error)

    # -- Permission check -----------------------------------------------------------

    def test_permission_denied_blocks_write_and_marks_error(self):
        with patch("huf.ai.automation_runner.frappe.has_permission", return_value=False):
            result = self._run()

        self.assertFalse(result["success"])
        self.todo.reload()
        self.assertNotEqual(self.todo.priority, "High")

        self.automation.reload()
        self.assertEqual(self.automation.last_status, "Error")

    # -- No recursion -----------------------------------------------------------

    def test_write_sets_and_clears_recursion_guard_flag(self):
        """The db_set() call that writes decision_output_field must run while
        huf_decision_write_refs names this exact document, and the flag must be
        cleared again once the write returns -- so a later, unrelated hook fire
        for a different document is never mistaken for this one."""
        captured = {}
        original_db_set = Document.db_set

        def spy_db_set(self_doc, *args, **kwargs):
            # _update_automation_bookkeeping() also calls db_set() (on the
            # Automation doc, after the ToDo write returns and the guard flag
            # is already cleared) -- only capture the flag state for the
            # write this test cares about, the one on the reference document.
            if self_doc.doctype == self.todo.doctype and self_doc.name == self.todo.name:
                captured["refs_during_write"] = set(frappe.flags.get("huf_decision_write_refs") or ())
            return original_db_set(self_doc, *args, **kwargs)

        with patch.object(Document, "db_set", spy_db_set):
            result = self._run()

        self.assertTrue(result["wrote"])
        self.assertIn(f"ToDo::{self.todo.name}", captured["refs_during_write"])
        # Cleared afterwards -- not left dangling for a later, unrelated write.
        self.assertFalse(frappe.flags.get("huf_decision_write_refs"))

    def test_recursion_guard_skips_matching_doc_in_run_hooked_automations(self):
        """automation_hooks.run_hooked_automations must return immediately for a
        document currently being written by a Decision action's own output
        write, before it even looks up matching Automation Triggers."""
        guard_key = f"{self.todo.doctype}::{self.todo.name}"
        frappe.flags.huf_decision_write_refs = {guard_key}
        try:
            with patch(
                "huf.ai.automation_hooks.get_doc_event_automation_triggers"
            ) as mock_get_triggers:
                automation_hooks.run_hooked_automations(self.todo, method="on_update")
                mock_get_triggers.assert_not_called()
        finally:
            frappe.flags.huf_decision_write_refs = None

    def test_recursion_guard_does_not_affect_unrelated_documents(self):
        """The guard is scoped to the exact document being written -- an
        unrelated document's doc-event processing must proceed normally."""
        other_todo = frappe.get_doc(
            {"doctype": "ToDo", "description": f"{PREFIX} unrelated {self.suffix}"}
        ).insert(ignore_permissions=True)
        try:
            frappe.flags.huf_decision_write_refs = {f"ToDo::{self.todo.name}"}
            try:
                with patch(
                    "huf.ai.automation_hooks.get_doc_event_automation_triggers", return_value=[]
                ) as mock_get_triggers:
                    automation_hooks.run_hooked_automations(other_todo, method="on_update")
                    mock_get_triggers.assert_called_once()
            finally:
                frappe.flags.huf_decision_write_refs = None
        finally:
            frappe.delete_doc("ToDo", other_todo.name, ignore_permissions=True, ignore_missing=True)

    # -- Existing Agent Run automations are untouched --------------------------------

    def test_agent_run_automation_still_uses_run_agent_sync(self):
        agent = make_agent(agent_name=f"{PREFIX} agent {self.suffix}")
        agent_automation = make_automation(
            automation_name=f"{PREFIX} agentrun {self.suffix}",
            agent=agent.name,
            instruction="Do the deterministic test thing.",
        )
        try:
            with patch("huf.ai.agent_integration.run_agent_sync") as mock_run_agent_sync:
                mock_run_agent_sync.return_value = {
                    "success": True,
                    "agent_run_id": f"AR-{PREFIX}-{self.suffix}",
                    "conversation_id": None,
                }
                result = run_automation(
                    agent_automation.name,
                    trigger_context=None,
                    initiating_user="Administrator",
                    commit=False,
                )

            mock_run_agent_sync.assert_called_once()
            self.assertEqual(result["agent_run_id"], f"AR-{PREFIX}-{self.suffix}")

            agent_automation.reload()
            self.assertEqual(agent_automation.last_run, f"AR-{PREFIX}-{self.suffix}")
            self.assertEqual(agent_automation.last_status, "Active")
        finally:
            frappe.delete_doc("Automation", agent_automation.name, ignore_permissions=True, ignore_missing=True)
            frappe.delete_doc("Agent", agent.name, ignore_permissions=True, ignore_missing=True)
            frappe.delete_doc("AI Model", agent.model, ignore_permissions=True, ignore_missing=True)
            frappe.delete_doc("AI Provider", agent.provider, ignore_permissions=True, ignore_missing=True)
