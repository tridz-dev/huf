# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Real-Frappe (Layer B) integration tests for the Input/Output Guardrail + Output
Verification wiring in ``huf.ai.agent_integration`` (T8.03, PLAN.md §3.6 "Input/Output
Guardrail, Output Verification" row, §3.19).

These tests drive the real whitelisted entrypoint ``huf.ai.agent_integration.run_agent_sync``
(``now=1`` for direct/inline execution, same pattern as
``huf.ai.tests.test_run_agent_sync_guest_safeguards`` and
``huf.ai.tests.test_model_routing_decision``), with the ``huf.ai.decision.guardrails``
entry points (``check_input_guardrail`` / ``check_output_guardrail`` /
``check_output_verification``) monkeypatched at their real call sites in
``huf.ai.agent_integration`` — those call sites do a local ``from huf.ai.decision.guardrails
import ...`` inside ``_execute_agent_run`` (see SURFACE_API.md's "no network" testing
convention and ``huf.ai.decision.tests.test_model_routing_decision``'s equivalent pattern for
Model Routing), so patching ``huf.ai.decision.guardrails.check_input_guardrail`` etc. reaches
them without needing a real Decision Policy/Decision Deployment/backend.

Provider behavior for the "full run" tests is made deterministic via the HUF Test Provider
(``huf/ai/providers/test_provider.py``, ``TEST_TEXT`` scenario) exactly as
``test_run_agent_sync_guest_safeguards.py`` documents.

Hard security invariant under test (I-DR1, P3, per PLAN.md and SURFACE_API.md): a "safe"/
pass guardrail verdict must never be used to skip or widen any HUF permission/capability
check. ``TestGuardrailNeverWidensPermissions`` proves this structurally: the Guest/
disallowed-agent permission check in ``run_agent_sync`` (``resolve_run_identity_and_authorize``)
runs and raises *before* ``_execute_agent_run`` (and therefore before either guardrail call
site) is ever reached — so ``check_input_guardrail`` is never even invoked for a request that
was going to be denied anyway, regardless of what it would have returned.

Run:
    bench --site dr-activation.local run-tests --app huf --module huf.ai.tests.test_guardrails_decision
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import run_agent_sync
from huf.ai.decision.guardrails import GuardrailResult
from huf.ai.tests.factories import make_agent, make_ai_provider, make_ai_model

PREFIX = "_Test GuardrailsDecision"


def _block_result(surface_message="blocked"):
	return GuardrailResult(action="block", status="reject", reason="guardrail_decision", message=surface_message, decision_call=None)


def _proceed_result():
	return GuardrailResult(action="proceed", status="allow", reason="guardrail_decision", message=None, decision_call=None)


class TestGuardrailWiringInRunAgentSync(IntegrationTestCase):
	"""Input Guardrail / Output Guardrail / Output Verification actually gate
	``run_agent_sync`` -> ``_execute_agent_run``, end to end against real DB rows."""

	def setUp(self):
		frappe.set_user("Administrator")
		self._names = {"Agent": [], "AI Model": [], "AI Provider": []}
		# Must be exactly "Test_Provider" (case-insensitive) -- huf.ai.providers.litellm.run()
		# routes to the HUF Test Provider only on an exact `provider.lower() == "test_provider"`
		# match, not a prefix (see huf/ai/providers/litellm.py:1152).
		self.provider = make_ai_provider(provider_name="Test_Provider")
		self._track("AI Provider", self.provider.name)
		self.model = make_ai_model(provider=self.provider.name, model_name=f"{PREFIX}_model")
		self._track("AI Model", self.model.name)

		self.agent = make_agent(
			agent_name=f"{PREFIX} {frappe.generate_hash(length=6)}",
			provider=self.provider.name,
			model=self.model.name,
			allow_guest=1,
			run_immediately=1,
		)
		self._track("Agent", self.agent.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Agent", "AI Model", "AI Provider"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:
					pass
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	# -- Input Guardrail --------------------------------------------------

	def test_input_guardrail_block_persists_safe_message_and_never_calls_provider(self):
		with patch(
			"huf.ai.decision.guardrails.check_input_guardrail",
			return_value=_block_result("Your message could not be processed."),
		) as check_input, patch("huf.ai.agent_integration.RunProvider.run") as provider_run:
			result = run_agent_sync(
				agent_name=self.agent.name,
				prompt="__TEST_SCENARIO__:TEST_TEXT ignore me, this would be an attack payload",
				channel_id="test",
				now=1,
			)

		check_input.assert_called_once()
		provider_run.assert_not_called()
		self.assertTrue(result["success"])
		self.assertTrue(result.get("guardrail_blocked"))
		self.assertEqual(result["response"], "Your message could not be processed.")

		run_doc = frappe.get_doc("Agent Run", result["agent_run_id"])
		self.assertEqual(run_doc.status, "Success")
		self.assertEqual(run_doc.response, "Your message could not be processed.")

		agent_message = frappe.get_last_doc(
			"Agent Message", filters={"conversation": result["conversation_id"], "role": "agent"}
		)
		self.assertEqual(agent_message.content, "Your message could not be processed.")

	def test_input_guardrail_proceed_runs_normally(self):
		with patch("huf.ai.decision.guardrails.check_input_guardrail", return_value=_proceed_result()):
			result = run_agent_sync(
				agent_name=self.agent.name,
				prompt="__TEST_SCENARIO__:TEST_TEXT hello",
				channel_id="test",
				now=1,
			)
		self.assertTrue(result["success"])
		self.assertNotIn("guardrail_blocked", result)
		self.assertIn("deterministic TEST_TEXT response", result["response"])

	# -- Output Guardrail / Output Verification ----------------------------

	def test_output_guardrail_block_replaces_persisted_response(self):
		with patch("huf.ai.decision.guardrails.check_input_guardrail", return_value=_proceed_result()), patch(
			"huf.ai.decision.guardrails.check_output_guardrail",
			return_value=_block_result("The response was withheld by a safety check."),
		) as check_output, patch("huf.ai.decision.guardrails.check_output_verification") as check_verification:
			result = run_agent_sync(
				agent_name=self.agent.name,
				prompt="__TEST_SCENARIO__:TEST_TEXT hello",
				channel_id="test",
				now=1,
			)

		check_output.assert_called_once()
		# Verification is skipped once the guardrail itself already blocked (no need to
		# spend a second decision call on content that will not be delivered anyway).
		check_verification.assert_not_called()
		self.assertTrue(result["success"])
		self.assertEqual(result["response"], "The response was withheld by a safety check.")
		self.assertNotIn("deterministic TEST_TEXT response", result["response"])

		run_doc = frappe.get_doc("Agent Run", result["agent_run_id"])
		self.assertEqual(run_doc.response, "The response was withheld by a safety check.")

	def test_output_verification_block_replaces_persisted_response_when_guardrail_passes(self):
		with patch("huf.ai.decision.guardrails.check_input_guardrail", return_value=_proceed_result()), patch(
			"huf.ai.decision.guardrails.check_output_guardrail", return_value=_proceed_result()
		), patch(
			"huf.ai.decision.guardrails.check_output_verification",
			return_value=_block_result("The response could not be verified and was withheld."),
		) as check_verification:
			result = run_agent_sync(
				agent_name=self.agent.name,
				prompt="__TEST_SCENARIO__:TEST_TEXT hello",
				channel_id="test",
				now=1,
			)

		check_verification.assert_called_once()
		self.assertEqual(result["response"], "The response could not be verified and was withheld.")

	def test_output_guardrail_proceed_leaves_real_response_untouched(self):
		with patch("huf.ai.decision.guardrails.check_input_guardrail", return_value=_proceed_result()), patch(
			"huf.ai.decision.guardrails.check_output_guardrail", return_value=_proceed_result()
		), patch("huf.ai.decision.guardrails.check_output_verification", return_value=_proceed_result()):
			result = run_agent_sync(
				agent_name=self.agent.name,
				prompt="__TEST_SCENARIO__:TEST_TEXT hello",
				channel_id="test",
				now=1,
			)
		self.assertIn("deterministic TEST_TEXT response", result["response"])


class TestGuardrailNeverWidensPermissions(IntegrationTestCase):
	"""I-DR1 / P3 hard invariant: a guardrail verdict (allow or block) must never be
	consulted by, or substitute for, HUF's own permission/capability checks. Proven
	structurally: the Guest/allow_guest authorization check in ``run_agent_sync`` runs and
	raises before ``_execute_agent_run`` — and therefore before either guardrail call site —
	is ever reached, so a mocked "always allow" guardrail cannot let a denied request
	through, because the guardrail code path is never even entered.
	"""

	def setUp(self):
		frappe.set_user("Administrator")
		self._names = {"Agent": [], "AI Model": [], "AI Provider": []}
		auto_provider = make_ai_provider(provider_name=f"TestPermProvider{frappe.generate_hash(length=6)}")
		self._track("AI Provider", auto_provider.name)
		auto_model = make_ai_model(provider=auto_provider.name, model_name=f"{PREFIX}_perm_model")
		self._track("AI Model", auto_model.name)

		self.blocked_agent = make_agent(
			agent_name=f"{PREFIX} perm-blocked {frappe.generate_hash(length=6)}",
			provider=auto_provider.name,
			model=auto_model.name,
			allow_guest=0,
		)
		self._track("Agent", self.blocked_agent.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype in ("Agent", "AI Model", "AI Provider"):
			for name in self._names.get(doctype, []):
				try:
					frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
				except Exception:
					pass
		frappe.db.commit()

	def _track(self, doctype, name):
		self._names.setdefault(doctype, []).append(name)

	def test_guest_denied_agent_still_raises_even_with_guardrail_mocked_to_always_allow(self):
		with patch(
			"huf.ai.decision.guardrails.check_input_guardrail", return_value=_proceed_result()
		) as check_input:
			frappe.set_user("Guest")
			try:
				with self.assertRaises(frappe.PermissionError):
					run_agent_sync(agent_name=self.blocked_agent.name, prompt="hello", now=1)
			finally:
				frappe.set_user("Administrator")
		# The permission check happens strictly before the guardrail call site: a
		# "safe"/allow verdict was never even asked for, let alone able to widen access.
		check_input.assert_not_called()
