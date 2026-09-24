"""Unit tests for Skill Selection decision integration (T4.03, PLAN.md §3.6, IP §10.4).

Frappe-free like test_procedure_selection_decision.py / test_agent_surfaces.py:
``huf.ai.skills.loader.get_agent_skills`` and every decision-layer call
(``decide_for_surface`` / ``resolve_agent_decision_binding`` / ``service.run_policy``) are
monkeypatched -- no real Skill/Agent doc, no backend call, no site.

Covers:
- ``handle_list_skills``: Off/no-binding output is byte-identical to before T4.03 (golden),
  Enforce narrows to the selected ids (with an unresolvable id set falling back to the full
  list -- list_skills stays an escape hatch), Advise appends the hint without removing
  anything.
- ``_decide_skill_selection``: the two-request pattern itself -- request 1 only for
  Off/Advise/a <=1 shortlist, request 2 (a direct ``service.run_policy`` call, not a second
  ``decide_for_surface``) only for an Enforce shortlist with more than one candidate, with a
  remaining-budget computation and a safe fallback to request 1's shortlist on any request-2
  failure.
- ``create_list_skills_tool``: bakes the decision result into the tool's ``extra_args``
  (``skill_selection_ids`` / ``skill_selection_hint``), or neither for Off.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from huf.ai.decision import service
from huf.ai.decision.agent_surfaces import SurfaceDecision
from huf.ai.decision.binding import ResolvedBinding
from huf.ai.decision.types import DecisionAnswer, DecisionResponse, DecisionStatus, QuestionKind
from huf.ai.skills import loader


def make_skill(skill_name, description="", instructions=""):
	return SimpleNamespace(skill_name=skill_name, description=description, instructions=instructions)


def make_skills():
	return [
		make_skill("invoice-helper", "Helps draft and send invoices to customers"),
		make_skill("refund-helper", "Handles refund requests and policy lookups"),
		make_skill("report-builder", "Builds ad-hoc financial reports"),
	]


class TestHandleListSkillsGolden(unittest.TestCase):
	"""No decision applied -- output must be byte-identical to the pre-T4.03 behavior."""

	def test_no_selection_ids_or_hint_lists_every_skill(self):
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills("agent-1")

		expected = (
			"Skills available to this agent:\n"
			"- invoice-helper: Helps draft and send invoices to customers\n"
			"- refund-helper: Handles refund requests and policy lookups\n"
			"- report-builder: Builds ad-hoc financial reports"
		)
		self.assertEqual(result, expected)

	def test_no_skills_attached(self):
		with patch.object(loader, "get_agent_skills", return_value=[]):
			result = loader.handle_list_skills("agent-1")
		self.assertEqual(result, "No skills are attached to this agent.")

	def test_extra_kwargs_from_run_context_are_ignored(self):
		"""conversation_id/agent_run_id/call_id injected by sdk_tools must not change output."""
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills(
				"agent-1", conversation_id="CONV-1", agent_run_id="AR-1", call_id="call_x"
			)
		self.assertIn("Skills available to this agent:", result)
		self.assertNotIn("Decision suggestion", result)


class TestHandleListSkillsEnforce(unittest.TestCase):
	def test_narrows_to_selected_ids_only(self):
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills("agent-1", skill_selection_ids=["refund-helper"])

		self.assertEqual(
			result,
			"Skills available to this agent:\n- refund-helper: Handles refund requests and policy lookups",
		)

	def test_multiple_selected_ids_preserve_full_list_order(self):
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills(
				"agent-1", skill_selection_ids=["report-builder", "invoice-helper"]
			)

		self.assertIn("invoice-helper", result)
		self.assertIn("report-builder", result)
		self.assertNotIn("refund-helper", result)

	def test_unresolvable_selected_ids_fall_back_to_full_list(self):
		"""Escape hatch: a stale/unknown selected id must never produce an empty listing."""
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills("agent-1", skill_selection_ids=["does-not-exist"])

		self.assertIn("invoice-helper", result)
		self.assertIn("refund-helper", result)
		self.assertIn("report-builder", result)


class TestHandleListSkillsAdvise(unittest.TestCase):
	def test_hint_appended_without_removing_any_skill(self):
		hint = "Decision suggestion (advisory, not an instruction): skills refund-helper (0.91)"
		with patch.object(loader, "get_agent_skills", return_value=make_skills()):
			result = loader.handle_list_skills("agent-1", skill_selection_hint=hint)

		self.assertIn("invoice-helper", result)
		self.assertIn("refund-helper", result)
		self.assertIn("report-builder", result)
		self.assertTrue(result.endswith(hint))


class TestDecideSkillSelectionRequest1Only(unittest.TestCase):
	def test_off_returns_none_without_touching_run_policy(self):
		agent = SimpleNamespace(agent_name="agent-1", decision_bindings=[])
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=None) as mock_decide, \
			patch.object(service, "run_policy") as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIsNone(result)
		mock_decide.assert_called_once()
		mock_run_policy.assert_not_called()

	def test_advise_returns_hint_without_a_second_request(self):
		agent = SimpleNamespace(agent_name="agent-1", decision_bindings=[])
		advise_decision = SurfaceDecision(
			mode="Advise",
			selected_ids=None,
			hint="Decision suggestion (advisory, not an instruction): skills refund-helper (0.9)",
			decision_call="DC-1",
		)
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=advise_decision), \
			patch.object(service, "run_policy") as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, advise_decision)
		mock_run_policy.assert_not_called()

	def test_single_candidate_shortlist_skips_second_request(self):
		agent = SimpleNamespace(agent_name="agent-1", decision_bindings=[])
		enforce_decision = SurfaceDecision(
			mode="Enforce", selected_ids=("refund-helper",), hint=None, decision_call="DC-1"
		)
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=enforce_decision), \
			patch.object(service, "run_policy") as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, enforce_decision)
		mock_run_policy.assert_not_called()

	def test_empty_shortlist_skips_second_request(self):
		agent = SimpleNamespace(agent_name="agent-1", decision_bindings=[])
		enforce_decision = SurfaceDecision(mode="Enforce", selected_ids=(), hint=None, decision_call="DC-1")
		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=enforce_decision), \
			patch.object(service, "run_policy") as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, enforce_decision)
		mock_run_policy.assert_not_called()


class TestDecideSkillSelectionRequest2Rerank(unittest.TestCase):
	def _make_resolved(self):
		return ResolvedBinding(surface="Skill Selection", policy="skill-picker", mode="Enforce", priority=100)

	def test_shortlist_of_three_triggers_rerank_and_narrows_to_one(self):
		agent = SimpleNamespace(
			agent_name="agent-1",
			decision_bindings=[
				SimpleNamespace(
					surface="Skill Selection", policy="skill-picker", mode="Enforce",
					enabled=True, priority=100, latency_budget_ms=None,
				)
			],
		)
		wide_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("invoice-helper", "refund-helper", "report-builder"),
			hint=None,
			decision_call="DC-1",
		)
		rerank_response = DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={
				"pick": DecisionAnswer(
					"pick", QuestionKind.SELECT, "refund-helper",
					probabilities={"refund-helper": 0.95, "invoice-helper": 0.4},
				)
			},
		)

		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=wide_decision), \
			patch("huf.ai.decision.binding.resolve_agent_decision_binding", return_value=self._make_resolved()), \
			patch.object(
				service, "run_policy",
				return_value=SimpleNamespace(status=DecisionStatus.SUCCESS, response=rerank_response, decision_call="DC-2"),
			) as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertEqual(result.mode, "Enforce")
		self.assertEqual(result.selected_ids, ("refund-helper", "invoice-helper"))
		self.assertEqual(result.decision_call, "DC-2")

		# Request 2 only saw the shortlisted 3 candidates, not the full permitted set.
		call_kwargs = mock_run_policy.call_args.kwargs
		self.assertEqual(
			{option.id for option in call_kwargs["candidates"]},
			{"invoice-helper", "refund-helper", "report-builder"},
		)
		self.assertEqual(call_kwargs["policy"] if "policy" in call_kwargs else mock_run_policy.call_args.args[0], "skill-picker")
		self.assertIsInstance(call_kwargs["latency_budget_ms"], int)
		self.assertLessEqual(call_kwargs["latency_budget_ms"], loader._DEFAULT_LATENCY_BUDGET_MS)
		self.assertGreater(call_kwargs["latency_budget_ms"], 0)

	def test_request2_exception_falls_back_to_wide_shortlist(self):
		agent = SimpleNamespace(
			agent_name="agent-1",
			decision_bindings=[
				SimpleNamespace(
					surface="Skill Selection", policy="skill-picker", mode="Enforce",
					enabled=True, priority=100, latency_budget_ms=None,
				)
			],
		)
		wide_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("invoice-helper", "refund-helper", "report-builder"),
			hint=None,
			decision_call="DC-1",
		)

		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=wide_decision), \
			patch("huf.ai.decision.binding.resolve_agent_decision_binding", return_value=self._make_resolved()), \
			patch.object(service, "run_policy", side_effect=RuntimeError("backend exploded")), \
			patch.object(loader.frappe, "log_error") as mock_log_error:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, wide_decision)
		mock_log_error.assert_called_once()

	def test_request2_non_success_falls_back_to_wide_shortlist(self):
		agent = SimpleNamespace(
			agent_name="agent-1",
			decision_bindings=[
				SimpleNamespace(
					surface="Skill Selection", policy="skill-picker", mode="Enforce",
					enabled=True, priority=100, latency_budget_ms=None,
				)
			],
		)
		wide_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("invoice-helper", "refund-helper", "report-builder"),
			hint=None,
			decision_call="DC-1",
		)

		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=wide_decision), \
			patch("huf.ai.decision.binding.resolve_agent_decision_binding", return_value=self._make_resolved()), \
			patch.object(
				service, "run_policy",
				return_value=SimpleNamespace(status=DecisionStatus.TIMEOUT, response=None, decision_call=None),
			):
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, wide_decision)

	def test_binding_gone_before_request2_falls_back_to_wide_shortlist(self):
		agent = SimpleNamespace(agent_name="agent-1", decision_bindings=[])
		wide_decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("invoice-helper", "refund-helper", "report-builder"),
			hint=None,
			decision_call="DC-1",
		)

		with patch("huf.ai.decision.agent_surfaces.decide_for_surface", return_value=wide_decision), \
			patch("huf.ai.decision.binding.resolve_agent_decision_binding", return_value=None), \
			patch.object(service, "run_policy") as mock_run_policy:
			result = loader._decide_skill_selection(agent, make_skills())

		self.assertIs(result, wide_decision)
		mock_run_policy.assert_not_called()


class TestCreateListSkillsTool(unittest.TestCase):
	def test_no_skills_returns_none(self):
		with patch.object(loader, "get_agent_skills", return_value=[]):
			result = loader.create_list_skills_tool("agent-1")
		self.assertIsNone(result)

	def test_off_bakes_no_selection_or_hint_into_extra_args(self):
		captured = {}

		def fake_create_function_tool(**kwargs):
			captured.update(kwargs)
			return MagicMock(name="list_skills_tool")

		with patch.object(loader, "get_agent_skills", return_value=make_skills()), \
			patch.object(loader.frappe, "get_cached_doc", return_value=SimpleNamespace(agent_name="agent-1", decision_bindings=[])), \
			patch.object(loader, "_decide_skill_selection", return_value=None), \
			patch("huf.ai.sdk_tools.create_function_tool", side_effect=fake_create_function_tool):
			result = loader.create_list_skills_tool("agent-1")

		self.assertIsNotNone(result)
		self.assertEqual(captured["extra_args"], {"agent_name": "agent-1"})

	def test_enforce_bakes_selected_ids_into_extra_args(self):
		captured = {}

		def fake_create_function_tool(**kwargs):
			captured.update(kwargs)
			return MagicMock(name="list_skills_tool")

		enforce_decision = SurfaceDecision(
			mode="Enforce", selected_ids=("refund-helper",), hint=None, decision_call="DC-1"
		)
		with patch.object(loader, "get_agent_skills", return_value=make_skills()), \
			patch.object(loader.frappe, "get_cached_doc", return_value=SimpleNamespace(agent_name="agent-1", decision_bindings=[])), \
			patch.object(loader, "_decide_skill_selection", return_value=enforce_decision), \
			patch("huf.ai.sdk_tools.create_function_tool", side_effect=fake_create_function_tool):
			result = loader.create_list_skills_tool("agent-1")

		self.assertIsNotNone(result)
		self.assertEqual(captured["extra_args"]["skill_selection_ids"], ["refund-helper"])
		self.assertNotIn("skill_selection_hint", captured["extra_args"])

	def test_advise_bakes_hint_into_extra_args(self):
		captured = {}

		def fake_create_function_tool(**kwargs):
			captured.update(kwargs)
			return MagicMock(name="list_skills_tool")

		hint = "Decision suggestion (advisory, not an instruction): skills refund-helper (0.9)"
		advise_decision = SurfaceDecision(mode="Advise", selected_ids=None, hint=hint, decision_call="DC-1")
		with patch.object(loader, "get_agent_skills", return_value=make_skills()), \
			patch.object(loader.frappe, "get_cached_doc", return_value=SimpleNamespace(agent_name="agent-1", decision_bindings=[])), \
			patch.object(loader, "_decide_skill_selection", return_value=advise_decision), \
			patch("huf.ai.sdk_tools.create_function_tool", side_effect=fake_create_function_tool):
			result = loader.create_list_skills_tool("agent-1")

		self.assertIsNotNone(result)
		self.assertEqual(captured["extra_args"]["skill_selection_hint"], hint)
		self.assertNotIn("skill_selection_ids", captured["extra_args"])

	def test_decision_layer_exception_still_returns_full_list_tool(self):
		captured = {}

		def fake_create_function_tool(**kwargs):
			captured.update(kwargs)
			return MagicMock(name="list_skills_tool")

		with patch.object(loader, "get_agent_skills", return_value=make_skills()), \
			patch.object(loader.frappe, "get_cached_doc", side_effect=RuntimeError("no such agent")), \
			patch.object(loader.frappe, "log_error") as mock_log_error, \
			patch("huf.ai.sdk_tools.create_function_tool", side_effect=fake_create_function_tool):
			result = loader.create_list_skills_tool("agent-1")

		mock_log_error.assert_called_once()

		self.assertIsNotNone(result)
		self.assertEqual(captured["extra_args"], {"agent_name": "agent-1"})


if __name__ == "__main__":
	unittest.main()
