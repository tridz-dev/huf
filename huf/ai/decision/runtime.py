"""Provider-neutral decision orchestration; no provider transport is embedded here."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from huf.ai.decision.errors import DecisionError, DecisionErrorCode
from huf.ai.decision.deployment import DeploymentChain
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

	def evaluate(
		self,
		request: DecisionRequest,
		backend: Any | str,
		*,
		_deployment_metadata: tuple[str, int, tuple[str, ...]] | None = None,
	) -> DecisionResponse:
		started = time.monotonic()
		state_hash = None
		adapter = None
		policy = request.policy
		prepared = None
		try:
			policy = validate_policy(request.policy)
			request = replace(request, policy=policy, identity=_sanitize_identity(request.identity))
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
				candidate_resolver_id=request.candidate_resolver_id,
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
		if _deployment_metadata is not None:
			selection_source, fallback_count, fallback_chain = _deployment_metadata
			response = replace(
				response,
				deployment_selection_source=selection_source,
				deployment_fallback_count=fallback_count,
				deployment_fallback_chain=fallback_chain,
			)
		self._emit(
			request,
			response,
			state_hash,
			prepared.value if prepared is not None and policy.store_state else None,
		)
		return response

	def evaluate_deployment_chain(self, request: DecisionRequest, chain: DeploymentChain, deadline: float | None = None) -> DecisionResponse:
		"""Try eligible deployments in deterministic order without changing policy identity.

		Args:
			request: The decision request.
			chain: The ordered deployment chain.
			deadline: Monotonic timestamp (seconds); stops trying candidates after this time, returns TIMEOUT.
		"""
		if not chain.candidates:
			return self.evaluate(request, object(), _deployment_metadata=("priority", 0, ()))
		labels = chain.fallback_chain
		last = None
		for index, candidate in enumerate(chain.candidates):
			# Check deadline before attempting this candidate
			if deadline is not None and time.monotonic() >= deadline:
				# Return TIMEOUT with partial fallback chain
				if last is not None:
					# Use the last response as base, update status to TIMEOUT
					return replace(
						last,
						status=DecisionStatus.TIMEOUT,
						error_code=DecisionErrorCode.TIMEOUT.value,
					)
				else:
					# No candidates evaluated yet; create TIMEOUT response
					return DecisionResponse(
						status=DecisionStatus.TIMEOUT,
						identity=request.identity,
						requested_identity=request.identity,
						requested_model=request.identity.canonical_model,
						requested_model_version=request.identity.canonical_version,
						error_code=DecisionErrorCode.TIMEOUT.value,
						deployment_fallback_count=index,
						deployment_fallback_chain=labels[:index],
					)
			selection = "failover" if index else chain.selection_source
			last = self.evaluate(
				request,
				candidate.backend,
				_deployment_metadata=(selection, index, labels),
			)
			if last.status == DecisionStatus.SUCCESS:
				return last
		return last

	def apply_policy_fallback(
		self,
		request: DecisionRequest,
		response: DecisionResponse,
		*,
		deployments_exhausted: bool,
	) -> DecisionResponse:
		"""Record policy fallback only after the deployment resolver has exhausted candidates."""
		if not deployments_exhausted:
			raise ValueError("Policy fallback cannot run before deployment options are exhausted")
		if response.status == DecisionStatus.SUCCESS:
			raise ValueError("Policy fallback applies only after decision execution failure")
		policy = validate_policy(request.policy)
		request = replace(request, policy=policy, identity=_sanitize_identity(request.identity))
		fallback_response = replace(response, policy_fallback_action=policy.fallback_action)
		self._emit(request, fallback_response, None, None)
		return fallback_response

	def _validate_capabilities(self, request: DecisionRequest, capabilities: DecisionCapabilities) -> None:
		unsupported = {question.kind for question in request.policy.questions} - capabilities.primitives
		if unsupported:
			raise DecisionError(DecisionErrorCode.UNSUPPORTED_CAPABILITY)
		if len(request.policy.questions) > 1 and not capabilities.parallel_questions:
			# Runtime deliberately does not fan out: a single DecisionRequest is one unit of work.
			raise DecisionError(DecisionErrorCode.UNSUPPORTED_CAPABILITY)
		if request.policy.minimum_confidence is not None and not capabilities.confidence:
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
		if request.candidate_source is not None and not isinstance(request.candidate_source, CandidateSource):
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID, "Candidate provenance must use CandidateSource")
		if request.candidates and request.candidate_source == CandidateSource.POLICY_OPTIONS:
			raise DecisionError(DecisionErrorCode.CANDIDATE_INVALID)
		if request.candidates and request.candidate_source != CandidateSource.POLICY_OPTIONS:
			if _safe_label(request.candidate_resolver_id) is None:
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
				DecisionStatus.AUTHENTICATION_FAILED: DecisionErrorCode.AUTHENTICATION_FAILED,
				DecisionStatus.TIMEOUT: DecisionErrorCode.TIMEOUT,
				DecisionStatus.RATE_LIMITED: DecisionErrorCode.RATE_LIMITED,
				DecisionStatus.UNSUPPORTED: DecisionErrorCode.UNSUPPORTED_CAPABILITY,
				DecisionStatus.INVALID_RESPONSE: DecisionErrorCode.INVALID_RESPONSE,
				DecisionStatus.FAILED: DecisionErrorCode.FAILED,
			}.get(response.status, DecisionErrorCode.FAILED)
			return replace(
				response,
				answers={},
				identity=_resolved_identity(request.identity, response.identity),
				requested_identity=request.identity,
				backend_adapter=_safe_label(adapter or response.backend_adapter),
				error_code=error_code.value,
				requested_model=request.identity.canonical_model,
				requested_model_version=request.identity.canonical_version,
				resolved_model=_safe_label(response.identity.canonical_model or request.identity.canonical_model),
				resolved_model_version=_safe_label(response.identity.canonical_version or request.identity.canonical_version),
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
				deployment_fallback_chain=_safe_fallback_chain(response.deployment_fallback_chain),
			)
		if not isinstance(response.answers, Mapping):
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		if set(response.answers) != {question.id for question in request.policy.questions}:
			raise DecisionError(DecisionErrorCode.INVALID_RESPONSE)
		normalized_answers = {}
		for question in request.policy.questions:
			answer_key = question.id
			answer = response.answers[answer_key]
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
			identity=_resolved_identity(request.identity, response.identity),
			requested_identity=request.identity,
			backend_adapter=_safe_label(adapter or response.backend_adapter),
			requested_model=request.identity.canonical_model,
			requested_model_version=request.identity.canonical_version,
			resolved_model=_safe_label(response.identity.canonical_model or request.identity.canonical_model),
			resolved_model_version=_safe_label(response.identity.canonical_version or request.identity.canonical_version),
			usage=replace(
				response.usage,
				cost_source=response.usage.cost_source if response.usage.cost_source in {"provider_reported", "estimated"} else None,
			),
			deployment_selection_source=(
				response.deployment_selection_source
				if response.deployment_selection_source in {"explicit", "primary", "health", "priority", "failover"}
				else None
			),
			deployment_fallback_chain=_safe_fallback_chain(response.deployment_fallback_chain),
		)

	def _failure_response(self, error: DecisionError, request: DecisionRequest, adapter: str | None) -> DecisionResponse:
		status = {
			DecisionErrorCode.BACKEND_NOT_REGISTERED: DecisionStatus.UNAVAILABLE,
			DecisionErrorCode.PROVIDER_UNAVAILABLE: DecisionStatus.UNAVAILABLE,
			DecisionErrorCode.AUTHENTICATION_FAILED: DecisionStatus.AUTHENTICATION_FAILED,
			DecisionErrorCode.TIMEOUT: DecisionStatus.TIMEOUT,
			DecisionErrorCode.RATE_LIMITED: DecisionStatus.RATE_LIMITED,
			DecisionErrorCode.UNSUPPORTED_CAPABILITY: DecisionStatus.UNSUPPORTED,
			DecisionErrorCode.INVALID_RESPONSE: DecisionStatus.INVALID_RESPONSE,
		}.get(error.code, DecisionStatus.FAILED)
		return DecisionResponse(
			status=status,
			identity=request.identity,
			requested_identity=request.identity,
			backend_adapter=_safe_label(adapter),
			requested_model=request.identity.canonical_model,
			requested_model_version=request.identity.canonical_version,
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


def _resolved_identity(requested: DecisionIdentity, resolved: DecisionIdentity) -> DecisionIdentity:
	"""Return the actual resolved model/deployment, falling back to requested values when absent."""
	return DecisionIdentity(
		model_class=_safe_label(resolved.model_class or requested.model_class),
		model_family=_safe_label(resolved.model_family or requested.model_family),
		canonical_model=_safe_label(resolved.canonical_model or requested.canonical_model),
		canonical_version=_safe_label(resolved.canonical_version or requested.canonical_version),
		provider=_safe_label(resolved.provider or requested.provider),
		deployment=_safe_label(resolved.deployment or requested.deployment),
		provider_model_id=_safe_label(resolved.provider_model_id or requested.provider_model_id),
	)


def _sanitize_identity(identity: DecisionIdentity) -> DecisionIdentity:
	"""Keep bounded identity labels while preventing diagnostic credential fields leaking."""
	return DecisionIdentity(**{
		field_name: _safe_label(getattr(identity, field_name))
		for field_name in (
			"model_class", "model_family", "canonical_model", "canonical_version",
			"provider", "deployment", "provider_model_id",
		)
	})


def _safe_fallback_chain(chain: tuple[str, ...]) -> tuple[str, ...]:
	return tuple(label for item in chain if (label := _safe_label(item)) is not None)[:16]


def _safe_label(value: Any) -> str | None:
	if value is None:
		return None
	allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._:/@+-"
	if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii() or not value.isprintable():
		return None
	if any(char not in allowed for char in value):
		return None
	words = set(value.lower().replace("-", " ").replace("_", " ").split())
	if words & {"token", "secret", "password", "credential", "authorization", "bearer", "apikey"}:
		return None
	return value
