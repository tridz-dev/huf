"""
Telemetry mapper for subscription CLI turns to Agent Run fields.

PURE FUNCTION MODULE: no Frappe doc writes, no I/O. Takes data in, returns a dict out.
This is a compliance-critical function — a test suite checks every rule.

Key compliance rules (from PLAN.md §58 and §12.2/§12.3), AS ADAPTED to a real,
live-verified schema constraint: every numeric Agent Run field this module
writes (`cost`, `input_tokens`, `output_tokens`, `cached_tokens`,
`billed_input_tokens`, `peak_context_tokens`, `cache_creation_tokens`,
`total_tokens`, `round_count`) is a Frappe Currency/Int field -- a NOT NULL DB
column with a numeric DEFAULT -- so none of them can ever be written as
`None` (confirmed live: `IntegrityError: Column '<field>' cannot be null`).
The plan's null-vs-zero distinction is therefore carried at the WHOLE-RECORD
level via `cost_source`/`cost_calculation_status`/`usage_source`, not
per-field:
- cost is always 0 (the field's only representable "no real charge" value);
  `cost_source="subscription_unmetered"` and
  `cost_calculation_status="unavailable"` are what tell a reader this 0 is
  not a real charge total.
- usage fields default to 0 when the provider reports nothing; `usage_source`
  is "unavailable" for that whole record, or "provider_reported" when at
  least one metric was present (individual missing sibling fields within a
  provider_reported record still read as 0 -- the schema cannot distinguish
  "reported 0" from "not reported" at the single-field level).
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
		# LIVE-VERIFIED bug fix: `Agent Run.cost` is a Frappe Currency field,
		# which is a NOT NULL DB column with DEFAULT 0.000000000 (confirmed via
		# `DESCRIBE` on a real site) -- `frappe.db.set_value(..., "cost": None)`
		# raises `IntegrityError: Column 'cost' cannot be null` on any real
		# Frappe site (structurally, no Currency field can ever be written as
		# NULL). PLAN §58/§12.2's intent -- "do not write cost = 0 merely
		# because HUF did not make an API-billed request; subscription has
		# economic cost, unmetered by HUF != free" -- must therefore be carried
		# entirely by `cost_source`/`cost_calculation_status` (both nullable),
		# not by `cost` itself. `cost` stays at the field's own numeric
		# default; the source/status fields are what tell a reader "this 0 is
		# not a real charge total, it is unmeasured."
		"cost": 0,
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

	# LIVE-VERIFIED bug fix: every one of these Agent Run fields is a Frappe
	# Int field, a NOT NULL DB column with DEFAULT 0 (confirmed via `DESCRIBE`
	# on a real site) -- writing `None` raises
	# `IntegrityError: Column '<field>' cannot be null`. So a "missing metric"
	# is represented as 0 in the field itself (structurally unavoidable), with
	# `usage_source` (set below) as the sole signal of whether that 0 means
	# "provider reported 0" / "provider reported this metric" or "provider
	# reported nothing at all, this whole record is unavailable" -- the
	# per-field null/zero distinction PLAN §12.3 originally asked for is not
	# representable field-by-field on this schema, only at the whole-record
	# `usage_source` level.
	for field_name, provider_keys in usage_field_definitions.items():
		value = 0
		for key in provider_keys:
			if key in usage:
				value = usage[key]
				break
		fields[field_name] = value

	# Round count: special case, used for multi-step completions.
	fields["round_count"] = usage.get("round_count", 0)

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
