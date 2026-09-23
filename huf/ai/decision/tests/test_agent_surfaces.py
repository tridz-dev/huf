"""Unit tests for huf.ai.decision.agent_surfaces (T4.01, PLAN.md §3.6, D6/D14/D18, I-DR1).

Frappe-free like test_flow_adapter.py: service.run_policy is monkeypatched (no real Decision
Policy row, no backend call, no site). ``agent_surfaces`` calls ``service.run_policy`` through
its own module-level ``service`` reference, so every test patches
``huf.ai.decision.agent_surfaces.service.run_policy``.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from huf.ai.decision import agent_surfaces, service
from huf.ai.decision.agent_surfaces import SurfaceDecision, decide_for_surface
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

SURFACE = "Tool Selection"


def make_agent(*, mode="Enforce", policy="pick-tool", surface=SURFACE, latency_budget_ms=None, enabled=True):
	binding = SimpleNamespace(
		surface=surface,
		policy=policy,
		mode=mode,
		priority=100,
		enabled=enabled,
		latency_budget_ms=latency_budget_ms,
	)
	return SimpleNamespace(decision_bindings=[binding])


def make_origin():
	return DecisionOrigin(origin_type="Agent Run", agent_run="AR-1")


def make_candidates():
	return (Option("create_invoice", "Create an invoice"), Option("lookup_customer", "Look up a customer"))


def make_success(probabilities=None, value=None, kind=QuestionKind.SELECT, confidence=None):
	return DecisionResponse(
		status=DecisionStatus.SUCCESS,
		answers={
			"pick": DecisionAnswer(
				"pick",
				kind,
				value if value is not None else "create_invoice",
				probabilities=probabilities,
				confidence=confidence,
			)
		},
	)


class TestOffAndMissingBinding(unittest.TestCase):
	def test_off_binding_returns_none_without_calling_run_policy(self):
		agent = make_agent(mode="Off")
		with patch("huf.ai.decision.agent_surfaces.service.run_policy") as run_policy:
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)
		run_policy.assert_not_called()

	def test_no_binding_for_surface_returns_none(self):
		agent = make_agent(surface="Skill Selection")
		with patch("huf.ai.decision.agent_surfaces.service.run_policy") as run_policy:
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)
		run_policy.assert_not_called()

	def test_disabled_binding_row_returns_none(self):
		agent = make_agent(enabled=False)
		with patch("huf.ai.decision.agent_surfaces.service.run_policy") as run_policy:
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)
		run_policy.assert_not_called()


class TestShadowMode(unittest.TestCase):
	def test_shadow_enqueues_and_returns_none(self):
		agent = make_agent(mode="Shadow")
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=service.SHADOW_ENQUEUED),
		) as run_policy:
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)
		self.assertEqual(run_policy.call_args.kwargs["mode"], "Shadow")


class TestKillSwitchAndFailureModes(unittest.TestCase):
	def test_disabled_service_result_returns_none(self):
		agent = make_agent()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=service.DISABLED),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)

	def test_budget_exceeded_returns_none(self):
		agent = make_agent()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=service.BUDGET_EXCEEDED),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)

	def test_timeout_status_returns_none(self):
		agent = make_agent()
		response = DecisionResponse(status=DecisionStatus.TIMEOUT)
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.TIMEOUT, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)

	def test_throughput_exhausted_returns_none(self):
		agent = make_agent()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.THROUGHPUT_BUDGET_EXHAUSTED),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)

	def test_exception_from_run_policy_is_swallowed_and_logged(self):
		agent = make_agent()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			side_effect=ValueError("boom"),
		), patch.object(agent_surfaces.frappe, "log_error", create=True) as log_error:
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)
		log_error.assert_called_once()

	def test_exception_is_logged_at_most_once_per_throttle_window(self):
		agent = make_agent()
		agent_surfaces._last_logged_at.clear()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			side_effect=ValueError("boom"),
		), patch.object(agent_surfaces.frappe, "log_error", create=True) as log_error:
			decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
			decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(log_error.call_count, 1)

	def test_resolve_agent_decision_binding_exception_returns_none(self):
		with patch(
			"huf.ai.decision.agent_surfaces.resolve_agent_decision_binding",
			side_effect=RuntimeError("bad agent doc"),
		), patch.object(agent_surfaces.frappe, "log_error", create=True):
			result = decide_for_surface(object(), SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(result)


class TestAdviseMode(unittest.TestCase):
	def test_advise_returns_hint_and_never_narrows(self):
		agent = make_agent(mode="Advise", policy="advise-tool")
		response = make_success(probabilities={"create_invoice": 0.86, "lookup_customer": 0.71})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			result = decide_for_surface(
				agent, SURFACE, make_candidates(), {}, make_origin(), hint_kind="tools"
			)
		self.assertIsInstance(result, SurfaceDecision)
		self.assertEqual(result.mode, "Advise")
		self.assertIsNone(result.selected_ids)
		self.assertIn("create_invoice (0.86)", result.hint)
		self.assertIn("tools", result.hint)
		self.assertEqual(run_policy.call_args.kwargs["mode"], "Advise")

	def test_advise_with_no_scoreable_answer_returns_none_hint(self):
		agent = make_agent(mode="Advise", policy="advise-tool")
		response = DecisionResponse(status=DecisionStatus.SUCCESS, answers={})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsInstance(result, SurfaceDecision)
		self.assertIsNone(result.hint)
		self.assertIsNone(result.selected_ids)


class TestEnforceMode(unittest.TestCase):
	def test_enforce_filters_and_orders_by_score(self):
		agent = make_agent(mode="Enforce")
		response = make_success(probabilities={"lookup_customer": 0.4, "create_invoice": 0.9})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(result.mode, "Enforce")
		self.assertIsNone(result.hint)
		self.assertEqual(result.selected_ids, ("create_invoice", "lookup_customer"))

	def test_enforce_subset_guarantee_drops_unknown_ids(self):
		agent = make_agent(mode="Enforce")
		# Backend returns one real candidate plus an id that was never in the input set.
		response = make_success(probabilities={"create_invoice": 0.9, "ghost_tool": 0.99})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(result.selected_ids, ("create_invoice",))
		self.assertTrue(set(result.selected_ids) <= {c.id for c in make_candidates()})

	def test_enforce_select_answer_narrows_to_one(self):
		agent = make_agent(mode="Enforce")
		response = make_success(value="lookup_customer", kind=QuestionKind.SELECT)
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(result.selected_ids, ("lookup_customer",))

	def test_enforce_select_answer_outside_candidates_yields_empty_subset(self):
		agent = make_agent(mode="Enforce")
		response = make_success(value="not_a_real_tool", kind=QuestionKind.SELECT)
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(result.selected_ids, ())

	def test_enforce_respects_top_n(self):
		agent = make_agent(mode="Enforce")
		response = make_success(probabilities={"lookup_customer": 0.4, "create_invoice": 0.9})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin(), top_n=1)
		self.assertEqual(result.selected_ids, ("create_invoice",))


class TestCallShape(unittest.TestCase):
	def test_passes_surface_origin_mode_policy_and_candidate_provenance(self):
		agent = make_agent(mode="Enforce", policy="pick-tool")
		response = make_success(probabilities={"create_invoice": 0.9})
		origin = make_origin()
		candidates = make_candidates()
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			decide_for_surface(
				agent,
				SURFACE,
				candidates,
				{"foo": "bar"},
				origin,
				candidate_source=CandidateSource.PERMISSION_FILTERED_TOOLS,
				candidate_resolver_id="tools.eligibility",
			)
		call_args, call_kwargs = run_policy.call_args
		self.assertEqual(call_args[0], "pick-tool")
		self.assertEqual(call_kwargs["surface"], SURFACE)
		self.assertIs(call_kwargs["origin"], origin)
		self.assertEqual(call_kwargs["mode"], "Enforce")
		self.assertEqual(call_kwargs["candidates"], candidates)
		self.assertEqual(call_kwargs["candidate_source"], CandidateSource.PERMISSION_FILTERED_TOOLS)
		self.assertEqual(call_kwargs["candidate_resolver_id"], "tools.eligibility")
		self.assertEqual(call_kwargs["state"], {"foo": "bar"})

	def test_binding_latency_budget_override_is_passed_through(self):
		agent = make_agent(mode="Enforce", latency_budget_ms=750)
		response = make_success(probabilities={"create_invoice": 0.9})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertEqual(run_policy.call_args.kwargs["latency_budget_ms"], 750)

	def test_no_latency_override_passes_none_for_surface_default(self):
		agent = make_agent(mode="Enforce", latency_budget_ms=None)
		response = make_success(probabilities={"create_invoice": 0.9})
		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			decide_for_surface(agent, SURFACE, make_candidates(), {}, make_origin())
		self.assertIsNone(run_policy.call_args.kwargs["latency_budget_ms"])


if __name__ == "__main__":
	unittest.main()
