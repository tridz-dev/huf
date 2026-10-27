"""Redacted Decision Call telemetry records and sink integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from huf.ai.decision.types import CandidateSource, DecisionIdentity, DecisionResponse, DecisionUsage


@dataclass(frozen=True, slots=True)
class DecisionCall:
	"""Normalized audit event; provider-visible state is absent unless explicitly enabled."""

	status: str
	policy_id: str
	policy_version: str | None
	policy_fingerprint: str
	surface: str
	backend_adapter: str | None
	requested_identity: DecisionIdentity
	resolved_identity: DecisionIdentity
	requested_model: str | None
	requested_model_version: str | None
	resolved_model: str | None
	resolved_model_version: str | None
	candidate_ids: tuple[str, ...]
	candidate_source: CandidateSource | None
	candidate_resolver_id: str | None
	deployment_selection_source: str | None = None
	deployment_fallback_count: int = 0
	answers: Mapping[str, Any] = field(default_factory=dict)
	usage: DecisionUsage = field(default_factory=DecisionUsage)
	latency_ms: float | None = None
	state_hash: str | None = None
	state_snapshot: Any | None = None
	gate_result: str | None = None
	policy_fallback_action: str | None = None
	error_code: str | None = None
	deployment_fallback_chain: tuple[str, ...] = ()


TelemetrySink = Callable[[DecisionCall], None]


def make_decision_call(
	request,
	response: DecisionResponse,
	*,
	state_hash: str | None,
	state_snapshot: Any | None = None,
) -> DecisionCall:
	"""Build an audit event without copying execution context or secrets."""
	questions = {item.id: item for item in request.policy.questions}
	return DecisionCall(
		status=response.status.value,
		policy_id=_safe_telemetry_label(request.policy.policy_id) or "unknown",
		policy_version=_safe_telemetry_label(request.policy.version),
		policy_fingerprint=request.policy.fingerprint,
		surface=_safe_telemetry_label(request.surface) or "generic",
		backend_adapter=_safe_telemetry_label(response.backend_adapter),
		requested_identity=response.requested_identity,
		resolved_identity=response.identity,
		requested_model=response.requested_model,
		requested_model_version=response.requested_model_version,
		resolved_model=response.resolved_model,
		resolved_model_version=response.resolved_model_version,
		candidate_ids=tuple(_safe_telemetry_label(item) for item in dict.fromkeys(
			[option.id for question in request.policy.questions if question.id in questions for option in question.options]
			+ [candidate.id for candidate in request.candidates]
		) if _safe_telemetry_label(item) is not None),
		candidate_source=request.candidate_source,
		candidate_resolver_id=_safe_telemetry_label(request.candidate_resolver_id),
		deployment_selection_source=response.deployment_selection_source,
		deployment_fallback_count=response.deployment_fallback_count,
		answers=response.answers,
		usage=response.usage,
		latency_ms=response.latency_ms,
		state_hash=state_hash,
		state_snapshot=state_snapshot,
		gate_result=response.gate_result,
		policy_fallback_action=response.policy_fallback_action,
		error_code=response.error_code,
		deployment_fallback_chain=response.deployment_fallback_chain,
	)


def _safe_telemetry_label(value: str | None) -> str | None:
	if value is None or not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
		return None
	allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._:/@+-"
	if not value.isprintable() or any(char not in allowed for char in value):
		return None
	words = set(value.lower().replace("-", " ").replace("_", " ").split())
	if words & {"token", "secret", "password", "credential", "authorization", "bearer", "apikey", "api"}:
		return None
	return value
