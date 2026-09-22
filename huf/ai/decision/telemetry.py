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
	resolved_model: str | None
	candidate_ids: tuple[str, ...]
	candidate_source: CandidateSource | None
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
		policy_id=request.policy.policy_id,
		policy_version=request.policy.version,
		policy_fingerprint=request.policy.fingerprint,
		surface=request.surface,
		backend_adapter=response.backend_adapter,
		requested_identity=response.requested_identity,
		resolved_identity=response.identity,
		requested_model=response.requested_model,
		resolved_model=response.resolved_model,
		candidate_ids=tuple(dict.fromkeys(
			[option.id for question in request.policy.questions if question.id in questions for option in question.options]
			+ [candidate.id for candidate in request.candidates]
		)),
		candidate_source=request.candidate_source,
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
