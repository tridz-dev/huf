"""Code-owned gates and closed-candidate integrity checks."""

from __future__ import annotations

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.types import DecisionAnswer, DecisionPolicy, DecisionRequest, QuestionKind


def validate_answer_integrity(request: DecisionRequest, answer: DecisionAnswer) -> None:
	question = next((item for item in request.policy.questions if item.id == answer.question_id), None)
	if question is None or answer.kind != question.kind:
		raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
	if answer.kind == QuestionKind.SELECT:
		allowed = {option.id for option in question.options}
		if request.candidates and not allowed <= {candidate.id for candidate in request.candidates}:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
		if answer.probabilities is not None and not set(answer.probabilities) <= allowed:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
		if answer.value == "none" and question.allow_none:
			return
		if not isinstance(answer.value, str) or answer.value not in allowed:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
	elif answer.kind == QuestionKind.SCORE:
		allowed = {option.id for option in question.options}
		if not isinstance(answer.value, str) or answer.value not in allowed:
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		if answer.probabilities is not None and not set(answer.probabilities) <= allowed:
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)


def evaluate_gate(policy: DecisionPolicy, answers: dict[str, DecisionAnswer]) -> str:
	"""Return accepted, uncertain, or rejected using policy-owned confidence threshold."""
	if policy.minimum_confidence is None:
		return "accepted"
	confidences = [answer.confidence for answer in answers.values() if answer.confidence is not None]
	if len(confidences) != len(answers) or not confidences or min(confidences) < policy.minimum_confidence:
		return "uncertain"
	return "accepted"
