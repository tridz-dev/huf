# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""
Tests for T8.04 Context Relevance compaction (PLAN.md §3.6 "Context Relevance" row, D6, D9,
D14, D18, I-DR1):

- ``huf.ai.conversation_manager.get_tool_exchange_candidates`` -- describes every completed
  tool-call group in a history, marking status/error/pending-approval/recency/shared-turn.
- ``huf.ai.decision.context_relevance.compact_context`` -- the surface itself: applies the hard
  I-DR1 eligibility constraints *before* anything is ever offered to a decision backend, then
  (Enforce only) drops the subset the backend marks confidently irrelevant.

These are Layer B (real-Frappe) tests because ``get_tool_exchange_candidates`` reads ``Agent
Tool Call`` rows and ``compact_context``'s error path calls ``frappe.log_error`` -- both need a
site context -- but no Agent/Decision Policy DocTypes are created: ``compact_context`` only
needs an ``agent_doc`` exposing ``.decision_bindings`` (duck-typed, see
``huf.ai.decision.binding.resolve_agent_decision_binding``), and every backend call is
monkeypatched at ``huf.ai.decision.service.run_policy`` -- no network, no real Decision
Policy/Deployment.

Run:
    bench --site dr-activation.local run-tests --app huf --module huf.ai.tests.test_context_relevance_decision
