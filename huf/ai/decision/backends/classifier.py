"""Provider-neutral classifier Decision Runtime backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, QuestionKind


class ClassifierBackend:
	"""Adapt a deterministic classifier callable to the normalized HUF contract."""

	def __init__(self, classifier: Callable[[Any, Any], Any], *, model: str = "Local Classifier v1"):
		self.classifier = classifier
		self.identity = DecisionIdentity(model_class="Classifier", model_family="Local", canonical_model=model, canonical_version="1")

	@classmethod
	def adapter_id(cls) -> str:
		return "classifier"

	def capabilities(self) -> DecisionCapabilities:
		return DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT, QuestionKind.JUDGE}), parallel_questions=True, probabilities=False, confidence=True, input_modalities=frozenset({"text", "json"}))

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		answers = {}
		for question in request.policy.questions:
			value = self.classifier(request.state, question)
			confidence = 1.0
			if isinstance(value, tuple) and len(value) == 2:
				value, confidence = value
			answers[question.id] = DecisionAnswer(question.id, question.kind, value, confidence=float(confidence))
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
