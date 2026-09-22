"""Provider-neutral decision orchestration; no provider transport is embedded here."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.gating import evaluate_gate, validate_answer_integrity
from huf.ai.decision.policy import validate_policy
from huf.ai.decision.registry import resolve_backend
from huf.ai.decision.state import prepare_state
from huf.ai.decision.telemetry import TelemetrySink, make_decision_call
from huf.ai.decision.types import (
	DecisionAnswer,
	DecisionBackendRequest,
	DecisionCapabilities,
	CandidateSource,
	DecisionIdentity,
	DecisionRequest,
	DecisionResponse,
	DecisionStatus,
	QuestionKind,
)


class DecisionRuntime:
	"""Validate and execute one batched policy request using a registered backend."""

	def __init__(self, *, telemetry_sink: TelemetrySink | None = None):
		self.telemetry_sink = telemetry_sink

	def evaluate(self, request: DecisionRequest, backend: Any | str) -> DecisionResponse:
		started = time.monotonic()
		state_hash = None
		adapter = None
		policy = request.policy
		prepared = None
		try:
			policy = validate_policy(request.policy)
			request = replace(request, policy=policy)
			backend = resolve_backend(backend) if isinstance(backend, str) else backend
			adapter = backend.adapter_id() if callable(getattr(backend, "adapter_id", None)) else None
			capabilities: DecisionCapabilities = backend.capabilities()
			self._validate_capabilities(request, capabilities)
			prepared = prepare_state(request, policy, capabilities)
			state_hash = prepared.sha256
			self._validate_request_candidates(request)
			backend_request = DecisionBackendRequest(
				policy=policy,
				state=prepared.value,
				identity=request.identity,
				surface=request.surface,
				candidates=request.candidates,
				candidate_source=request.candidate_source,
				modalities=request.modalities,
			)
			response = backend.evaluate(backend_request)
			response = self._normalize_response(request, response, capabilities, adapter)
			gate_result = evaluate_gate(policy, dict(response.answers))
			response = replace(
				response,
				gate_result=gate_result,
				latency_ms=response.latency_ms if response.latency_ms is not None else (time.monotonic() - started) * 1000,
			)
		except DecisionError as exc:
			response = self._failure_response(exc, request, adapter)
		except Exception:
			# Provider/library exception text may contain sensitive request or credential data.
			exc = DecisionError(DecisionErrorCode.FAILED)
			response = self._failure_response(exc, request, adapter)
		response = replace(response, latency_ms=(time.monotonic() - started) * 1000)
		self._emit(
			request,
			response,
			state_hash,
			prepared.value if prepared is not None and policy.store_state else None,
		)
		return response

	def apply_policy_fallback(
		self,
		response: DecisionResponse,
		policy,
		*,
		deployments_exhausted: bool,
	) -> DecisionResponse:
		"""Record policy fallback only after the deployment resolver has exhausted candidates."""
		if not deployments_exhausted:
			raise ValueError("Policy fallback cannot run before deployment options are exhausted")
		if response.status == DecisionStatus.SUCCESS:
			raise ValueError("Policy fallback applies only after decision execution failure")
		return replace(response, policy_fallback_action=policy.fallback_action)

	def _validate_capabilities(self, request: DecisionRequest, capabilities: DecisionCapabilities) -> None:
		unsupported = {question.kind for question in request.policy.questions} - capabilities.primitives
		if unsupported:
			raise DecisionError(DecisionErrorCode.UNSUPPORTED_CAPABILITY)
		if len(request.policy.questions) > 1 and not capabilities.parallel_questions:
			# Runtime deliberately does not fan out: a single DecisionRequest is one unit of work.
			raise DecisionError(DecisionErrorCode.UNSUPPORTED_CAPABILITY)
		if capabilities.max_candidates_per_select is not None:
			if len({candidate.id for candidate in request.candidates}) > capabilities.max_candidates_per_select:
				raise DecisionError(DecisionErrorCode.CANDIDATE_LIMIT_EXCEEDED)
			if any(
				question.kind == QuestionKind.SELECT
				and len(question.options) > capabilities.max_candidates_per_select
				for question in request.policy.questions
			):
				raise DecisionError(DecisionErrorCode.CANDIDATE_LIMIT_EXCEEDED)

	def _validate_request_candidates(self, request: DecisionRequest) -> None:
		select_questions = [question for question in request.policy.questions if question.kind == QuestionKind.SELECT]
		candidate_ids = [candidate.id for candidate in request.candidates]
		if len(candidate_ids) != len(set(candidate_ids)):
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
		if select_questions and request.candidate_source is None:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID, "Select candidates require provenance")
		if request.candidates and request.candidate_source == CandidateSource.POLICY_OPTIONS:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
		if request.candidates:
			eligible_ids = set(candidate_ids)
			for question in request.policy.questions:
				if question.kind == QuestionKind.SELECT and not {option.id for option in question.options} <= eligible_ids:
					raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)

	def _normalize_response(
		self,
		request: DecisionRequest,
		response: DecisionResponse,
		capabilities: DecisionCapabilities,
		adapter: str | None,
	) -> DecisionResponse:
		if not isinstance(response, DecisionResponse):
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		if not isinstance(response.status, DecisionStatus):
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		if response.status != DecisionStatus.SUCCESS:
			error_code = {
				DecisionStatus.UNAVAILABLE: DecisionErrorCode.PROVIDER_UNAVAILABLE,
				DecisionStatus.TIMEOUT: DecisionErrorCode.TIMEOUT,
				DecisionStatus.RATE_LIMITED: DecisionErrorCode.RATE_LIMITED,
				DecisionStatus.UNSUPPORTED: DecisionErrorCode.UNSUPPORTED_CAPABILITY,
				DecisionStatus.INVALID_RESPONSE: DecisionErrorCode.INVALID_RESPONSE,
				DecisionStatus.FAILED: DecisionErrorCode.FAILED,
			}.get(response.status, DecisionErrorCode.FAILED)
			return replace(
				response,
				answers={},
				identity=_merge_identity(request.identity, response.identity),
				requested_identity=request.identity,
				backend_adapter=adapter or response.backend_adapter,
				error_code=error_code.value,
				policy_fallback_action=None,
				usage=replace(
					response.usage,
					cost_source=response.usage.cost_source
					if response.usage.cost_source in {"provider_reported", "estimated"}
					else None,
				),
				deployment_selection_source=(
					response.deployment_selection_source
					if response.deployment_selection_source in {"explicit", "primary", "health", "priority", "failover"}
					else None
				),
				deployment_fallback_chain=tuple(
					item[:128] for item in response.deployment_fallback_chain
					if isinstance(item, str) and item and len(item) <= 128 and item.isprintable()
				)[:16],
			)
		if set(response.answers) != {question.id for question in request.policy.questions}:
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		normalized_answers = {}
		for answer_key, answer in response.answers.items():
			if not isinstance(answer, DecisionAnswer):
				raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
			if answer_key != answer.question_id:
				raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
			validate_answer_integrity(request, answer)
			if answer.probabilities is not None and not capabilities.probabilities:
				raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
			if answer.confidence is not None and not capabilities.confidence:
				raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
			# Provider/raw payloads are never part of the normalized caller or audit contract.
			normalized_answers[answer.question_id] = replace(answer, backend_metadata={})
		return replace(
			response,
			answers=normalized_answers,
			identity=_merge_identity(request.identity, response.identity),
			requested_identity=request.identity,
			backend_adapter=adapter or response.backend_adapter,
			requested_model=response.requested_model or request.identity.canonical_model,
			resolved_model=response.resolved_model or request.identity.canonical_model,
			usage=replace(
				response.usage,
				cost_source=response.usage.cost_source if response.usage.cost_source in {"provider_reported", "estimated"} else None,
			),
			deployment_selection_source=(
				response.deployment_selection_source
				if response.deployment_selection_source in {"explicit", "primary", "health", "priority", "failover"}
				else None
			),
			deployment_fallback_chain=tuple(
				item[:128] for item in response.deployment_fallback_chain
				if isinstance(item, str) and item and len(item) <= 128 and item.isprintable()
			)[:16],
		)

	def _failure_response(self, error: DecisionError, request: DecisionRequest, adapter: str | None) -> DecisionResponse:
		status = {
			DecisionErrorCode.BACKEND_NOT_REGISTERED: DecisionStatus.UNAVAILABLE,
			DecisionErrorCode.PROVIDER_UNAVAILABLE: DecisionStatus.UNAVAILABLE,
			DecisionErrorCode.TIMEOUT: DecisionStatus.TIMEOUT,
			DecisionErrorCode.RATE_LIMITED: DecisionStatus.RATE_LIMITED,
			DecisionErrorCode.UNSUPPORTED_CAPABILITY: DecisionStatus.UNSUPPORTED,
			DecisionErrorCode.INVALID_RESPONSE: DecisionStatus.INVALID_RESPONSE,
		}.get(error.code, DecisionStatus.FAILED)
		return DecisionResponse(
			status=status,
			identity=request.identity,
			requested_identity=request.identity,
			backend_adapter=adapter,
			requested_model=request.identity.canonical_model,
			error_code=error.code.value,
		)

	def _emit(
		self,
		request: DecisionRequest,
		response: DecisionResponse,
		state_hash: str | None,
		state_snapshot: Any | None,
	) -> None:
		if self.telemetry_sink is None:
			return
		try:
			self.telemetry_sink(
				make_decision_call(
					request,
					response,
					state_hash=state_hash,
					state_snapshot=state_snapshot,
				)
			)
		except Exception:
			# Audit sink failure must not rewrite the decision result; caller can monitor sink health.
			return


def _merge_identity(requested: DecisionIdentity, resolved: DecisionIdentity) -> DecisionIdentity:
	"""Preserve canonical request identity while taking resolved serving metadata from backend."""
	return DecisionIdentity(
		model_class=requested.model_class or resolved.model_class,
		model_family=requested.model_family or resolved.model_family,
		canonical_model=requested.canonical_model or resolved.canonical_model,
		canonical_version=requested.canonical_version or resolved.canonical_version,
		provider=resolved.provider or requested.provider,
		deployment=resolved.deployment or requested.deployment,
		provider_model_id=resolved.provider_model_id or requested.provider_model_id,
	)
