"""Opt-in semantic guardrail decisions layered after hard validation."""

from __future__ import annotations

from dataclasses import dataclass

from huf.ai.decision.types import DecisionResponse, DecisionStatus, QuestionKind


@dataclass(frozen=True, slots=True)
class GuardrailDecision:
	status: str
	action: str
	reason: str


def evaluate_guardrail(response: DecisionResponse, *, reject_threshold: float = 0.5, uncertain_action: str = "review") -> GuardrailDecision:
	"""Map a normalized judge response to allow/reject/uncertain without mutating input."""
	if not 0 <= reject_threshold <= 1:
		raise ValueError("reject_threshold must be in [0, 1]")
	if response.status != DecisionStatus.SUCCESS:
		return GuardrailDecision("uncertain", uncertain_action, response.error_code or "decision_failed")
	answer = next(iter(response.answers.values()), None)
	if answer is None or answer.kind != QuestionKind.JUDGE or not isinstance(answer.value, (int, float)):
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_missing_judge")
	if answer.confidence is None:
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_missing_confidence")
	if answer.confidence < reject_threshold:
		return GuardrailDecision("uncertain", uncertain_action, "guardrail_low_confidence")
	return GuardrailDecision("reject" if answer.value >= reject_threshold else "allow", "reject" if answer.value >= reject_threshold else "allow", "guardrail_decision")
