"""
Comprehensive unit tests for subscription telemetry mapper.

Tests EVERY rule from PLAN.md §58 and §12.2/§12.3 as separate test cases:
- Cost is NEVER 0 (compliance critical)
- Missing usage metric stays null, not zero
- Provider-reported zero is preserved as zero (not treated as missing)
- Usage source correctly marked (provider_reported vs unavailable)
- Reasoning snapshot shape when summary is present
- Table-driven tests with representative SubscriptionTurnResult inputs
"""

from __future__ import annotations

import json
from unittest import TestCase

from huf.ai.subscription.telemetry import map_turn_result_to_agent_run_fields
from huf.ai.subscription.types import SubscriptionTurnResult


class TestTelemetryMapperBasics(TestCase):
	"""Basic compliance rules: provider_path, billing_mode, runtime fields."""

	def test_provider_path_always_subscription_cli(self) -> None:
		"""provider_path must always be "subscription_cli"."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["provider_path"], "subscription_cli")

	def test_billing_mode_always_subscription(self) -> None:
		"""billing_mode must always be "subscription"."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["billing_mode"], "subscription")

	def test_runtime_set_from_parameter(self) -> None:
		"""runtime field must be set to the runtime_name parameter."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "gpt_runner")

		self.assertEqual(fields["runtime"], "gpt_runner")

	def test_runtime_mode_always_subscription_passthrough(self) -> None:
		"""runtime_mode must always be "subscription_passthrough"."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["runtime_mode"], "subscription_passthrough")

	def test_cost_source_always_subscription_unmetered(self) -> None:
		"""cost_source must always be "subscription_unmetered"."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["cost_source"], "subscription_unmetered")

	def test_cost_calculation_status_always_unavailable(self) -> None:
		"""cost_calculation_status must always be "unavailable"."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["cost_calculation_status"], "unavailable")

	def test_provider_session_id_snapshot_from_result(self) -> None:
		"""provider_session_id_snapshot must be set from result.provider_session_id."""
		result = SubscriptionTurnResult(
			status="success", final_text="Hello", provider_session_id="sess_xyz789"
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["provider_session_id_snapshot"], "sess_xyz789")

	def test_provider_session_id_snapshot_none_when_missing(self) -> None:
		"""provider_session_id_snapshot must be None if result has no session ID."""
		result = SubscriptionTurnResult(
			status="success", final_text="Hello", provider_session_id=None
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["provider_session_id_snapshot"])


class TestCostCompliance(TestCase):
	"""CRITICAL compliance rule: cost must NEVER be 0 or 0.0 (per PLAN §58, §12.2)."""

	def test_cost_is_none_not_zero(self) -> None:
		"""Cost must be None, not 0 or 0.0. This is the single most important rule."""
		result = SubscriptionTurnResult(status="success", final_text="Hello")
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["cost"])
		self.assertNotEqual(fields["cost"], 0)
		self.assertNotEqual(fields["cost"], 0.0)

	def test_cost_is_none_even_with_usage(self) -> None:
		"""Cost must be None even when provider reports usage (subscription is unmetered by HUF)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			usage={"input_tokens": 100, "output_tokens": 50},
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["cost"])

	def test_cost_is_none_even_on_error(self) -> None:
		"""Cost must be None even if the turn failed (no successful API charge recorded)."""
		result = SubscriptionTurnResult(
			status="error", final_text=None, usage={"input_tokens": 100}
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["cost"])


class TestUsageFieldSemantics(TestCase):
	"""Usage field rules (per PLAN §12.3, §39.4, §58.1):
	- provider reported → store it, mark usage_source="provider_reported"
	- not reported → leave null, NOT 0
	- provider-reported 0 → store 0 (explicit zero ≠ missing)
	"""

	def test_present_usage_stored_as_is(self) -> None:
		"""When provider reports a usage metric, store it exactly."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			usage={"input_tokens": 150, "output_tokens": 75, "total_tokens": 225},
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["input_tokens"], 150)
		self.assertEqual(fields["output_tokens"], 75)
		self.assertEqual(fields["total_tokens"], 225)

	def test_missing_usage_metric_stays_null_not_zero(self) -> None:
		"""When provider does NOT report a metric, leave it null (not 0). Per PLAN §12.3."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			usage={"input_tokens": 100},  # Only input_tokens reported
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["input_tokens"], 100)
		self.assertIsNone(fields["output_tokens"])  # NOT 0
		self.assertIsNone(fields["total_tokens"])  # NOT 0

	def test_provider_reported_zero_preserved_as_zero(self) -> None:
		"""When provider explicitly reports 0, preserve it (different from missing). Per PLAN §12.3."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			usage={
				"input_tokens": 100,
				"output_tokens": 0,  # Explicitly reported as zero
				"cached_tokens": 0,  # Explicitly reported as zero
			},
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["input_tokens"], 100)
		self.assertEqual(fields["output_tokens"], 0)  # Preserved, not treated as missing
		self.assertEqual(fields["cached_tokens"], 0)  # Preserved, not treated as missing

	def test_all_usage_fields_unmapped_stay_null(self) -> None:
		"""All usage fields default to None if not in result.usage."""
		result = SubscriptionTurnResult(
			status="success", final_text="Hello", usage={}
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["input_tokens"])
		self.assertIsNone(fields["output_tokens"])
		self.assertIsNone(fields["cached_tokens"])
		self.assertIsNone(fields["billed_input_tokens"])
		self.assertIsNone(fields["peak_context_tokens"])
		self.assertIsNone(fields["cache_creation_tokens"])
		self.assertIsNone(fields["total_tokens"])

	def test_round_count_from_usage(self) -> None:
		"""round_count should be extracted from usage dict when present."""
		result = SubscriptionTurnResult(
			status="success", final_text="Hello", usage={"round_count": 3}
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["round_count"], 3)

	def test_round_count_null_when_missing(self) -> None:
		"""round_count should be None if not in usage dict."""
		result = SubscriptionTurnResult(status="success", final_text="Hello", usage={})
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertIsNone(fields["round_count"])


