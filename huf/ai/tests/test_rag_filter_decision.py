"""Unit tests for RAG Filter decision binding (T8.02, PLAN.md §3.8, D8/D18, I-DR1).

Tests that:
1. RAG Filter binding narrows authorized retrieval results (Enforce mode).
2. In Advise mode, all passages are kept and annotated with relevance scores.
3. The result set is always a subset of the input (I-DR1 guarantee).
4. When backend is down or no binding, all results are kept (golden test).
5. The decision integrates with context_builder to filter passages.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from collections import namedtuple

from huf.ai.decision import agent_surfaces
from huf.ai.decision.agent_surfaces import SurfaceDecision, decide_for_surface
from huf.ai.decision.rag import retain_selected_context, apply_rag_filter_decision
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


# Chunk-like object (mimics knowledge search result)
ChunkData = namedtuple("ChunkData", ["id", "chunk_id", "title", "text", "score", "source"])


def make_agent(*, mode="Enforce", policy="filter-rag", surface="RAG Filter", enabled=True):
	"""Create a test agent with RAG Filter binding."""
	binding = SimpleNamespace(
		surface=surface,
		policy=policy,
		mode=mode,
		priority=100,
		enabled=enabled,
		latency_budget_ms=None,
	)
	return SimpleNamespace(decision_bindings=[binding])


def make_origin():
	"""Create a test DecisionOrigin for Agent Run."""
	return DecisionOrigin(origin_type="Agent Run", agent_run="AR-1")


def make_chunks(count=3):
	"""Create test retrieval results (passages)."""
	chunks = []
	for i in range(count):
		chunks.append({
			"chunk_id": f"chunk-{i+1}",
			"title": f"Passage {i+1}",
			"text": f"This is passage {i+1}",
			"score": 0.9 - (i * 0.1),
			"source": "TestKB",
			"metadata": {"index": i},
		})
	return chunks


def make_chunk_objects(count=3):
	"""Create test chunk objects for decide_for_surface."""
	chunks = []
	for i in range(count):
		chunks.append(ChunkData(
			id=f"chunk-{i+1}",
			chunk_id=f"chunk-{i+1}",
			title=f"Passage {i+1}",
			text=f"This is passage {i+1}",
			score=0.9 - (i * 0.1),
			source="TestKB",
		))
	return tuple(chunks)


def make_success_response(probabilities=None):
	"""Create a successful DecisionResponse for RAG Filter."""
	if probabilities is None:
		probabilities = {
			"chunk-1": 0.95,
			"chunk-2": 0.85,
		}
	return DecisionResponse(
		status=DecisionStatus.SUCCESS,
		answers={
			"filter": DecisionAnswer(
				"filter",
				QuestionKind.SCORE,
				value=None,
				probabilities=probabilities,
				confidence=None,
			)
		},
	)


class TestRetainSelectedContext(unittest.TestCase):
	"""Test the retain_selected_context function (I-DR1 guarantee)."""

	def test_keeps_only_selected_ids(self):
		"""Narrow an authorized set to selected ids."""
		chunks = make_chunks(3)
		# Convert to objects that have 'id' or 'chunk_id' attribute
		objects = [SimpleNamespace(**c) for c in chunks]

		selected_ids = ["chunk-1", "chunk-3"]
		result = retain_selected_context(objects, selected_ids)

		result_ids = [getattr(obj, "chunk_id", getattr(obj, "id", None)) for obj in result]
		self.assertEqual(set(result_ids), {"chunk-1", "chunk-3"})

	def test_preserves_source_order(self):
		"""Result maintains order of input objects, not selection order."""
		chunks = make_chunks(3)
		objects = [SimpleNamespace(**c) for c in chunks]

		# Select them out of original order
		selected_ids = ["chunk-3", "chunk-1"]
		result = retain_selected_context(objects, selected_ids)

		result_ids = [getattr(obj, "chunk_id", getattr(obj, "id", None)) for obj in result]
		# Should be in input order, not selection order
		self.assertEqual(result_ids, ["chunk-1", "chunk-3"])

	def test_subset_guarantee(self):
		"""Result is always a subset of input (I-DR1)."""
		chunks = make_chunks(5)
		objects = [SimpleNamespace(**c) for c in chunks]
		input_ids = {getattr(obj, "chunk_id", getattr(obj, "id", None)) for obj in objects}

		selected_ids = ["chunk-1", "chunk-3", "chunk-999"]  # includes non-existent id
		result = retain_selected_context(objects, selected_ids)
		result_ids = {getattr(obj, "chunk_id", getattr(obj, "id", None)) for obj in result}

		# Result is subset of input, no hallucinated ids
		self.assertTrue(result_ids <= input_ids)
		self.assertEqual(result_ids, {"chunk-1", "chunk-3"})

	def test_empty_selection_yields_empty_result(self):
		"""Selecting with no valid ids returns empty."""
		chunks = make_chunks(3)
		objects = [SimpleNamespace(**c) for c in chunks]

		result = retain_selected_context(objects, [])
		self.assertEqual(len(result), 0)

	def test_deduplicates_and_handles_both_id_and_chunk_id(self):
		"""Handles objects with 'id' or 'chunk_id' attribute."""
		obj1 = SimpleNamespace(id="chunk-1", text="text")
		obj2 = SimpleNamespace(chunk_id="chunk-2", text="text")
		objects = [obj1, obj2]

		selected_ids = ["chunk-1"]
		result = retain_selected_context(objects, selected_ids)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0].id, "chunk-1")


class TestApplyRagFilterDecision(unittest.TestCase):
	"""Test apply_rag_filter_decision function."""

	def test_enforce_mode_narrows_chunks(self):
		"""Enforce mode filters to selected_ids."""
		chunks = make_chunks(3)
		decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=("chunk-1", "chunk-3"),
			hint=None,
			decision_call="DC-1"
		)

		result = apply_rag_filter_decision(chunks, decision, "Enforce")

		result_ids = [c["chunk_id"] for c in result]
		self.assertEqual(result_ids, ["chunk-1", "chunk-3"])

	def test_advise_mode_keeps_all_chunks(self):
		"""Advise mode returns all chunks unchanged."""
		chunks = make_chunks(3)
		decision = SurfaceDecision(
			mode="Advise",
			selected_ids=None,
			hint="Decision suggestion: chunk-1 (0.95), chunk-2 (0.85)",
			decision_call="DC-1"
		)

		result = apply_rag_filter_decision(chunks, decision, "Advise")

		self.assertEqual(len(result), 3)
		self.assertEqual(len(result), len(chunks))

	def test_no_decision_keeps_all_chunks(self):
		"""When decision is None, all chunks are kept."""
		chunks = make_chunks(3)

		result = apply_rag_filter_decision(chunks, None, "Enforce")

		self.assertEqual(len(result), 3)

	def test_off_mode_keeps_all_chunks(self):
		"""When mode is Off or unknown, all chunks are kept."""
		chunks = make_chunks(3)
		decision = SurfaceDecision(
			mode="Off",
			selected_ids=None,
			hint=None,
			decision_call=None
		)

		result = apply_rag_filter_decision(chunks, decision, "Off")

		self.assertEqual(len(result), 3)

	def test_enforce_with_empty_selection_narrows_to_zero(self):
		"""Enforce with empty selection yields zero chunks."""
		chunks = make_chunks(3)
		decision = SurfaceDecision(
			mode="Enforce",
			selected_ids=(),
			hint=None,
			decision_call="DC-1"
		)

		result = apply_rag_filter_decision(chunks, decision, "Enforce")

		self.assertEqual(len(result), 0)


class TestRagFilterDecisionIntegration(unittest.TestCase):
	"""Test RAG Filter surface integration with agent_surfaces."""

	def test_enforce_filters_and_reorders_chunks(self):
		"""Enforce mode: decide_for_surface returns selected_ids as subset."""
		agent = make_agent(mode="Enforce")
		candidates = make_chunk_objects(3)
		# Backend returns scores for chunks 1 and 3 only (reordered)
		response = make_success_response(probabilities={
			"chunk-3": 0.95,
			"chunk-1": 0.85,
		})

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		self.assertEqual(result.mode, "Enforce")
		self.assertIsNone(result.hint)
		# Result is ordered by score: chunk-3 (0.95), chunk-1 (0.85)
		self.assertEqual(result.selected_ids, ("chunk-3", "chunk-1"))

	def test_enforce_subset_guarantee_drops_unknown_ids(self):
		"""Enforce: hallucinated ids are silently dropped (I-DR1)."""
		agent = make_agent(mode="Enforce")
		candidates = make_chunk_objects(2)
		# Backend returns a real chunk plus a hallucinated id
		response = make_success_response(probabilities={
			"chunk-1": 0.95,
			"ghost-chunk": 0.99,  # Not in original candidates
		})

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		# Ghost id should be dropped, only real chunk-1 kept
		self.assertEqual(result.selected_ids, ("chunk-1",))
		self.assertTrue(set(result.selected_ids) <= {c.id for c in candidates})

	def test_advise_returns_hint_and_never_narrows(self):
		"""Advise mode: keep all candidates and return hint."""
		agent = make_agent(mode="Advise")
		candidates = make_chunk_objects(3)
		response = make_success_response(probabilities={
			"chunk-1": 0.95,
			"chunk-2": 0.85,
		})

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			result = decide_for_surface(
				agent, "RAG Filter", candidates, {}, make_origin(), hint_kind="passages"
			)

		self.assertEqual(result.mode, "Advise")
		self.assertIsNone(result.selected_ids)
		self.assertIsNotNone(result.hint)
		self.assertIn("passages", result.hint)
		self.assertIn("chunk-1 (0.95)", result.hint)
		self.assertIn("chunk-2 (0.85)", result.hint)
		self.assertEqual(run_policy.call_args.kwargs["mode"], "Advise")

	def test_advise_with_no_scoreable_answer_returns_none_hint(self):
		"""Advise with no probabilities: keep all candidates, return None hint."""
		agent = make_agent(mode="Advise")
		candidates = make_chunk_objects(2)
		response = DecisionResponse(status=DecisionStatus.SUCCESS, answers={})

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		):
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		self.assertEqual(result.mode, "Advise")
		self.assertIsNone(result.hint)
		self.assertIsNone(result.selected_ids)

	def test_off_mode_returns_none_without_calling_run_policy(self):
		"""Off binding: no decision call."""
		agent = make_agent(mode="Off")
		candidates = make_chunk_objects(3)

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy"
		) as run_policy:
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		self.assertIsNone(result)
		run_policy.assert_not_called()

	def test_disabled_backend_returns_none_keeps_all(self):
		"""Disabled service (kill switch off): caller keeps all candidates."""
		agent = make_agent(mode="Enforce")
		candidates = make_chunk_objects(3)

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=agent_surfaces.service.DISABLED),
		):
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		self.assertIsNone(result)
		# Caller keeps all candidates

	def test_timeout_returns_none_keeps_all(self):
		"""Timeout: caller keeps all candidates."""
		agent = make_agent(mode="Enforce")
		candidates = make_chunk_objects(3)
		response = DecisionResponse(status=DecisionStatus.TIMEOUT)

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.TIMEOUT, response=response),
		):
			result = decide_for_surface(agent, "RAG Filter", candidates, {}, make_origin())

		self.assertIsNone(result)

	def test_passes_correct_candidate_source_and_hint_kind(self):
		"""Verify candidate_source and hint_kind are passed through."""
		agent = make_agent(mode="Advise")
		candidates = make_chunk_objects(2)
		response = make_success_response()

		with patch(
			"huf.ai.decision.agent_surfaces.service.run_policy",
			return_value=ServiceResult(status=DecisionStatus.SUCCESS, response=response),
		) as run_policy:
			decide_for_surface(
				agent,
				"RAG Filter",
				candidates,
				{"query": "test"},
				make_origin(),
				candidate_source=CandidateSource.AUTHORIZED_KNOWLEDGE_CHUNKS,
				hint_kind="passages",
			)

		call_kwargs = run_policy.call_args.kwargs
		self.assertEqual(call_kwargs["candidate_source"], CandidateSource.AUTHORIZED_KNOWLEDGE_CHUNKS)


if __name__ == "__main__":
	unittest.main()
