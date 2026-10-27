"""Routing contract for Flow ``router.decision`` nodes."""

from __future__ import annotations

from typing import Any

from huf.ai.decision.types import DecisionResponse, DecisionStatus


def resolve_decision_route(
	response: DecisionResponse,
	*,
	candidate_node_ids: set[str],
	uncertain_next: str | None = None,
	minimum_confidence: float | None = None,
) -> dict[str, Any]:
	"""Convert a normalized Decision response into a bounded Flow route."""
	if response.status != DecisionStatus.SUCCESS:
		return {"status": "uncertain", "next_node_id": uncertain_next, "reason": response.error_code or "decision_failed"}
	answer = next(iter(response.answers.values()), None)
	if answer is None:
		return {"status": "uncertain", "next_node_id": uncertain_next, "reason": "decision_missing_answer"}
	if minimum_confidence is not None and (answer.confidence is None or answer.confidence < minimum_confidence):
		return {"status": "uncertain", "next_node_id": uncertain_next, "reason": "decision_low_confidence"}
	selected = answer.value if isinstance(answer.value, str) else None
	if selected not in candidate_node_ids:
		return {"status": "uncertain", "next_node_id": uncertain_next, "reason": "decision_invalid_route"}
	return {"status": "success", "next_node_id": selected, "reason": "decision_selected"}