"""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.conversation_manager import get_tool_exchange_candidates
from huf.ai.decision import context_relevance, service
from huf.ai.decision.types import (
	DecisionAnswer,
	DecisionOrigin,
	DecisionResponse,
	DecisionStatus,
	QuestionKind,
	ServiceResult,
)

PREFIX = "_Test ContextRelevanceDecision"


def _origin():
	return DecisionOrigin(origin_type="Agent Run", agent="test-agent", agent_run="RUN-1", conversation="CONV-1")


def _agent_doc(mode="Enforce", policy="_Test CR Policy"):
	"""Minimal duck-typed agent_doc: resolve_agent_decision_binding only reads
	``.decision_bindings`` (list of objects exposing enabled/surface/mode/policy/priority)."""
	binding = SimpleNamespace(enabled=1, surface="Context Relevance", mode=mode, policy=policy, priority=100)
	return SimpleNamespace(decision_bindings=[binding])


def _off_agent_doc():
	return SimpleNamespace(decision_bindings=[])


def _exchange(id, *, status="Completed", has_error=False, pending_approval=False, is_recent=False, shared_turn=False, summary=""):
	return {
		"id": id,
		"tool_name": "some_tool",
		"summary": summary or f"summary-{id}",
		"status": status,
		"has_error": has_error,
		"pending_approval": pending_approval,
		"is_recent": is_recent,
		"shared_turn": shared_turn,
		"start": 0,
		"end": 1,
	}


def _drop_response(dropped_ids, confidence=0.9):
	"""A DecisionResponse whose single 'select' answer marks ``dropped_ids`` irrelevant."""
	answer = DecisionAnswer(question_id="irrelevant", kind=QuestionKind.SELECT, value="", probabilities={i: confidence for i in dropped_ids})
	return DecisionResponse(status=DecisionStatus.SUCCESS, answers={"irrelevant": answer})


class TestCompactContextEligibilityAndCandidates(IntegrationTestCase):
	"""Hard I-DR1 constraints: protected exchanges must never even become candidates handed to
	the decision backend -- asserted on the mocked call's own kwargs, not just the final output.
	"""

	def test_recent_error_and_approval_exchanges_never_become_candidates(self):
		exchanges = [
			_exchange("recent-1", is_recent=True),
			_exchange("errored-1", has_error=True),
			_exchange("failed-status-1", status="Failed"),
			_exchange("pending-approval-1", pending_approval=True),
			_exchange("shared-turn-1", shared_turn=True),
			_exchange("unknown-status-1", status=""),
			_exchange("old-completed-1"),
		]
		captured = {}

		def fake_run_policy(*args, **kwargs):
			captured["candidates"] = kwargs.get("candidates")
			captured["candidate_source"] = kwargs.get("candidate_source")
			return ServiceResult(status=DecisionStatus.SUCCESS, response=_drop_response([]), decision_call=None)

		with patch("huf.ai.decision.service.run_policy", side_effect=fake_run_policy):
			kept_ids, _ = context_relevance.compact_context(_agent_doc(), exchanges, _origin())

		candidate_ids = {option.id for option in captured["candidates"]}
		self.assertEqual(candidate_ids, {"old-completed-1"})
		# Nothing was dropped (fake backend marked nothing irrelevant), so every input id
		# survives -- protection is about never *offering* the protected ones, not just never
		# dropping them.
		self.assertEqual(set(kept_ids), {e["id"] for e in exchanges})

	def test_protected_records_never_dropped_even_when_backend_marks_them_irrelevant(self):
		"""A misbehaving/compromised backend naming a protected id as irrelevant must be a
		no-op: protected ids are never in eligible_ids, so compact_context ignores them (I-DR1)
		even if a hallucinated/malicious response names them."""
		exchanges = [
			_exchange("recent-1", is_recent=True),
			_exchange("errored-1", has_error=True),
			_exchange("pending-approval-1", pending_approval=True),
			_exchange("old-completed-1"),
			_exchange("old-completed-2"),
		]

		def fake_run_policy(*args, **kwargs):
			# Backend tries to drop everything, including ids it was never offered.
			all_ids = [e["id"] for e in exchanges]
			return ServiceResult(status=DecisionStatus.SUCCESS, response=_drop_response(all_ids), decision_call="DC-1")

		with patch("huf.ai.decision.service.run_policy", side_effect=fake_run_policy):
			kept_ids, decision_call = context_relevance.compact_context(_agent_doc(), exchanges, _origin())

		self.assertIn("recent-1", kept_ids)
		self.assertIn("errored-1", kept_ids)
		self.assertIn("pending-approval-1", kept_ids)
		# Both eligible candidates were confidently marked irrelevant and were legitimately
		# offered, so they are the only ones allowed to be dropped.
		self.assertNotIn("old-completed-1", kept_ids)
		self.assertNotIn("old-completed-2", kept_ids)
		self.assertEqual(decision_call, "DC-1")

	def test_no_eligible_candidates_never_calls_backend(self):
		exchanges = [_exchange("recent-1", is_recent=True), _exchange("errored-1", has_error=True)]
		with patch("huf.ai.decision.service.run_policy") as run_policy:
			kept_ids, decision_call = context_relevance.compact_context(_agent_doc(), exchanges, _origin())
		run_policy.assert_not_called()
		self.assertEqual(set(kept_ids), {"recent-1", "errored-1"})
		self.assertIsNone(decision_call)


class TestCompactContextConfidenceGating(IntegrationTestCase):
	def test_only_confidently_irrelevant_candidates_are_dropped(self):
		exchanges = [_exchange("low-conf"), _exchange("high-conf"), _exchange("kept")]

		def fake_run_policy(*args, **kwargs):
			answer = DecisionAnswer(
				question_id="irrelevant",
				kind=QuestionKind.SELECT,
				value="",
				probabilities={"low-conf": 0.5, "high-conf": 0.95},
			)
			return ServiceResult(
				status=DecisionStatus.SUCCESS,
				response=DecisionResponse(status=DecisionStatus.SUCCESS, answers={"irrelevant": answer}),
				decision_call="DC-2",
			)

		with patch("huf.ai.decision.service.run_policy", side_effect=fake_run_policy):
			kept_ids, _ = context_relevance.compact_context(_agent_doc(), exchanges, _origin())

		# Below the minimum-confidence floor (_MIN_DROP_CONFIDENCE = 0.85): retained.
		self.assertIn("low-conf", kept_ids)
		# At/above the floor: dropped.
		self.assertNotIn("high-conf", kept_ids)
		self.assertIn("kept", kept_ids)

	def test_gate_result_not_accepted_retains_everything(self):
		exchanges = [_exchange("a"), _exchange("b")]

		def fake_run_policy(*args, **kwargs):
			response = DecisionResponse(status=DecisionStatus.SUCCESS, answers={}, gate_result="below_minimum_confidence")
			return ServiceResult(status=DecisionStatus.SUCCESS, response=response, decision_call="DC-3")

		with patch("huf.ai.decision.service.run_policy", side_effect=fake_run_policy):
			kept_ids, _ = context_relevance.compact_context(_agent_doc(), exchanges, _origin())
		self.assertEqual(set(kept_ids), {"a", "b"})


class TestCompactContextSafeDefaults(IntegrationTestCase):
	def test_backend_down_retains_all(self):
		exchanges = [_exchange("a"), _exchange("b")]
		with patch("huf.ai.decision.service.run_policy", side_effect=RuntimeError("backend down")):
			kept_ids, decision_call = context_relevance.compact_context(_agent_doc(), exchanges, _origin())
		self.assertEqual(set(kept_ids), {"a", "b"})
		self.assertIsNone(decision_call)

	def test_non_success_service_result_retains_all(self):
		exchanges = [_exchange("a"), _exchange("b")]
		with patch(
			"huf.ai.decision.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.TIMEOUT, response=None, decision_call="DC-4"),
		):
			kept_ids, decision_call = context_relevance.compact_context(_agent_doc(), exchanges, _origin())
		self.assertEqual(set(kept_ids), {"a", "b"})
		self.assertEqual(decision_call, "DC-4")

	def test_off_or_no_binding_retains_all_and_never_calls_backend(self):
		exchanges = [_exchange("a"), _exchange("b")]
		with patch("huf.ai.decision.service.run_policy") as run_policy:
			kept_ids, decision_call = context_relevance.compact_context(_off_agent_doc(), exchanges, _origin())
		run_policy.assert_not_called()
		self.assertEqual(set(kept_ids), {"a", "b"})
		self.assertIsNone(decision_call)

	def test_shadow_mode_never_compacts_but_still_calls_backend(self):
		exchanges = [_exchange("a"), _exchange("b")]

		def fake_run_policy(*args, **kwargs):
			self.assertEqual(kwargs.get("mode"), service.MODE_SHADOW)
			return ServiceResult(status=DecisionStatus.SUCCESS, response=_drop_response(["a", "b"]), decision_call="DC-5")

		with patch("huf.ai.decision.service.run_policy", side_effect=fake_run_policy) as run_policy:
			kept_ids, decision_call = context_relevance.compact_context(_agent_doc(mode="Shadow"), exchanges, _origin())
		run_policy.assert_called_once()
		# Shadow logs only -- output is unchanged even though the (mocked) backend would have
		# dropped everything.
		self.assertEqual(set(kept_ids), {"a", "b"})
		self.assertEqual(decision_call, "DC-5")


class TestGetToolExchangeCandidates(IntegrationTestCase):
	"""huf.ai.conversation_manager.get_tool_exchange_candidates: builds the raw per-exchange
	description compact_context's eligibility check reads. No Agent Tool Call rows exist for
	these synthetic call ids, so every exchange comes back status="" (never eligible) -- this
	suite only checks recency/shared-turn/pending-approval detection, which do not depend on
	the DB lookup.
	"""

	def _history(self, n_groups, *, shared_turn_at=None, approval_at=None):
		history = [{"role": "user", "content": "hi"}]
		for i in range(n_groups):
			call_id = f"call_{i}"
			tool_calls = [{"id": call_id, "type": "function", "function": {"name": "tool_a", "arguments": "{}"}}]
			if shared_turn_at == i:
				tool_calls.append({"id": f"call_{i}_b", "type": "function", "function": {"name": "tool_b", "arguments": "{}"}})
			history.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
			content = "approval_pending:some-approval" if approval_at == i else "ok"
			history.append({"role": "tool", "tool_call_id": call_id, "content": content})
			if shared_turn_at == i:
				history.append({"role": "tool", "tool_call_id": f"call_{i}_b", "content": "ok"})
		return history

	def test_recency_window_marks_only_last_two_groups_recent(self):
		history = self._history(4)
		candidates = get_tool_exchange_candidates("CONV-X", history)
		self.assertEqual(len(candidates), 4)
		recent_flags = [c["is_recent"] for c in candidates]
		# _RECENT_TOOL_EXCHANGES = 2: only the last two groups are recent.
		self.assertEqual(recent_flags, [False, False, True, True])

	def test_shared_turn_detected(self):
		# group 0 declares two tool calls in the same assistant message -> two candidates
		# (call_0, call_0_b), both marked shared_turn; group 1's single call is not.
		history = self._history(2, shared_turn_at=0)
		candidates = get_tool_exchange_candidates("CONV-X", history)
		self.assertEqual(len(candidates), 3)
		self.assertTrue(candidates[0]["shared_turn"])
		self.assertTrue(candidates[1]["shared_turn"])
		self.assertFalse(candidates[2]["shared_turn"])

	def test_pending_approval_detected(self):
		history = self._history(2, approval_at=0)
		candidates = get_tool_exchange_candidates("CONV-X", history)
		self.assertTrue(candidates[0]["pending_approval"])
		self.assertFalse(candidates[1]["pending_approval"])

	def test_empty_history_returns_empty_list(self):
		self.assertEqual(get_tool_exchange_candidates("CONV-X", []), [])
