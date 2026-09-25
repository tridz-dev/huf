"""Tests for subscription types module."""

from __future__ import annotations

import dataclasses

import pytest

from huf.ai.subscription.types import SubscriptionTurnRequest


class TestSubscriptionTurnRequestClosedFields:
	"""
	Verify that SubscriptionTurnRequest has exactly the expected closed set of fields.

	This test exists specifically to catch accidental additions of fields like
	`conversation_history`, `system_instructions`, `tool_schemas`, or `knowledge_context`
	that would violate the passthrough design constraint. The subscription CLI provider
	must NEVER accidentally carry HUF internals into a turn.
	"""

	def test_has_exactly_expected_fields(self) -> None:
		"""Assert SubscriptionTurnRequest fields are exactly the 8 closed fields."""
		expected_fields = {
			"runtime_name",
			"provider_session_id",
			"text",
			"files",
			"model_override",
			"run_id",
			"conversation_id",
			"timeout_seconds",
		}

		actual_fields = {f.name for f in dataclasses.fields(SubscriptionTurnRequest)}

		assert (
			actual_fields == expected_fields
		), f"SubscriptionTurnRequest fields changed. Expected {expected_fields}, got {actual_fields}"

	def test_closed_field_set_matches_count(self) -> None:
		"""Assert SubscriptionTurnRequest has exactly 8 fields."""
		field_count = len(dataclasses.fields(SubscriptionTurnRequest))
		assert (
			field_count == 8
		), f"Expected 8 fields, got {field_count}. Do not add conversation_history, system_instructions, or knowledge context fields."

	def test_instantiation_with_valid_data(self) -> None:
		"""Verify SubscriptionTurnRequest can be instantiated with valid data."""
		req = SubscriptionTurnRequest(
			runtime_name="test-runtime",
			provider_session_id="session-123",
			text="Hello, world!",
			files=["/tmp/file1.txt"],
			model_override="gpt-4",
			run_id="run-456",
			conversation_id="conv-789",
			timeout_seconds=30,
		)
		assert req.runtime_name == "test-runtime"
		assert req.text == "Hello, world!"
		assert len(req.files) == 1
		assert req.timeout_seconds == 30

	def test_rejects_missing_runtime_name(self) -> None:
		"""Verify validation rejects empty runtime_name."""
		with pytest.raises(ValueError, match="runtime_name is required"):
			SubscriptionTurnRequest(
				runtime_name="",
				provider_session_id=None,
				text="test",
				files=[],
				model_override=None,
				run_id="run-1",
				conversation_id=None,
				timeout_seconds=30,
			)

	def test_rejects_missing_text(self) -> None:
		"""Verify validation rejects empty text."""
		with pytest.raises(ValueError, match="text is required"):
			SubscriptionTurnRequest(
				runtime_name="test",
				provider_session_id=None,
				text="",
				files=[],
				model_override=None,
				run_id="run-1",
				conversation_id=None,
				timeout_seconds=30,
			)

	def test_rejects_missing_run_id(self) -> None:
		"""Verify validation rejects empty run_id."""
		with pytest.raises(ValueError, match="run_id is required"):
			SubscriptionTurnRequest(
				runtime_name="test",
				provider_session_id=None,
				text="test",
				files=[],
				model_override=None,
				run_id="",
				conversation_id=None,
				timeout_seconds=30,
			)

	def test_rejects_nonpositive_timeout(self) -> None:
		"""Verify validation rejects zero or negative timeout_seconds."""
		with pytest.raises(ValueError, match="timeout_seconds must be positive"):
			SubscriptionTurnRequest(
				runtime_name="test",
				provider_session_id=None,
				text="test",
				files=[],
				model_override=None,
				run_id="run-1",
				conversation_id=None,
				timeout_seconds=0,
			)

	def test_frozen_dataclass_immutable(self) -> None:
		"""Verify SubscriptionTurnRequest instances are immutable."""
		req = SubscriptionTurnRequest(
			runtime_name="test",
			provider_session_id=None,
			text="test",
			files=[],
			model_override=None,
			run_id="run-1",
			conversation_id=None,
			timeout_seconds=30,
		)
		with pytest.raises(
			(AttributeError, dataclasses.FrozenInstanceError), match=".*frozen.*|cannot assign"
		):
			req.runtime_name = "modified"  # type: ignore
