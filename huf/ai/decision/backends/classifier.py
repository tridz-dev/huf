"""Provider-neutral classifier Decision Runtime backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, DeploymentSpec, QuestionKind

_DEFAULT_CAPABILITIES = DecisionCapabilities(primitives=frozenset({QuestionKind.SELECT, QuestionKind.JUDGE}), parallel_questions=True, probabilities=False, confidence=True, input_modalities=frozenset({"text", "json"}))


class ClassifierBackend:
	"""Adapt a deterministic classifier callable to the normalized HUF contract."""

	def __init__(
		self,
		classifier: Callable[[Any, Any], Any] | None = None,
		*,
		model: str = "Local Classifier v1",
		identity: DecisionIdentity | None = None,
		capabilities: DecisionCapabilities | None = None,
	):
		self.classifier = classifier
		self.identity = identity or DecisionIdentity(model_class="Classifier", model_family="Local", canonical_model=model, canonical_version="1")
		self._capabilities = capabilities or _DEFAULT_CAPABILITIES

	@classmethod
	def adapter_id(cls) -> str:
		return "classifier"

	@classmethod
	def from_deployment(cls, spec: DeploymentSpec, transport: Any = None) -> "ClassifierBackend":
		"""Deployment-driven instantiation for identity/capabilities only.

		The classifier callable is caller business logic, not deployment configuration, so it
		cannot be derived from ``spec``; an instance built this way carries the deployment's
		identity/capabilities (so persistence resolves against the right ``Decision Model`` row)
		but ``evaluate`` raises until a classifier is supplied by constructing directly with one.
		No network transport is needed; ``transport`` is accepted and ignored.
		"""
		return cls(identity=spec.identity, capabilities=spec.effective_capabilities)

	def capabilities(self) -> DecisionCapabilities:
		return self._capabilities

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		if self.classifier is None:
			raise RuntimeError(
				"ClassifierBackend has no classifier callable configured -- from_deployment() "
				"supplies identity/capabilities only; construct with a classifier callable to evaluate."
			)
		answers = {}
		for question in request.policy.questions:
			value = self.classifier(request.state, question)
			confidence = 1.0
			if isinstance(value, tuple) and len(value) == 2:
				value, confidence = value
			# Emitting a confidence value when self._capabilities.confidence is False would make
			# DecisionRuntime._normalize_response reject the answer as INVALID_RESPONSE.
			answers[question.id] = DecisionAnswer(question.id, question.kind, value, confidence=float(confidence) if self._capabilities.confidence else None)
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
