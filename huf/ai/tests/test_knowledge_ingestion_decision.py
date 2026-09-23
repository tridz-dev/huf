"""Tests for Knowledge Source ingestion decision tagging."""

import pytest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace


import frappe

# Mock frappe components before importing indexer
frappe.session = SimpleNamespace(user="test_user")
frappe.logger = MagicMock(return_value=MagicMock())

from huf.ai.knowledge.indexer import _apply_ingestion_decision_tags
from huf.ai.decision.types import ServiceResult, DecisionResponse, DecisionStatus, DecisionAnswer, QuestionKind


@pytest.fixture
def knowledge_source():
	"""Create a test Knowledge Source mock."""
	return SimpleNamespace(
		doctype="Knowledge Source",
		source_name="test_ingestion_source",
		knowledge_type="sqlite_fts",
		scope="Site",
		chunk_size=512,
		chunk_overlap=50,
		ingestion_decision_policy=None,
		ingestion_decision_mode="Off",
	)


@pytest.fixture
def test_chunks():
	"""Create sample chunks for testing."""
	return [
		{
			"input_id": "test_input_1",
			"input_type": "Text",
			"source_title": "Test Document",
			"chunk_index": 0,
			"text": "This is a test chunk about compliance.",
			"char_start": 0,
			"char_end": 50,
			"metadata": {"source": "test"},
		},
		{
			"input_id": "test_input_1",
			"input_type": "Text",
			"source_title": "Test Document",
			"chunk_index": 1,
			"text": "This is another chunk about security policies.",
			"char_start": 50,
			"char_end": 100,
			"metadata": {"source": "test"},
		},
	]


def test_ingestion_tagging_disabled(knowledge_source, test_chunks):
	"""Test that tagging is skipped when mode is Off."""
	knowledge_source.ingestion_decision_mode = "Off"
	original_metadata = [chunk["metadata"].copy() for chunk in test_chunks]

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify metadata unchanged
	for chunk, orig in zip(test_chunks, original_metadata):
		assert chunk["metadata"] == orig


