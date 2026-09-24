"""Unit tests for huf.ai.decision.flow_adapter (T3.01, PLAN.md §3.11 point 4, D10).

Frappe-free like test_flow_router.py: service.run_policy is monkeypatched (no real Decision
Policy row, no backend call), and flow_adapter._current_published_version / commit_if_background
are patched for the version-pinning path so these tests never touch a real site.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from huf.ai.decision import flow_adapter, service
from huf.ai.decision.types import (
	CandidateSource,
	DecisionAnswer,
	DecisionOrigin,
	DecisionResponse,
	DecisionStatus,
	Option,
	QuestionKind,
	ServiceResult,
)


def make_flow_run(name="FR-1", context_json=None):
	flow_run = SimpleNamespace(name=name, context_json=context_json)
	flow_run.db_set = Mock(side_effect=lambda field, value: setattr(flow_run, field, value))
	return flow_run


def make_response(value="branch_a", confidence=0.9, status=DecisionStatus.SUCCESS):
	return DecisionResponse(
		status=status,
		answers={"route": DecisionAnswer("route", QuestionKind.SELECT, value, confidence=confidence)},
	)


class TestMakeFlowDecisionRouter(unittest.TestCase):
	def setUp(self):
		self.flow_run = make_flow_run()
		self.node = {"id": "n1"}
		self.candidates = [
			{"to": "branch_a", "edge_id": "e1", "label": "Branch A"},
			{"to": "branch_b", "edge_id": "e2", "label": "Branch B"},
		]
		self.config = {"policy": "policy-1", "options": [], "default": "uncertain"}
		# make_flow_decision_router only needs a truthy flow_run + a version placeholder.
		self.router = flow_adapter.make_flow_decision_router(self.flow_run, SimpleNamespace(fingerprint="fp1"))
		get_value_patcher = patch("huf.ai.decision.flow_adapter._current_published_version", return_value="policy-1-v1")
		self.get_value = get_value_patcher.start()
		self.addCleanup(get_value_patcher.stop)
		commit_patcher = patch("huf.ai.decision.flow_adapter.commit_if_background")
		commit_patcher.start()
		self.addCleanup(commit_patcher.stop)

	def test_factory_requires_flow_run(self):
		with self.assertRaises(ValueError):
			flow_adapter.make_flow_decision_router(None, SimpleNamespace())

	# -- candidate provenance (I-DR1) ---------------------------------------------------------

	def test_candidates_come_from_outgoing_edges_not_config_alone(self):
		config = {
			"policy": "policy-1",
			# declares a third branch with no matching outgoing edge -- must not appear.
			"options": [
				{"label": "A", "node_id": "branch_a", "criteria": "when the user asks about billing"},
				{"label": "Ghost", "node_id": "branch_ghost"},
			],
		}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, config, {}, self.candidates)

		ids = [option.id for option in captured["candidates"]]
		self.assertEqual(ids, ["branch_a", "branch_b"])
		descriptions = {option.id: option.description for option in captured["candidates"]}
		self.assertEqual(descriptions["branch_a"], "when the user asks about billing")
		self.assertEqual(descriptions["branch_b"], "Branch B")  # falls back to the edge label

	def test_no_candidates_fails_without_calling_run_policy(self):
		with patch("huf.ai.decision.flow_adapter.service.run_policy") as mock_run_policy:
			result = self.router(self.flow_run, self.node, self.config, {}, [])
		mock_run_policy.assert_not_called()
		self.assertEqual(result.status, DecisionStatus.FAILED)
		self.assertEqual(result.error_code, "decision_router_no_candidates")

	def test_missing_policy_fails_without_calling_run_policy(self):
		with patch("huf.ai.decision.flow_adapter.service.run_policy") as mock_run_policy:
			result = self.router(self.flow_run, self.node, {"options": []}, {}, self.candidates)
		mock_run_policy.assert_not_called()
		self.assertEqual(result.status, DecisionStatus.FAILED)
		self.assertEqual(result.error_code, "decision_router_no_policy")

	# -- call shape: surface / origin / mode / candidate_source ------------------------------

	def test_calls_run_policy_with_flow_surface_and_origin(self):
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured["policy"] = policy
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, self.config, {}, self.candidates)

		self.assertEqual(captured["policy"], "policy-1")
		self.assertEqual(captured["surface"], "Flow Decision Router")
		self.assertEqual(captured["mode"], service.MODE_ENFORCE)
		self.assertEqual(captured["candidate_source"], CandidateSource.POLICY_OPTIONS)
		origin = captured["origin"]
		self.assertIsInstance(origin, DecisionOrigin)
		self.assertEqual(origin.origin_type, "Flow")
		self.assertEqual(origin.flow_run, "FR-1")
		self.assertEqual(origin.flow_node_id, "n1")

	def test_success_returns_the_service_response_unchanged(self):
		response = make_response("branch_b")
		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = self.router(self.flow_run, self.node, self.config, {}, self.candidates)
		self.assertIs(result, response)

	def test_disabled_service_result_becomes_a_failed_response(self):
		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=service.DISABLED),
		):
			result = self.router(self.flow_run, self.node, self.config, {}, self.candidates)
		self.assertEqual(result.status, DecisionStatus.FAILED)
		self.assertEqual(result.error_code, "decision_runtime_disabled")

	def test_shadow_enqueued_service_result_becomes_a_failed_response(self):
		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			return_value=ServiceResult(status=service.SHADOW_ENQUEUED),
		):
			result = self.router(self.flow_run, self.node, self.config, {}, self.candidates)
		self.assertEqual(result.status, DecisionStatus.FAILED)
		self.assertEqual(result.error_code, "decision_router_shadow_mode")

	def test_run_policy_value_error_becomes_a_failed_response(self):
		with patch(
			"huf.ai.decision.flow_adapter.service.run_policy",
			side_effect=ValueError("Decision Policy 'policy-1' has no default_model and none was given"),
		):
			result = self.router(self.flow_run, self.node, self.config, {}, self.candidates)
		self.assertEqual(result.status, DecisionStatus.FAILED)
		self.assertIn("no default_model", result.error_code)

	# -- state from state_bindings ------------------------------------------------------------

	def test_state_built_from_state_bindings(self):
		config = dict(self.config, state_bindings=[{"name": "ticket", "path": "input.ticket.subject"}])
		ctx_dict = {"input": {"ticket": {"subject": "Refund request"}}}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, config, ctx_dict, self.candidates)

		self.assertEqual(captured["state"], {"ticket": "Refund request"})

	def test_state_binding_dollar_projects_whole_context(self):
		config = dict(self.config, state_bindings=[{"name": "all", "path": "$"}])
		ctx_dict = {"a": 1}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, config, ctx_dict, self.candidates)

		self.assertEqual(captured["state"], {"all": {"a": 1}})

	def test_state_defaults_to_whole_context_without_bindings(self):
		ctx_dict = {"foo": "bar"}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		# The whole context, minus the PIN_CONTEXT_KEY bookkeeping _pinned_version added to
		# ctx_dict itself as a side effect -- that key must never leak into provider-visible state.
		self.assertEqual(captured["state"], {"foo": "bar"})
		self.assertIn(flow_adapter.PIN_CONTEXT_KEY, ctx_dict)

	# -- policy version pinning (D10) ---------------------------------------------------------

	def test_pins_current_published_version_on_first_use(self):
		ctx_dict = {}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		self.get_value.assert_called_once_with("policy-1")
		self.assertEqual(captured["policy_version"], "policy-1-v1")
		self.assertEqual(ctx_dict[flow_adapter.PIN_CONTEXT_KEY]["n1"], {"policy": "policy-1", "version": "policy-1-v1"})

	def test_pin_is_persisted_to_flow_run_context_json(self):
		ctx_dict = {}
		with patch("huf.ai.decision.flow_adapter.service.run_policy") as mock_run_policy:
			mock_run_policy.return_value = ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		self.flow_run.db_set.assert_called_once()
		field, value = self.flow_run.db_set.call_args[0]
		self.assertEqual(field, "context_json")
		self.assertEqual(json.loads(value)[flow_adapter.PIN_CONTEXT_KEY]["n1"]["version"], "policy-1-v1")

	def test_reuses_pinned_version_without_re_resolving(self):
		ctx_dict = {flow_adapter.PIN_CONTEXT_KEY: {"n1": {"policy": "policy-1", "version": "already-pinned-v0"}}}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		self.get_value.assert_not_called()
		self.flow_run.db_set.assert_not_called()
		self.assertEqual(captured["policy_version"], "already-pinned-v0")

	def test_paused_and_resumed_run_reuses_the_pin_across_a_new_closure(self):
		"""A resume calls _build_run_context again, building a brand new closure; the pin must
		still come from ctx_dict (persisted context), not from anything captured in the first
		closure's scope."""
		ctx_dict = {}
		with patch("huf.ai.decision.flow_adapter.service.run_policy") as mock_run_policy:
			mock_run_policy.return_value = ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		# Simulate resume: a fresh factory call, fresh closure, same persisted ctx_dict.
		resumed_router = flow_adapter.make_flow_decision_router(self.flow_run, SimpleNamespace(fingerprint="fp2"))
		self.get_value.reset_mock()
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			resumed_router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		self.get_value.assert_not_called()
		self.assertEqual(captured["policy_version"], "policy-1-v1")

	def test_no_published_version_leaves_pin_unresolved(self):
		self.get_value.return_value = None
		ctx_dict = {}
		captured = {}

		def fake_run_policy(policy, **kwargs):
			captured.update(kwargs)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=make_response())

		with patch("huf.ai.decision.flow_adapter.service.run_policy", side_effect=fake_run_policy):
			self.router(self.flow_run, self.node, self.config, ctx_dict, self.candidates)

		self.assertIsNone(captured["policy_version"])
		self.flow_run.db_set.assert_not_called()
		self.assertNotIn(flow_adapter.PIN_CONTEXT_KEY, ctx_dict)


if __name__ == "__main__":
	unittest.main()
