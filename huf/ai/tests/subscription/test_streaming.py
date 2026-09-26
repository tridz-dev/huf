"""
Unit tests for huf.ai.subscription.streaming — the pure mapping module
that converts SubscriptionTurnResult into HUF realtime lifecycle events.

These tests verify:
- Success, error, and auth_required result types produce correct event sequences
- Event shapes match the existing HUF realtime event convention
- Secrets and raw stderr are sanitized in error messages
- Buffered (non-streamed) delivery produces exactly 3-4 events in the right order
"""

import json
import unittest
from unittest.mock import MagicMock

from huf.ai.subscription.streaming import (
	_sanitize_error_message,
	map_turn_result_to_realtime_events,
)
from huf.ai.subscription.types import SubscriptionTurnResult


class TestSanitizeErrorMessage(unittest.TestCase):
	"""Unit tests for error sanitization."""

	def test_empty_error_returns_default(self):
		"""Empty error string returns default message."""
		result = _sanitize_error_message("")
		self.assertEqual(result, "An unknown error occurred.")

	def test_none_error_returns_default(self):
		"""None error returns default message."""
		result = _sanitize_error_message(None)
		self.assertEqual(result, "An unknown error occurred.")

	def test_masks_api_key_pattern(self):
		"""Error containing 'api_key' is masked entirely."""
		error = "Failed to authenticate: api_key=sk_live_abc123xyz"
		result = _sanitize_error_message(error)
		self.assertNotIn("sk_live", result)
		self.assertNotIn("api_key", result)
		self.assertIn("credential", result)

	def test_masks_bearer_token(self):
		"""Error containing 'bearer' token is masked."""
		error = "Authorization failed: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
		result = _sanitize_error_message(error)
		self.assertNotIn("Bearer", result)
		self.assertNotIn("eyJhbGc", result)

	def test_masks_password_pattern(self):
		"""Error containing 'password' is masked."""
		error = "Database connection failed: password=MySecretPassword123"
		result = _sanitize_error_message(error)
		self.assertNotIn("MySecretPassword", result)
		self.assertIn("credential", result)

	def test_truncates_long_error(self):
		"""Very long errors are truncated."""
		long_error = "x" * 1000
		result = _sanitize_error_message(long_error)
		self.assertLessEqual(len(result), 260)  # 256 + "…" overhead
		self.assertTrue(result.endswith("…"))

	def test_normal_user_error_preserved(self):
		"""User-facing errors without secrets are preserved."""
		error = "The agent did not find a matching workflow for your input."
		result = _sanitize_error_message(error)
		self.assertEqual(result, error)

	def test_case_insensitive_masking(self):
		"""Secret pattern matching is case-insensitive."""
		error = "Error: API_KEY=very_secret_value_here"
		result = _sanitize_error_message(error)
		self.assertNotIn("very_secret", result)
		self.assertIn("credential", result)