def test_ingestion_tagging_no_policy(knowledge_source, test_chunks):
	"""Test that tagging is skipped when no policy is set."""
	knowledge_source.ingestion_decision_policy = None
	knowledge_source.ingestion_decision_mode = "Enforce"
	original_metadata = [chunk["metadata"].copy() for chunk in test_chunks]

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify metadata unchanged
	for chunk, orig in zip(test_chunks, original_metadata):
		assert chunk["metadata"] == orig


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_shadow_mode(mock_run_policy, knowledge_source, test_chunks):
	"""Test Shadow mode: decisions are logged but chunks not modified."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Shadow"
	knowledge_source.ingestion_tag_field = "classification"

	# Mock run_policy to return a successful shadow result
	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(status=DecisionStatus.SUCCESS),
		decision_call="decision_call_123",
	)

	original_metadata = [chunk["metadata"].copy() for chunk in test_chunks]

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify run_policy was called for each chunk
	assert mock_run_policy.call_count == len(test_chunks)

	# Verify metadata NOT modified (Shadow mode logs only)
	for chunk, orig in zip(test_chunks, original_metadata):
		assert chunk["metadata"] == orig


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_enforce_mode(mock_run_policy, knowledge_source, test_chunks):
	"""Test Enforce mode: decisions are written to chunk metadata."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"
	knowledge_source.ingestion_tag_field = "decision_tag"

	# Mock run_policy to return a successful result with an answer
	decision_answer = DecisionAnswer(
		question_id="classification",
		kind=QuestionKind.SELECT,
		value="confidential",
	)
	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={"classification": decision_answer},
		),
		decision_call="decision_call_456",
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify run_policy was called for each chunk
	assert mock_run_policy.call_count == len(test_chunks)

	# Verify metadata was updated with decision tag
	for chunk in test_chunks:
		assert "decision_tag" in chunk["metadata"]
		assert chunk["metadata"]["decision_tag"] == "confidential"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_default_tag_field(mock_run_policy, knowledge_source, test_chunks):
	"""Test that default tag field is used when not specified."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"
	knowledge_source.ingestion_tag_field = None  # Should default to "decision_tag"

	decision_answer = DecisionAnswer(
		question_id="category",
		kind=QuestionKind.SELECT,
		value="important",
	)
	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={"category": decision_answer},
		),
		decision_call="decision_call_789",
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify default tag field was used
	for chunk in test_chunks:
		assert "decision_tag" in chunk["metadata"]
		assert chunk["metadata"]["decision_tag"] == "important"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_decision_failure_does_not_block(mock_run_policy, knowledge_source, test_chunks):
	"""Test that decision failures never block indexing."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"
	knowledge_source.ingestion_tag_field = "decision_tag"

	# Mock run_policy to raise an exception
	mock_run_policy.side_effect = Exception("Decision service unavailable")

	original_metadata = [chunk["metadata"].copy() for chunk in test_chunks]

	# Should not raise
	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify metadata unchanged
	for chunk, orig in zip(test_chunks, original_metadata):
		assert chunk["metadata"] == orig


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_partial_failures(mock_run_policy, knowledge_source, test_chunks):
	"""Test that partial failures in one chunk don't affect others."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"
	knowledge_source.ingestion_tag_field = "decision_tag"

	# Mock run_policy: fail on first chunk, succeed on second
	decision_answer = DecisionAnswer(
		question_id="category",
		kind=QuestionKind.SELECT,
		value="public",
	)
	successful_result = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={"category": decision_answer},
		),
		decision_call="decision_call_second",
	)

	mock_run_policy.side_effect = [
		Exception("Service error on first chunk"),
		successful_result,
	]

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify first chunk metadata unchanged (error)
	assert "decision_tag" not in test_chunks[0]["metadata"]

	# Verify second chunk metadata updated (success)
	assert test_chunks[1]["metadata"]["decision_tag"] == "public"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_numeric_answer(mock_run_policy, knowledge_source, test_chunks):
	"""Test handling of numeric decision answers."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"
	knowledge_source.ingestion_tag_field = "relevance_score"

	decision_answer = DecisionAnswer(
		question_id="relevance",
		kind=QuestionKind.JUDGE,
		value=0.85,
	)
	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers={"relevance": decision_answer},
		),
		decision_call="decision_call_numeric",
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify numeric answer is stored as string
	for chunk in test_chunks:
		assert chunk["metadata"]["relevance_score"] == "0.85"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_surface_name(mock_run_policy, knowledge_source, test_chunks):
	"""Test that surface parameter is 'knowledge_ingestion'."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"

	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(status=DecisionStatus.SUCCESS),
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify surface parameter
	for call in mock_run_policy.call_args_list:
		assert call.kwargs.get("surface") == "knowledge_ingestion"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_origin_type(mock_run_policy, knowledge_source, test_chunks):
	"""Test that origin type is set correctly."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"

	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(status=DecisionStatus.SUCCESS),
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify origin_type
	for call in mock_run_policy.call_args_list:
		origin = call.kwargs.get("origin")
		assert origin is not None
		assert origin.origin_type == "knowledge_ingestion"


@patch("huf.ai.knowledge.indexer.run_policy")
def test_ingestion_tagging_state_contains_text(mock_run_policy, knowledge_source, test_chunks):
	"""Test that chunk text is passed as state."""
	knowledge_source.ingestion_decision_policy = "test_policy"
	knowledge_source.ingestion_decision_mode = "Enforce"

	mock_run_policy.return_value = ServiceResult(
		status=DecisionStatus.SUCCESS,
		response=DecisionResponse(status=DecisionStatus.SUCCESS),
	)

	_apply_ingestion_decision_tags(knowledge_source, test_chunks)

	# Verify state contains chunk text
	for i, call in enumerate(mock_run_policy.call_args_list):
		state = call.kwargs.get("state")
		assert state is not None
		assert state.get("text") == test_chunks[i]["text"]
