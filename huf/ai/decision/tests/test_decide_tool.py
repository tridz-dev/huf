"""Unit tests for huf.ai.decision.decide_tool (T4.05, PLAN.md §3.6 "decide tool (D9)").

Frappe-free like test_agent_surfaces.py / test_flow_adapter.py: ``service.run_policy`` and
the module's own ``_policy_shape`` (which would otherwise load a real ``Decision Policy`` /
``Decision Policy Version`` doc) are monkeypatched at their ``decide_tool`` module
reference, so no real site, policy row or backend call is ever touched.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.decision import decide_tool, service
from huf.ai.decision.decide_tool import (
	_PolicyShape,
	decide_tool_enabled,
	get_agent_tool_bindings,
	has_agent_tool_binding,
	run_decide,
)
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

SURFACE = "Agent Tool"


def make_binding(*, surface=SURFACE, policy="triage", mode="Enforce", enabled=True, priority=100, latency_budget_ms=None):
	return SimpleNamespace(
		surface=surface,
		policy=policy,
		mode=mode,
		enabled=enabled,
		priority=priority,
		latency_budget_ms=latency_budget_ms,
	)


def make_agent(bindings):
	return SimpleNamespace(name="AGT-1", decision_bindings=list(bindings))


def make_origin():
	return DecisionOrigin(origin_type="Agent Run", agent="AGT-1", agent_run="AR-1")


def make_success(value="approve", confidence=0.8, question_id="pick"):
	return DecisionResponse(
		status=DecisionStatus.SUCCESS,
		answers={question_id: DecisionAnswer(question_id, QuestionKind.JUDGE if isinstance(value, float) else QuestionKind.SELECT, value, confidence=confidence)},
	)


FIXED_SHAPE = _PolicyShape(takes_candidates=False, max_candidates=0)
CANDIDATE_SHAPE = _PolicyShape(takes_candidates=True, max_candidates=2)


class TestGetAgentToolBindings(unittest.TestCase):
	def test_off_binding_excluded(self):
		agent = make_agent([make_binding(mode="Off")])
		self.assertEqual(get_agent_tool_bindings(agent), {})
		self.assertFalse(has_agent_tool_binding(agent))

	def test_disabled_row_excluded(self):
		agent = make_agent([make_binding(enabled=False)])
		self.assertEqual(get_agent_tool_bindings(agent), {})

	def test_other_surface_excluded(self):
		agent = make_agent([make_binding(surface="Tool Selection")])
		self.assertEqual(get_agent_tool_bindings(agent), {})

	def test_advise_mode_downgraded_to_off_and_excluded(self):
		# "Agent Tool" is not in ADVISE_SURFACES; Advise here must behave exactly like Off
		# (this mirrors resolve_agent_decision_binding's own rule -- see module docstring).
		# Agent.validate (T1.22) rejects this at save time; this is the defensive runtime half.
		agent = make_agent([make_binding(mode="Advise")])
		self.assertEqual(get_agent_tool_bindings(agent), {})
		self.assertFalse(has_agent_tool_binding(agent))

	def test_enforce_and_shadow_both_included(self):
		agent = make_agent([make_binding(policy="p1", mode="Enforce"), make_binding(policy="p2", mode="Shadow")])
		bindings = get_agent_tool_bindings(agent)
		self.assertEqual(set(bindings), {"p1", "p2"})
		self.assertEqual(bindings["p1"].mode, "Enforce")
		self.assertEqual(bindings["p2"].mode, "Shadow")

	def test_duplicate_policy_lowest_priority_wins(self):
		agent = make_agent(
			[
				make_binding(policy="p1", priority=200, mode="Shadow"),
				make_binding(policy="p1", priority=50, mode="Enforce"),
			]
		)
		bindings = get_agent_tool_bindings(agent)
		self.assertEqual(bindings["p1"].mode, "Enforce")

	def test_no_policy_name_excluded(self):
		agent = make_agent([make_binding(policy=None)])
		self.assertEqual(get_agent_tool_bindings(agent), {})


class TestDecideToolEnabled(unittest.TestCase):
	def test_no_binding_disabled_regardless_of_kill_switch(self):
		agent = make_agent([])
		with patch.object(decide_tool, "kill_switch_enabled", return_value=True):
			self.assertFalse(decide_tool_enabled(agent))

	def test_kill_switch_off_disables_even_with_binding(self):
		agent = make_agent([make_binding()])
		with patch.object(decide_tool, "kill_switch_enabled", return_value=False):
			self.assertFalse(decide_tool_enabled(agent))

	def test_binding_and_kill_switch_on_enables(self):
		agent = make_agent([make_binding()])
		with patch.object(decide_tool, "kill_switch_enabled", return_value=True):
			self.assertTrue(decide_tool_enabled(agent))


class TestRunDecideUnbound(unittest.TestCase):
	def test_unbound_policy_is_error_with_no_service_call(self):
		agent = make_agent([make_binding(policy="bound-one")])
		with patch("huf.ai.decision.decide_tool.service.run_policy") as run_policy:
			result = run_decide(agent, policy="not-bound", state="x", candidates=None, origin=make_origin())
		run_policy.assert_not_called()
		self.assertEqual(result["status"], "error")
		self.assertIsNone(result["answer"])

	def test_no_bindings_at_all_is_error_with_no_service_call(self):
		agent = make_agent([])
		with patch("huf.ai.decision.decide_tool.service.run_policy") as run_policy:
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		run_policy.assert_not_called()
		self.assertEqual(result["status"], "error")


class TestRunDecideFixedOptions(unittest.TestCase):
	def test_candidates_ignored_and_empty_source_used(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		model_candidates = [{"id": "a"}, {"id": "b"}]
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=DecisionStatus.SUCCESS.value, response=make_success()),
			) as run_policy,
		):
			result = run_decide(agent, policy="triage", state="x", candidates=model_candidates, origin=make_origin())
		self.assertEqual(run_policy.call_args.kwargs["candidates"], ())
		self.assertIsNone(run_policy.call_args.kwargs["candidate_source"])
		self.assertEqual(result["status"], "success")


class TestRunDecideRuntimeCandidates(unittest.TestCase):
	def test_empty_candidates_is_error_with_no_service_call(self):
		agent = make_agent([make_binding(policy="pick", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=CANDIDATE_SHAPE),
			patch("huf.ai.decision.decide_tool.service.run_policy") as run_policy,
		):
			result = run_decide(agent, policy="pick", state="x", candidates=None, origin=make_origin())
		run_policy.assert_not_called()
		self.assertEqual(result["status"], "error")

	def test_candidates_capped_by_max_candidates(self):
		agent = make_agent([make_binding(policy="pick", mode="Enforce")])
		model_candidates = [{"id": "a", "description": "A"}, {"id": "b"}, {"id": "c"}]
		with (
			patch.object(decide_tool, "_policy_shape", return_value=CANDIDATE_SHAPE),  # max_candidates=2
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=DecisionStatus.SUCCESS.value, response=make_success()),
			) as run_policy,
		):
			run_decide(agent, policy="pick", state="x", candidates=model_candidates, origin=make_origin())
		passed = run_policy.call_args.kwargs["candidates"]
		self.assertEqual(len(passed), 2)
		self.assertEqual(passed[0], Option("a", "A"))
		self.assertEqual(run_policy.call_args.kwargs["candidate_source"], CandidateSource.MODEL_SUPPLIED_CANDIDATES)

	def test_invalid_candidate_shape_is_error_with_no_service_call(self):
		agent = make_agent([make_binding(policy="pick", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=CANDIDATE_SHAPE),
			patch("huf.ai.decision.decide_tool.service.run_policy") as run_policy,
		):
			result = run_decide(agent, policy="pick", state="x", candidates=["not-a-dict"], origin=make_origin())
		run_policy.assert_not_called()
		self.assertEqual(result["status"], "error")


class TestRunDecideShadow(unittest.TestCase):
	def test_shadow_call_runs_but_model_never_sees_the_answer(self):
		agent = make_agent([make_binding(policy="triage", mode="Shadow")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=service.SHADOW_ENQUEUED),
			) as run_policy,
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		self.assertEqual(run_policy.call_args.kwargs["mode"], "Shadow")
		self.assertEqual(result, {"status": "shadow", "answer": None})


class TestRunDecideEnforceOutcomes(unittest.TestCase):
	def test_success_maps_answer_confidence_and_note(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=DecisionStatus.SUCCESS.value, response=make_success(value="approve", confidence=0.75)),
			),
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["answer"], "approve")
		self.assertEqual(result["confidence"], 0.75)
		self.assertIn("advisory", result["note"].lower())

	def test_disabled_status_maps_to_unavailable(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=service.DISABLED),
			),
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		self.assertEqual(result, {"status": "unavailable", "answer": None})

	def test_timeout_status_maps_to_unavailable(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		failure_response = DecisionResponse(status=DecisionStatus.TIMEOUT)
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=DecisionStatus.TIMEOUT.value, response=failure_response),
			),
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		self.assertEqual(result, {"status": "unavailable", "answer": None})

	def test_budget_exceeded_maps_to_unavailable(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", return_value=FIXED_SHAPE),
			patch(
				"huf.ai.decision.decide_tool.service.run_policy",
				return_value=ServiceResult(status=service.BUDGET_EXCEEDED),
			),
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		self.assertEqual(result, {"status": "unavailable", "answer": None})


class TestPolicyShapeReadFailure(unittest.TestCase):
	def test_policy_shape_error_is_error_result_with_no_service_call(self):
		agent = make_agent([make_binding(policy="triage", mode="Enforce")])
		with (
			patch.object(decide_tool, "_policy_shape", side_effect=ValueError("no published version")),
			patch("huf.ai.decision.decide_tool.service.run_policy") as run_policy,
		):
			result = run_decide(agent, policy="triage", state="x", candidates=None, origin=make_origin())
		run_policy.assert_not_called()
		self.assertEqual(result["status"], "error")


if __name__ == "__main__":
	unittest.main()
