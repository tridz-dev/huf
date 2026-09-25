"""
Pure mapping module: converts SubscriptionTurnResult into HUF's existing realtime lifecycle events.

This module NEVER touches dispatch files (agent_integration.py, run.py) — it is a standalone
normalization layer that produces deterministic event sequences matching the shape that the
existing HUF frontend expects for a normal (non-subscription) run.

BUFFERED delivery only: the full turn result arrives at once, and this module's job is to map
that single completed result into the sequence of realtime lifecycle events the frontend already
handles for normal runs.
"""

from __future__ import annotations

from typing import Any

from .types import SubscriptionTurnResult


def _sanitize_error_message(error: str, max_length: int = 256) -> str:
	"""
	Sanitize an error message to prevent leaking secrets, provider internals, or raw stderr.

	Keeps user-facing error text only, truncates to prevent log injection,
	and masks likely secret/credential patterns.

	Args:
		error: Raw error message from provider or runtime
		max_length: Maximum output length (default 256 chars)

	Returns:
		Sanitized error message safe for frontend display
	"""
	if not error:
		return "An unknown error occurred."

	# Truncate early to prevent log injection
	truncated = error[:max_length * 2]

	# Common secret patterns to mask (case-insensitive)
	secret_patterns = [
		"api_key",
		"api-key",
		"apikey",
		"access_token",
		"access-token",
		"secret",
		"password",
		"bearer",
		"authorization",
		"credentials",
		"token",
		"key=",
		"sk_",
		"sk-",
		"pk_",
		"pk-",
	]

	# Simple masking: if any secret pattern is found in the error, mask the entire thing
	error_lower = truncated.lower()
	for pattern in secret_patterns:
		if pattern in error_lower:
			return "Authentication or credential error. Please verify your provider configuration."

	# Truncate to final length and clean up
	sanitized = truncated[:max_length].strip()
	if len(truncated) > max_length:
		sanitized += "…"

	return sanitized if sanitized else "An unknown error occurred."


def map_turn_result_to_realtime_events(
	result: SubscriptionTurnResult, run_id: str, conversation_id: str
) -> list[dict[str, Any]]:
	"""
	Map a completed SubscriptionTurnResult into a sequence of realtime lifecycle events.

	This function produces a deterministic sequence of events in the same shape as HUF's
	existing `_emit_run_lifecycle_event` function (huf/ai/agent_integration.py:535-560).

	Events are buffered (not streamed incrementally): the full turn result arrives at once,
	and we emit:
	1. A "status: Started" event (if applicable)
	2. A "delta"/"response" event carrying final_text as the complete response
	3. A terminal event (success, error, or auth_required)

	This allows the frontend to render subscription-mode responses using the same
	realtime event handler it already uses for normal runs.

	Args:
		result: A completed SubscriptionTurnResult from the provider
		run_id: The Agent Run ID for tracking
		conversation_id: The Agent Conversation ID for channel routing

	Returns:
		A list of realtime event dicts in the canonical HUF shape:
		{
			"type": "agent_run_status",
			"status": "Started" | "Success" | "Failed",
			"agent_run_id": run_id,
			"conversation_id": conversation_id,
			"response" | "error" | "auth_reason": <value>,
			"sequence": <optional sequence number>,
		}

	Example:
		>>> result = SubscriptionTurnResult(
		...     status="success",
		...     final_text="Hello from the API!",
		...     provider_session_id="sess-123"
		... )
		>>> events = map_turn_result_to_realtime_events(result, "AR-001", "CONV-001")
		>>> len(events)
		3
		>>> events[0]["status"]
		"Started"
		>>> events[1]["response"]
		"Hello from the API!"
		>>> events[2]["status"]
		"Success"
	"""
	events: list[dict[str, Any]] = []

	# 1. STARTED event: signal that execution has begun
	events.append(
		{
			"type": "agent_run_status",
			"status": "Started",
			"agent_run_id": run_id,
			"conversation_id": conversation_id,
		}
	)

	# 2. MESSAGE event: carry the full response text in a single event (buffered, not streamed)
	# The frontend expects this in the "response" field for success, or "error" field for errors
	if result.status == "success" and result.final_text:
		events.append(
			{
				"type": "agent_run_status",
				"status": "Started",  # Still "Started" for intermediate delivery
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"response": result.final_text,
			}
		)
	elif result.status == "auth_required":
		# Auth-required is a special in-progress state, not a failure
		# The frontend should render this as "waiting for authentication"
		events.append(
			{
				"type": "subscription_auth_required",
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"auth_reason": result.auth_reason or "Authentication required",
				"provider_session_id": result.provider_session_id,
			}
		)
	elif result.status == "error" and result.final_text:
		# Error with a message: sanitize and emit
		sanitized = _sanitize_error_message(result.final_text)
		events.append(
			{
				"type": "agent_run_status",
				"status": "Started",
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"error": sanitized,
			}
		)

	# 3. TERMINAL event: signal completion
	if result.status == "success":
		events.append(
			{
				"type": "agent_run_status",
				"status": "Success",
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"response": result.final_text,
			}
		)
	elif result.status == "error":
		sanitized = _sanitize_error_message(result.final_text or "An unknown error occurred.")
		events.append(
			{
				"type": "agent_run_status",
				"status": "Failed",
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"error": sanitized,
			}
		)
	elif result.status == "auth_required":
		# Auth-required is NOT a failure; it's a normal, recoverable state
		# The terminal event for auth-required is already emitted above
		# No additional event needed here
		pass
	else:
		# Unknown status: treat as error with generic message
		events.append(
			{
				"type": "agent_run_status",
				"status": "Failed",
				"agent_run_id": run_id,
				"conversation_id": conversation_id,
				"error": f"Unknown result status: {result.status}",
			}
		)

	return events
