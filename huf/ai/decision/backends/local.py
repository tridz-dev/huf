"""Provider-free deterministic local Decision Runtime backend."""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, QuestionKind


class LocalRulesBackend:
	"""Evaluate bounded policies from caller-supplied deterministic rules."""

	def __init__(self, rules: Mapping[str, Any] | None = None, *, model: str = "Local Rules v1"):
		self.rules = dict(rules or {})
		self.identity = DecisionIdentity(model_class="Rules", model_family="Local", canonical_model=model, canonical_version="1")

	@classmethod
	def adapter_id(cls) -> str:
		return "local_rules"

	def capabilities(self) -> DecisionCapabilities:
		return DecisionCapabilities(primitives=frozenset(QuestionKind), parallel_questions=True, probabilities=False, confidence=True, input_modalities=frozenset({"text", "json"}))

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		answers = {}
		for question in request.policy.questions:
			value = self.rules.get(question.id)
			if value is None:
				value = question.options[0].id if question.options else 0.5
			answers[question.id] = DecisionAnswer(question.id, question.kind, value, confidence=1.0)
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