class TestMapTurnResultToRealtimeEvents(unittest.TestCase):
	"""Unit tests for mapping SubscriptionTurnResult to realtime events."""

	def setUp(self):
		"""Set up test fixtures."""
		self.run_id = "AR-TEST-001"
		self.conversation_id = "CONV-TEST-001"

	def test_success_produces_three_events(self):
		"""Success result produces exactly 3 events: Started, message, Success."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello from the subscription provider!",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		self.assertEqual(len(events), 3)

	def test_success_event_sequence(self):
		"""Success events are emitted in the correct order."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello from the subscription provider!",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Event 1: Started
		self.assertEqual(events[0]["type"], "agent_run_status")
		self.assertEqual(events[0]["status"], "Started")
		self.assertEqual(events[0]["agent_run_id"], self.run_id)
		self.assertEqual(events[0]["conversation_id"], self.conversation_id)

		# Event 2: Message with response
		self.assertEqual(events[1]["type"], "agent_run_status")
		self.assertEqual(events[1]["status"], "Started")
		self.assertEqual(events[1]["response"], "Hello from the subscription provider!")

		# Event 3: Success terminal
		self.assertEqual(events[2]["type"], "agent_run_status")
		self.assertEqual(events[2]["status"], "Success")
		self.assertEqual(events[2]["response"], "Hello from the subscription provider!")

	def test_success_event_shape_matches_canonical(self):
		"""Success event shape matches HUF's _emit_run_lifecycle_event canonical format."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Test response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)
		terminal_event = events[-1]

		# Verify all expected fields are present
		expected_keys = {"type", "status", "agent_run_id", "conversation_id", "response"}
		self.assertTrue(expected_keys.issubset(set(terminal_event.keys())))

		# Verify no raw provider data is included
		self.assertNotIn("provider_session_id", terminal_event)
		self.assertNotIn("events", terminal_event)
		self.assertNotIn("usage", terminal_event)

	def test_error_produces_sanitized_message(self):
		"""Error result produces events with sanitized error message."""
		result = SubscriptionTurnResult(
			status="error",
			final_text="Failed: api_key=sk_live_abcdef123456",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Find the error event
		error_events = [e for e in events if "error" in e]
		self.assertGreater(len(error_events), 0)

		# Verify secret is not leaked
		for event in error_events:
			error_msg = event.get("error", "")
			self.assertNotIn("sk_live", error_msg)
			self.assertNotIn("api_key", error_msg)
			# Verify sanitization replacement is present
			self.assertTrue(
				"credential" in error_msg or "unknown error" in error_msg.lower()
			)

	def test_error_event_shape(self):
		"""Error events have the correct shape matching canonical format."""
		result = SubscriptionTurnResult(
			status="error",
			final_text="Something went wrong",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)
		terminal_event = events[-1]

		# Verify it's a Failed terminal event
		self.assertEqual(terminal_event["status"], "Failed")
		self.assertIn("error", terminal_event)
		self.assertEqual(terminal_event["agent_run_id"], self.run_id)
		self.assertEqual(terminal_event["conversation_id"], self.conversation_id)

	def test_auth_required_produces_special_event(self):
		"""Auth-required result produces a special subscription_auth_required event, not a generic error."""
		result = SubscriptionTurnResult(
			status="auth_required",
			final_text=None,
			provider_session_id="sess-123",
			auth_reason="Device code flow waiting for user approval",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Should have auth event + started event (or more)
		auth_events = [e for e in events if e.get("type") == "subscription_auth_required"]
		self.assertEqual(len(auth_events), 1)

		auth_event = auth_events[0]
		self.assertEqual(auth_event["type"], "subscription_auth_required")
		self.assertEqual(auth_event["agent_run_id"], self.run_id)
		self.assertEqual(auth_event["conversation_id"], self.conversation_id)
		self.assertEqual(auth_event["auth_reason"], "Device code flow waiting for user approval")

	def test_auth_required_not_treated_as_error(self):
		"""Auth-required events should not have a Failed status."""
		result = SubscriptionTurnResult(
			status="auth_required",
			final_text=None,
			provider_session_id="sess-123",
			auth_reason="Waiting for approval",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Verify no Failed event is emitted
		failed_events = [e for e in events if e.get("status") == "Failed"]
		self.assertEqual(len(failed_events), 0)

	def test_auth_required_with_default_reason(self):
		"""Auth-required without explicit reason uses default."""
		result = SubscriptionTurnResult(
			status="auth_required",
			final_text=None,
			provider_session_id="sess-123",
			auth_reason=None,
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		auth_event = [e for e in events if e.get("type") == "subscription_auth_required"][0]
		self.assertIn(auth_event["auth_reason"], "Authentication required")

	def test_unknown_status_treated_as_error(self):
		"""Unknown status is treated as an error."""
		result = SubscriptionTurnResult(
			status="unknown_status",
			final_text=None,
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		terminal_event = events[-1]
		self.assertEqual(terminal_event["status"], "Failed")
		self.assertIn("Unknown result status", terminal_event["error"])

	def test_no_raw_provider_json_forwarded(self):
		"""Raw provider JSON/JSONL is never forwarded directly to events."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="User-facing response",
			provider_session_id="sess-123",
			usage={"input_tokens": 100, "output_tokens": 50},
			reasoning_summary="Internal reasoning trace",
			events=[
				{"type": "token", "text": "hello"},
				{"type": "token", "text": " world"},
			],
			raw_debug_ref="debug-log-12345",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Verify no provider fields are leaked
		for event in events:
			self.assertNotIn("usage", event)
			self.assertNotIn("reasoning_summary", event)
			self.assertNotIn("events", event)
			self.assertNotIn("raw_debug_ref", event)
			self.assertNotIn("exit_code", event)

	def test_event_dict_is_json_serializable(self):
		"""All events must be JSON-serializable (no non-serializable objects)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Test response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Attempt to serialize all events; should not raise
		for event in events:
			try:
				json.dumps(event)
			except TypeError as e:
				self.fail(f"Event is not JSON-serializable: {event}\n{e}")

	def test_run_id_propagated_to_all_events(self):
		"""Every event contains the run_id."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		for event in events:
			self.assertEqual(
				event.get("agent_run_id"),
				self.run_id,
				f"Event missing agent_run_id: {event}",
			)

	def test_conversation_id_propagated_to_all_events(self):
		"""Every event contains the conversation_id."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		for event in events:
			self.assertEqual(
				event.get("conversation_id"),
				self.conversation_id,
				f"Event missing conversation_id: {event}",
			)

	def test_success_with_no_final_text(self):
		"""Success with no final_text still produces valid events."""
		result = SubscriptionTurnResult(
			status="success",
			final_text=None,
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# Should still have Started and Success events
		terminal_event = events[-1]
		self.assertEqual(terminal_event["status"], "Success")

	def test_error_with_empty_final_text(self):
		"""Error with empty final_text is handled gracefully."""
		result = SubscriptionTurnResult(
			status="error",
			final_text="",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		terminal_event = events[-1]
		self.assertEqual(terminal_event["status"], "Failed")
		self.assertIn("error", terminal_event)

	def test_error_sanitization_preserves_non_secret_info(self):
		"""Sanitization preserves helpful non-secret error details."""
		error = "API request failed with status 401: unauthorized access"
		result = SubscriptionTurnResult(
			status="error",
			final_text=error,
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		terminal_event = events[-1]
		# Should preserve the 401 status code info
		self.assertIn("401", terminal_event.get("error", ""))


class TestStreamingEventStructure(unittest.TestCase):
	"""Integration tests for the full event structure matching HUF canonical format."""

	def setUp(self):
		"""Set up test fixtures."""
		self.run_id = "AR-STRUCT-001"
		self.conversation_id = "CONV-STRUCT-001"

	def test_event_type_is_canonical(self):
		"""All events use the canonical 'agent_run_status' type (except auth_required)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		for event in events:
			self.assertIn(
				event["type"],
				["agent_run_status", "subscription_auth_required"],
				f"Unexpected event type: {event['type']}",
			)

	def test_status_values_are_canonical(self):
		"""Status fields use canonical HUF values."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Response",
			provider_session_id="sess-123",
		)

		events = map_turn_result_to_realtime_events(result, self.run_id, self.conversation_id)

		# All agent_run_status events should have valid status values
		for event in events:
			if event["type"] == "agent_run_status":
				self.assertIn(event["status"], ["Started", "Success", "Failed"])

	def test_snapshot_success_event_shape(self):
		"""Snapshot test: verify the exact shape of a success event sequence."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello, World!",
			provider_session_id="sess-abc",
			usage={"input": 10, "output": 5},  # Should not appear in events
		)

		events = map_turn_result_to_realtime_events(
			result,
			"AR-SNAPSHOT-001",
			"CONV-SNAPSHOT-001",
		)

		# Event 1: Start signal
		self.assertEqual(
			events[0],
			{
				"type": "agent_run_status",
				"status": "Started",
				"agent_run_id": "AR-SNAPSHOT-001",
				"conversation_id": "CONV-SNAPSHOT-001",
			},
		)

		# Event 2: Message delivery (full text, buffered)
		self.assertEqual(
			events[1],
			{
				"type": "agent_run_status",
				"status": "Started",
				"agent_run_id": "AR-SNAPSHOT-001",
				"conversation_id": "CONV-SNAPSHOT-001",
				"response": "Hello, World!",
			},
		)

		# Event 3: Terminal success
		self.assertEqual(
			events[2],
			{
				"type": "agent_run_status",
				"status": "Success",
				"agent_run_id": "AR-SNAPSHOT-001",
				"conversation_id": "CONV-SNAPSHOT-001",
				"response": "Hello, World!",
			},
		)

	def test_snapshot_error_event_sanitization(self):
		"""Snapshot test: verify error sanitization in event."""
		result = SubscriptionTurnResult(
			status="error",
			final_text="Database error: password=super_secret_123",
			provider_session_id="sess-xyz",
		)

		events = map_turn_result_to_realtime_events(
			result,
			"AR-ERROR-001",
			"CONV-ERROR-001",
		)

		terminal_event = events[-1]

		# Verify the structure
		self.assertEqual(terminal_event["type"], "agent_run_status")
		self.assertEqual(terminal_event["status"], "Failed")
		self.assertEqual(terminal_event["agent_run_id"], "AR-ERROR-001")
		self.assertEqual(terminal_event["conversation_id"], "CONV-ERROR-001")

		# Verify secrets are masked
		self.assertNotIn("super_secret", terminal_event["error"])
		self.assertNotIn("password=", terminal_event["error"])

	def test_snapshot_auth_required_event_shape(self):
		"""Snapshot test: verify the exact shape of auth_required events."""
		result = SubscriptionTurnResult(
			status="auth_required",
			final_text=None,
			provider_session_id="sess-auth-123",
			auth_reason="Device code verification pending",
		)

		events = map_turn_result_to_realtime_events(
			result,
			"AR-AUTH-001",
			"CONV-AUTH-001",
		)

		# Find the auth event
		auth_event = [e for e in events if e.get("type") == "subscription_auth_required"][0]

		# Verify exact shape
		self.assertEqual(
			auth_event,
			{
				"type": "subscription_auth_required",
				"agent_run_id": "AR-AUTH-001",
				"conversation_id": "CONV-AUTH-001",
				"auth_reason": "Device code verification pending",
				"provider_session_id": "sess-auth-123",
			},
		)


if __name__ == "__main__":
	unittest.main()
