"""Provider-neutral similarity-based Decision Runtime backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, QuestionKind


class SimilarityBackend:
	"""Adapt a similarity scorer to normalized HUF selection answers."""

	def __init__(self, scorer: Callable[[Any, Any, Any], float], *, model: str = "Local Similarity v1"):
		self.scorer = scorer
		self.identity = DecisionIdentity(model_class="Similarity", model_family="Local", canonical_model=model, canonical_version="1")

	@classmethod
	def adapter_id(cls) -> str:
		return "similarity"

	def capabilities(self) -> DecisionCapabilities:
		return DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), parallel_questions=True, probabilities=True, confidence=True, input_modalities=frozenset({"text", "json"}))

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		answers = {}
		for question in request.policy.questions:
			if question.kind != QuestionKind.SELECT:
				continue
			scores = {option.id: float(self.scorer(request.state, question, option)) for option in question.options}
			if not scores:
				return DecisionResponse(status=DecisionStatus.INVALID_RESPONSE, identity=self.identity, backend_adapter=self.adapter_id())
			selected = max(scores, key=scores.get)
			total = sum(max(0.0, score) for score in scores.values()) or 1.0
			probabilities = {key: max(0.0, value) / total for key, value in scores.items()}
			answers[question.id] = DecisionAnswer(question.id, question.kind, selected, probabilities=probabilities, confidence=probabilities[selected])
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
