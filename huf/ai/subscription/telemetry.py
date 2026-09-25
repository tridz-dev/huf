"""
Telemetry mapper for subscription CLI turns to Agent Run fields.

PURE FUNCTION MODULE: no Frappe doc writes, no I/O. Takes data in, returns a dict out.
This is a compliance-critical function — a test suite checks every rule.

Key compliance rules (from PLAN.md §58 and §12.2/§12.3):
- cost MUST be None, NEVER 0 or 0.0: an unmetered subscription turn must never be recorded as a $0 API cost
- missing usage metrics stay null, NOT 0: provider silence means "unknown", not "zero"
- provider-reported 0 is preserved as 0: a metric explicitly reported as 0 is different from missing
- usage_source marks the provenance of metrics (provider_reported vs estimated vs unavailable)
- never blend estimated values into provider-reported fields without a distinguishing marker
"""

from __future__ import annotations

from typing import Any

from huf.ai.subscription.types import SubscriptionTurnResult


def map_turn_result_to_agent_run_fields(
	result: SubscriptionTurnResult,
	runtime_name: str,
) -> dict[str, Any]:
	"""
	Map a subscription CLI turn result to Agent Run field values.

	Args:
		result: SubscriptionTurnResult from the subscription CLI adapter
		runtime_name: Name of the Subscription Runtime that executed this turn

	Returns:
		A dict with Agent Run field names and values ready to merge into a doc.save() call.
		Keys correspond exactly to DocType field names.

	Compliance rules:
	- cost MUST be None (per PLAN §58, §12.2): unmetered subscription turns must NEVER be recorded as $0
	- missing usage metrics stay None/unset (per PLAN §12.3, §39.4): provider silence ≠ zero
	- provider-reported 0 is preserved as 0 (per PLAN §12.3): explicit zero ≠ missing metric
	- usage_source marks the source of each usage field's data: provider_reported, estimated, or unavailable
	- reasoning_snapshot shape: {"source": "provider_visible_summary", "summary": ...}
	"""

	fields = {
		"provider_path": "subscription_cli",
		"billing_mode": "subscription",
		"runtime": runtime_name,
		"runtime_mode": "subscription_passthrough",
		"provider_session_id_snapshot": result.provider_session_id,
		# CRITICAL: Cost must be None, not 0 or 0.0.
		# Per PLAN §58 and §12.2: "Do not write cost = 0 merely because HUF did not make
		# an API-billed request." Subscription has economic cost; "unmetered by HUF" ≠ "free".
		"cost": None,
		"cost_source": "subscription_unmetered",
		"cost_calculation_status": "unavailable",
	}

	# Map usage fields with strict null/zero semantics.
	# Missing metrics stay null. Provider-reported 0 is preserved. Estimated values require
	# usage_source="estimated" for the whole record (we do not estimate here, so never reached).
	usage = result.usage or {}

	# Define usage fields to populate. Map multiple provider keys to single fields via aliases.
	# Process in priority order: if a high-priority key is present, prefer it.
	usage_field_definitions = {
		# (field_name, [list of provider keys in priority order])
		"input_tokens": ["input_tokens"],
		"output_tokens": ["output_tokens"],
		"cached_tokens": ["cached_tokens", "cached_input_tokens"],  # Prefer cached_tokens, fallback to cached_input_tokens
		"billed_input_tokens": ["billed_input_tokens"],
		"peak_context_tokens": ["peak_context_tokens"],
		"cache_creation_tokens": ["cache_creation_tokens"],
		"total_tokens": ["total_tokens"],
	}

	for field_name, provider_keys in usage_field_definitions.items():
		# Find first key that's present in usage
		value = None
		for key in provider_keys:
			if key in usage:
				value = usage[key]
				break

		# Set field: use found value (including 0 if provider reported it) or None if not reported.
		# Per PLAN §12.3: missing metrics → null, provider-reported 0 → preserved as 0.
		fields[field_name] = value

	# Round count: special case, used for multi-step completions.
	# If provider reported it, use it; otherwise leave unset.
	fields["round_count"] = usage.get("round_count")

	# Mark usage source: provider_reported (only when provider gave us metrics),
	# estimated (if HUF estimated from text — not done here), or unavailable.
	# Since passthrough mode gets no history to estimate from, and this mapper does not estimate,
	# usage_source is always provider_reported (if any usage field exists) or unavailable (if none).
	if usage:
		fields["usage_source"] = "provider_reported"
	else:
		fields["usage_source"] = "unavailable"

	# Reasoning snapshot: JSON-serializable dict if summary is present.
	# Shape: {"source": "provider_visible_summary", "summary": "..."}
	# Per PLAN §12.4: capture provider-visible summary, not hidden reasoning.
	if result.reasoning_summary:
		fields["reasoning_snapshot"] = {
			"source": "provider_visible_summary",
			"summary": result.reasoning_summary,
		}
	else:
		fields["reasoning_snapshot"] = None

	return fields