class TestUsageSourceMarking(TestCase):
	"""usage_source field: mark the provenance of usage data (per PLAN §12.3, §58)."""

	def test_usage_source_provider_reported_when_usage_present(self) -> None:
		"""When result.usage has any metrics, mark usage_source="provider_reported"."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			usage={"input_tokens": 100, "output_tokens": 50},
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["usage_source"], "provider_reported")

	def test_usage_source_unavailable_when_no_usage(self) -> None:
		"""When result.usage is empty or None, mark usage_source="unavailable"."""
		result1 = SubscriptionTurnResult(
			status="success", final_text="Hello", usage={}
		)
		fields1 = map_turn_result_to_agent_run_fields(result1, "my_runtime")
		self.assertEqual(fields1["usage_source"], "unavailable")

		result2 = SubscriptionTurnResult(status="success", final_text="Hello")
		fields2 = map_turn_result_to_agent_run_fields(result2, "my_runtime")
		self.assertEqual(fields2["usage_source"], "unavailable")

	def test_usage_source_never_estimated_in_passthrough_mode(self) -> None:
		"""Passthrough mode has no history to estimate from, so never estimated."""
		# This test documents the current behavior: passthrough mapper does NOT estimate.
		# If future mapper gains estimation, this test catches the change.
		result = SubscriptionTurnResult(
			status="success", final_text="Hello", usage={}
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertNotEqual(fields["usage_source"], "estimated")


class TestReasoningSnapshot(TestCase):
	"""reasoning_snapshot field: capture provider-visible reasoning when present (per PLAN §12.4)."""

	def test_reasoning_snapshot_with_summary(self) -> None:
		"""When reasoning_summary is present, create JSON snapshot."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			reasoning_summary="Analyzed the prompt and decided to answer directly.",
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		snapshot = fields["reasoning_snapshot"]
		self.assertIsNotNone(snapshot)
		self.assertEqual(snapshot["source"], "provider_visible_summary")
		self.assertEqual(
			snapshot["summary"],
			"Analyzed the prompt and decided to answer directly.",
		)

	def test_reasoning_snapshot_none_when_no_summary(self) -> None:
		"""When reasoning_summary is None/empty, reasoning_snapshot should be None."""
		result1 = SubscriptionTurnResult(
			status="success", final_text="Hello", reasoning_summary=None
		)
		fields1 = map_turn_result_to_agent_run_fields(result1, "my_runtime")
		self.assertIsNone(fields1["reasoning_snapshot"])

		result2 = SubscriptionTurnResult(status="success", final_text="Hello")
		fields2 = map_turn_result_to_agent_run_fields(result2, "my_runtime")
		self.assertIsNone(fields2["reasoning_snapshot"])

	def test_reasoning_snapshot_is_json_serializable(self) -> None:
		"""reasoning_snapshot must be JSON-serializable (no nested objects)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Hello",
			reasoning_summary="Step 1. Think. Step 2. Answer.",
		)
		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		snapshot = fields["reasoning_snapshot"]
		# Should not raise
		json.dumps(snapshot)


class TestTableDrivenCases(TestCase):
	"""Table-driven tests with representative SubscriptionTurnResult inputs."""

	def test_success_with_full_usage(self) -> None:
		"""Successful turn with complete usage telemetry."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Here is the answer.",
			provider_session_id="sess_abc123",
			usage={
				"input_tokens": 200,
				"output_tokens": 150,
				"cached_tokens": 50,
				"total_tokens": 350,
				"round_count": 1,
			},
			reasoning_summary="Direct response to user query.",
		)

		fields = map_turn_result_to_agent_run_fields(result, "gemini_runtime")

		# Verify all expected fields
		self.assertEqual(fields["provider_path"], "subscription_cli")
		self.assertEqual(fields["billing_mode"], "subscription")
		self.assertEqual(fields["runtime"], "gemini_runtime")
		self.assertEqual(fields["runtime_mode"], "subscription_passthrough")
		self.assertIsNone(fields["cost"])
		self.assertEqual(fields["cost_source"], "subscription_unmetered")
		self.assertEqual(fields["cost_calculation_status"], "unavailable")
		self.assertEqual(fields["provider_session_id_snapshot"], "sess_abc123")
		self.assertEqual(fields["input_tokens"], 200)
		self.assertEqual(fields["output_tokens"], 150)
		self.assertEqual(fields["cached_tokens"], 50)
		self.assertEqual(fields["total_tokens"], 350)
		self.assertEqual(fields["round_count"], 1)
		self.assertEqual(fields["usage_source"], "provider_reported")
		self.assertIsNotNone(fields["reasoning_snapshot"])
		self.assertEqual(fields["reasoning_snapshot"]["source"], "provider_visible_summary")

	def test_success_with_partial_usage(self) -> None:
		"""Successful turn with incomplete usage telemetry (provider doesn't expose all metrics)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Response",
			provider_session_id="sess_def456",
			usage={
				"input_tokens": 150,
				"output_tokens": 100,
				# No cached_tokens, total_tokens, round_count
			},
		)

		fields = map_turn_result_to_agent_run_fields(result, "claude_runtime")

		self.assertEqual(fields["input_tokens"], 150)
		self.assertEqual(fields["output_tokens"], 100)
		self.assertIsNone(fields["cached_tokens"])  # Not reported
		self.assertIsNone(fields["total_tokens"])  # Not reported
		self.assertIsNone(fields["round_count"])  # Not reported
		self.assertEqual(fields["usage_source"], "provider_reported")
		self.assertIsNone(fields["reasoning_snapshot"])

	def test_success_with_no_usage(self) -> None:
		"""Successful turn but provider reports no usage metrics (e.g., streaming not supported)."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Here is my response.",
			provider_session_id="sess_ghi789",
			usage=None,  # Provider doesn't expose usage
		)

		fields = map_turn_result_to_agent_run_fields(result, "openai_runtime")

		self.assertIsNone(fields["input_tokens"])
		self.assertIsNone(fields["output_tokens"])
		self.assertIsNone(fields["total_tokens"])
		self.assertEqual(fields["usage_source"], "unavailable")
		self.assertIsNone(fields["cost"])

	def test_error_result(self) -> None:
		"""Error turn (e.g., model unavailable, CLI crashed)."""
		result = SubscriptionTurnResult(
			status="error",
			final_text=None,
			provider_session_id="sess_jkl012",
			usage={},
		)

		fields = map_turn_result_to_agent_run_fields(result, "fallback_runtime")

		self.assertIsNone(fields["cost"])
		self.assertEqual(fields["usage_source"], "unavailable")
		self.assertIsNone(fields["reasoning_snapshot"])

	def test_auth_required_result(self) -> None:
		"""Turn parked due to authentication required."""
		result = SubscriptionTurnResult(
			status="auth_required",
			final_text=None,
			provider_session_id="sess_mno345",
			usage={},
		)

		fields = map_turn_result_to_agent_run_fields(result, "secured_runtime")

		# Even on auth failure, fields are set consistently
		self.assertEqual(fields["provider_path"], "subscription_cli")
		self.assertEqual(fields["billing_mode"], "subscription")
		self.assertIsNone(fields["cost"])
		self.assertEqual(fields["usage_source"], "unavailable")

	def test_cached_tokens_alias(self) -> None:
		"""Some providers report cached_input_tokens instead of cached_tokens."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Answer",
			usage={
				"input_tokens": 100,
				"output_tokens": 50,
				"cached_input_tokens": 30,  # Alternate name
			},
		)

		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		# Should map to cached_tokens
		self.assertEqual(fields["cached_tokens"], 30)

	def test_provider_reported_zero_metrics_preserved(self) -> None:
		"""Provider explicitly reports 0 for some metrics."""
		result = SubscriptionTurnResult(
			status="success",
			final_text="Answer",
			usage={
				"input_tokens": 100,
				"output_tokens": 50,
				"cached_tokens": 0,  # Explicitly zero
				"cache_creation_tokens": 0,  # Explicitly zero
				"round_count": 1,
			},
		)

		fields = map_turn_result_to_agent_run_fields(result, "my_runtime")

		self.assertEqual(fields["cached_tokens"], 0)
		self.assertEqual(fields["cache_creation_tokens"], 0)
		# But unmentioned fields stay null
		self.assertIsNone(fields["billed_input_tokens"])


if __name__ == "__main__":
	import unittest

	unittest.main()
