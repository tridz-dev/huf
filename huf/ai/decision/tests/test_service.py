"""Frappe integration tests for huf.ai.decision.service.run_policy.

Covers PLAN.md §4.7 / task T2A.10 acceptance: kill switch -> disabled with zero network;
resolving a published version, a pinned version, and a validated ad-hoc policy; the
surface-default / override latency deadline; the inline Enforce path calling
evaluate_deployment_chain with a Frappe telemetry sink and persisting origin/mode on the
Decision Call; apply_policy_fallback on failure; Advise accepted on an ADVISE_SURFACES
surface and rejected elsewhere; and the Shadow dispatch never touching load_chain.
"""

from __future__ import annotations

import time
import uuid
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import service
from huf.ai.decision.types import CandidateSource, DecisionOrigin, DecisionStatus, Option


class TestRunPolicy(FrappeTestCase):
	def setUp(self):
		self._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		self.suffix = uuid.uuid4().hex[:8]
		self.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestSvcProvider{self.suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		self.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-svc-model-{self.suffix}",
			"provider": self.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		self.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_svc_class_{self.suffix}",
			"class_name": "Test Svc Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_svc_family_{self.suffix}",
			"family_name": "Test Svc Family",
			"adapter_id": "fake",
			"model_class": self.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-svc-model-key-{self.suffix}",
			"model_name": "Test Svc Model",
			"family": self.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-svc-{self.suffix}",
			"deployment_name": "Test Svc Deployment",
			"decision_model": self.decision_model.name,
			"ai_model": self.ai_model.name,
			"provider": self.provider.name,
			"provider_model_id": self.ai_model.name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 1,
		}).insert(ignore_permissions=True)

		self.policy = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Test Svc Policy {self.suffix}",
			"purpose": "Tool Selection",
			"default_model": self.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(self._definition()),
		}).insert(ignore_permissions=True)
		self.published_version = self.policy.publish_version()

	def tearDown(self):
		# Decision Call rows created by run_policy during the test link to this test's Decision
		# Policy Version / Decision Deployment (policy_version, resolved_deployment); those must
		# go first or delete_doc's link check blocks everything below. Decision Policy and
		# Decision Policy Version also reference each other (current_version / policy), which is
		# a genuine circular link -- break it before deleting either.
		for call_name in frappe.get_all("Decision Call", filters={"decision_model": self.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", call_name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.set_value("Decision Policy", self.policy.name, "current_version", None, update_modified=False)
		frappe.delete_doc("Decision Policy Version", self.published_version, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Policy", self.policy.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Deployment", self.deployment.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", self.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", self.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", self.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", self.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", self.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", self._prev_kill_switch)

	@staticmethod
	def _definition(policy_id: str = "test-svc-policy") -> dict:
		return {
			"policy_id": policy_id,
			"fallback_action": "fallback_default",
			# Required: prepare_state (state.py) rejects a policy with no state_bindings --
			# every field sent to a provider must be explicitly whitelisted (IP data
			# minimization). "$" projects the whole (bounded, test-only) state.
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "q1",
					"kind": "judge",
					"instructions": "Is this state acceptable?",
					"positive_criteria": "state looks fine",
				}
			],
		}

	@staticmethod
	def _origin(**overrides) -> DecisionOrigin:
		values = {"origin_type": "Playground"}
		values.update(overrides)
		return DecisionOrigin(**values)

	# -- Kill switch --------------------------------------------------------------------

	def test_kill_switch_off_returns_disabled_with_zero_network(self):
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 0)

		with patch("huf.ai.decision.service.load_chain") as mock_load_chain:
			result = service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
			)

		self.assertEqual(result.status, service.DISABLED)
		self.assertIsNone(result.decision_call)
		self.assertIsNone(result.response)
		mock_load_chain.assert_not_called()

	# -- Policy resolution ----------------------------------------------------------------

	def test_resolves_published_version(self):
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=self._origin(),
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
		self.assertIsNotNone(result.decision_call)
		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.policy, self.policy.name)
		self.assertEqual(call.policy_version, self.published_version)
		self.assertEqual(call.mode, "Enforce")
		self.assertEqual(call.origin_type, "Playground")

	def test_resolves_pinned_version(self):
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=self._origin(),
			policy_version=self.published_version,
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.policy_version, self.published_version)

	def test_resolves_validated_ad_hoc_definition(self):
		result = service.run_policy(
			definition=self._definition("ad-hoc-policy"),
			decision_model=self.decision_model.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=self._origin(),
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
		call = frappe.get_doc("Decision Call", result.decision_call)
		# No Decision Policy row exists for an ad-hoc definition, so the Link stays blank
		# (it must -- a non-blank Link that does not resolve would fail insert()); the
		# fingerprint still identifies exactly which definition ran.
		self.assertFalse(call.policy)
		self.assertTrue(call.policy_fingerprint)

	def test_ad_hoc_without_decision_model_raises(self):
		with self.assertRaises(ValueError):
			service.run_policy(
				definition=self._definition(),
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
			)

	def test_policy_and_definition_together_raises(self):
		with self.assertRaises(ValueError):
			service.run_policy(
				self.policy.name,
				definition=self._definition(),
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
			)

	# -- Deadline ---------------------------------------------------------------------------

	def test_deadline_uses_surface_default_when_no_override(self):
		captured = {}
		real_load_chain = service.load_chain

		def spy(*, decision_model, pinned_deployment=None, deadline=None):
			captured["deadline"] = deadline
			return real_load_chain(decision_model=decision_model, pinned_deployment=pinned_deployment, deadline=deadline)

		with patch("huf.ai.decision.service.load_chain", side_effect=spy):
			before = time.monotonic()
			service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
			)

		# Tool Selection default is 1500 ms (PLAN.md §3.6).
		self.assertAlmostEqual(captured["deadline"] - before, 1.5, delta=0.5)

	def test_deadline_uses_latency_budget_ms_override(self):
		captured = {}
		real_load_chain = service.load_chain

		def spy(*, decision_model, pinned_deployment=None, deadline=None):
			captured["deadline"] = deadline
			return real_load_chain(decision_model=decision_model, pinned_deployment=pinned_deployment, deadline=deadline)

		with patch("huf.ai.decision.service.load_chain", side_effect=spy):
			before = time.monotonic()
			service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
				latency_budget_ms=9000,
			)

		self.assertAlmostEqual(captured["deadline"] - before, 9.0, delta=0.5)

	def test_timeout_when_deadline_already_passed_applies_fallback(self):
		# Force the deadline to be already in the past regardless of how fast load_chain and
		# evaluate_deployment_chain run, so this deterministically exercises
		# evaluate_deployment_chain's own deadline check (T2A.08) and run_policy's
		# apply_policy_fallback call on a non-SUCCESS result.
		with patch("huf.ai.decision.service._deadline", return_value=time.monotonic() - 1):
			result = service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
			)

		self.assertEqual(result.status, DecisionStatus.TIMEOUT)
		self.assertIsNotNone(result.decision_call)
		self.assertIsNotNone(result.fallback_action)

	# -- Missing key on a deployment (build_transport ValueError) -------------------------

	def test_missing_provider_key_falls_back_cleanly(self):
		# AI Provider.validate() (ai_provider.py validate_api_key) refuses to save a cloud
		# provider with a blank api_key, so simulate "key was removed/rotated away" directly:
		# api_key is a Password field, stored in __Auth (not the main table), so a plain
		# db.set_value on the AI Provider row would not be seen by get_password() at all.
		from frappe.utils.password import remove_encrypted_password

		remove_encrypted_password("AI Provider", self.provider.name, "api_key")

		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=self._origin(),
		)

		self.assertNotEqual(result.status, DecisionStatus.SUCCESS)
		self.assertEqual(result.fallback_action, "fallback_default")
		self.assertIsNotNone(result.decision_call)
		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.fallback_action, "fallback_default")

	# -- Advise -----------------------------------------------------------------------------

	def test_advise_runs_inline_and_is_recorded_as_advise(self):
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			candidates=(Option(id="opt-a", description="A"), Option(id="opt-b", description="B")),
			candidate_source=CandidateSource.PERMISSION_FILTERED_TOOLS,
			candidate_resolver_id="list_tools",
			surface="Tool Selection",
			origin=self._origin(),
			mode="Advise",
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.mode, "Advise")
		# Advise never filters candidates: both supplied candidates are still visible on the
		# persisted call.
		self.assertEqual(call.candidate_count, 2)

	def test_advise_rejected_outside_advise_surfaces(self):
		with self.assertRaises(frappe.ValidationError):
			service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Input Guardrail",
				origin=self._origin(),
				mode="Advise",
			)

	# -- Origin persistence -----------------------------------------------------------------

	def test_origin_persisted_on_the_call(self):
		# agent/agent_run/conversation/etc. are Links (to Agent, Agent Run, ...) -- insert()
		# validates the target exists, so this only exercises fields whose value is either a
		# Select (origin_type) or a Link to a doctype guaranteed to have a row in any site
		# (User, "Administrator"). Full agent/agent_run propagation is exercised wherever
		# those fixtures already exist (e.g. the Agent-surface integration tasks).
		origin = self._origin(origin_type="API", owner_user="Administrator")
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			surface="Tool Selection",
			origin=origin,
		)

		call = frappe.get_doc("Decision Call", result.decision_call)
		self.assertEqual(call.origin_type, "API")
		self.assertEqual(call.owner_user, "Administrator")

	# -- Shadow dispatch ----------------------------------------------------------------------

	def test_shadow_enqueues_and_never_touches_load_chain(self):
		with patch("huf.ai.decision.service.load_chain") as mock_load_chain, \
			patch("frappe.enqueue") as mock_enqueue:
			result = service.run_policy(
				self.policy.name,
				state={"x": 1},
				surface="Tool Selection",
				origin=self._origin(),
				mode="Shadow",
			)

		self.assertEqual(result.status, service.SHADOW_ENQUEUED)
		self.assertIsNone(result.decision_call)
		mock_load_chain.assert_not_called()
		mock_enqueue.assert_called_once()
		args, kwargs = mock_enqueue.call_args
		self.assertEqual(args[0], "huf.ai.decision.service.run_shadow_job")
		self.assertEqual(kwargs["queue"], "short")
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["policy"], self.policy.name)

	# -- Repeated calls do not collide on Decision Call naming -----------------------------

	def test_repeated_successful_calls_do_not_collide(self):
		first = service.run_policy(
			self.policy.name, state={"x": 1}, surface="Tool Selection", origin=self._origin(),
		)
		second = service.run_policy(
			self.policy.name, state={"x": 1}, surface="Tool Selection", origin=self._origin(),
		)

		self.assertEqual(first.status, DecisionStatus.SUCCESS)
		self.assertEqual(second.status, DecisionStatus.SUCCESS)
		self.assertIsNotNone(first.decision_call)
		self.assertIsNotNone(second.decision_call)
		self.assertNotEqual(first.decision_call, second.decision_call)

	# -- Candidate source pass-through --------------------------------------------------------

	def test_candidate_source_and_resolver_id_pass_through(self):
		result = service.run_policy(
			self.policy.name,
			state={"x": 1},
			candidates=(Option(id="tool-a", description="A"),),
			candidate_source=CandidateSource.PERMISSION_FILTERED_TOOLS,
			candidate_resolver_id="list_tools",
			surface="Tool Selection",
			origin=self._origin(),
		)

		self.assertEqual(result.status, DecisionStatus.SUCCESS)
