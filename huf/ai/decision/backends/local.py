"""Provider-free deterministic local Decision Runtime backend."""

from __future__ import annotations

from typing import Any, Mapping

from huf.ai.decision.types import DecisionAnswer, DecisionBackendRequest, DecisionCapabilities, DecisionIdentity, DecisionResponse, DecisionStatus, DecisionUsage, DeploymentSpec, QuestionKind

_DEFAULT_CAPABILITIES = DecisionCapabilities(primitives=frozenset(QuestionKind), parallel_questions=True, probabilities=False, confidence=True, input_modalities=frozenset({"text", "json"}))


class LocalRulesBackend:
	"""Evaluate bounded policies from caller-supplied deterministic rules."""

	def __init__(
		self,
		rules: Mapping[str, Any] | None = None,
		*,
		model: str = "Local Rules v1",
		identity: DecisionIdentity | None = None,
		capabilities: DecisionCapabilities | None = None,
	):
		self.rules = dict(rules or {})
		self.identity = identity or DecisionIdentity(model_class="Rules", model_family="Local", canonical_model=model, canonical_version="1")
		self._capabilities = capabilities or _DEFAULT_CAPABILITIES

	@classmethod
	def adapter_id(cls) -> str:
		return "local_rules"

	@classmethod
	def from_deployment(cls, spec: DeploymentSpec, transport: Any = None) -> "LocalRulesBackend":
		"""Deployment-driven instantiation: identity/capabilities come from ``spec`` instead of
		the "Local Rules v1" hardcoded default, so persistence (``Decision Call.decision_model``)
		works against whatever ``Decision Model`` row actually backs this deployment. No network
		transport is needed here; ``transport`` is accepted (for the registry.resolve_backend
		contract) and ignored. ``rules`` is per-call caller state, not deployment configuration,
		so an instance built this way starts with no rules (each question falls back to its
		default in ``evaluate``) -- callers needing specific rules still construct directly.
		"""
		return cls(identity=spec.identity, capabilities=spec.effective_capabilities)

	def capabilities(self) -> DecisionCapabilities:
		return self._capabilities

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		# Emitting confidence when self._capabilities.confidence is False would make
		# DecisionRuntime._normalize_response reject the answer as INVALID_RESPONSE -- a real
		# gap once from_deployment (above) started passing through a deployment's actual
		# effective_capabilities instead of the always-True hardcoded default.
		confidence = 1.0 if self._capabilities.confidence else None
		answers = {}
		for question in request.policy.questions:
			value = self.rules.get(question.id)
			if value is None:
				value = question.options[0].id if question.options else 0.5
			answers[question.id] = DecisionAnswer(question.id, question.kind, value, confidence=confidence)
		return DecisionResponse(status=DecisionStatus.SUCCESS, answers=answers, identity=self.identity, backend_adapter=self.adapter_id(), requested_model=self.identity.canonical_model, requested_model_version=self.identity.canonical_version, resolved_model=self.identity.canonical_model, resolved_model_version=self.identity.canonical_version, usage=DecisionUsage())
