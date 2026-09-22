"""Small, provider-independent cost helpers for Decision Call accounting."""

from __future__ import annotations

from huf.ai.decision.types import DecisionUsage


def estimate_input_cost(usage: DecisionUsage, input_price_per_million: float | None) -> float | None:
	"""Estimate input cost when both usage and a deployment-specific price are known."""
	if usage.measured_cost is not None:
		return usage.measured_cost
	if usage.input_tokens is None or input_price_per_million is None:
		return None
	if input_price_per_million < 0:
		raise ValueError("input_price_per_million cannot be negative")
	return usage.input_tokens * input_price_per_million / 1_000_000
