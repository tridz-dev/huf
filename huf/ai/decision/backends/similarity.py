"""Provider-neutral similarity-based Decision Runtime backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, DeploymentSpec, QuestionKind

_DEFAULT_CAPABILITIES = DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT}), parallel_questions=True, probabilities=True, confidence=True, input_modalities=frozenset({"text", "json"}))


class SimilarityBackend:
	"""Adapt a similarity scorer to normalized HUF selection answers."""

	def __init__(
		self,
		scorer: Callable[[Any, Any, Any], float] | None = None,
		*,
		model: str = "Local Similarity v1",
		identity: DecisionIdentity | None = None,
		capabilities: DecisionCapabilities | None = None,
	):
		self.scorer = scorer
		self.identity = identity or DecisionIdentity(model_class="Similarity", model_family="Local", canonical_model=model, canonical_version="1")
		self._capabilities = capabilities or _DEFAULT_CAPABILITIES

	@classmethod
	def adapter_id(cls) -> str:
		return "similarity"

	@classmethod
	def from_deployment(cls, spec: DeploymentSpec, transport: Any = None) -> "SimilarityBackend":
		"""Deployment-driven instantiation for identity/capabilities only.

		The scorer callable is caller business logic, not deployment configuration, so it cannot
		be derived from ``spec``; an instance built this way carries the deployment's
		identity/capabilities (so persistence resolves against the right ``Decision Model`` row)
		but ``evaluate`` raises until a scorer is supplied by constructing directly with one. No
		network transport is needed; ``transport`` is accepted and ignored.
		"""
		return cls(identity=spec.identity, capabilities=spec.effective_capabilities)

	def capabilities(self) -> DecisionCapabilities:
		return self._capabilities

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		if self.scorer is None:
			raise RuntimeError(
				"SimilarityBackend has no scorer callable configured -- from_deployment() "
				"supplies identity/capabilities only; construct with a scorer callable to evaluate."
			)
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
			# Emitting probabilities/confidence when self._capabilities doesn't declare them
			# would make DecisionRuntime._normalize_response reject the answer as
			# INVALID_RESPONSE.
			answers[question.id] = DecisionAnswer(
				question.id,
				question.kind,
				selected,
				probabilities=probabilities if self._capabilities.probabilities else None,
				confidence=probabilities[selected] if self._capabilities.confidence else None,
			)
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
