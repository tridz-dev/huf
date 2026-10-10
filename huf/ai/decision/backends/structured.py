"""Provider-neutral structured LLM decision backend."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from huf.ai.decision.types import (
	DecisionAnswer,
	DecisionBackendRequest,
	DecisionCapabilities,
	DecisionIdentity,
	DecisionResponse,
	DecisionStatus,
	DecisionUsage,
	QuestionKind,
)


class StructuredTransport(Protocol):
	def __call__(self, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]: ...


class StructuredLLMBackend:
	"""Adapt a JSON-schema-capable model to the normalized decision contract."""

	def __init__(
		self,
		*,
		transport: StructuredTransport | None = None,
		provider: str = "structured-provider",
		deployment: str = "structured-llm-default",
		provider_model_id: str = "structured-llm",
	):
		self.transport = transport or self._unconfigured_transport
		self.identity = DecisionIdentity(
			model_class="Structured LLM",
			model_family="Structured LLM",
			canonical_model="Structured LLM",
			canonical_version="1",
			provider=provider,
			deployment=deployment,
			provider_model_id=provider_model_id,
		)

	@classmethod
	def adapter_id(cls) -> str:
		return "structured_llm"

	def capabilities(self) -> DecisionCapabilities:
		return DecisionCapabilities(
			primitives=frozenset(QuestionKind),
			parallel_questions=True,
			probabilities=True,
			confidence=True,
			input_modalities=frozenset({"text", "json"}),
		)

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		payload = {
			"model": self.identity.provider_model_id,
			"state": request.state,
			"questions": {
				question.id: {
					"kind": question.kind.value,
					"instructions": question.instructions,
					"options": [{"id": option.id, "description": option.description} for option in question.options],
				}
				for question in request.policy.questions
			},
		}
		try:
			status_code, raw = self.transport(payload)
		except TimeoutError:
			return self._failure(DecisionStatus.TIMEOUT)
		except PermissionError:
			return self._failure(DecisionStatus.AUTHENTICATION_FAILED)
		except Exception:
			return self._failure(DecisionStatus.UNAVAILABLE)
		if status_code in (401, 403):
			return self._failure(DecisionStatus.AUTHENTICATION_FAILED)
		if status_code == 429:
			return self._failure(DecisionStatus.RATE_LIMITED)
		if status_code >= 500:
			return self._failure(DecisionStatus.UNAVAILABLE)
		if status_code < 200 or status_code >= 300 or not isinstance(raw, Mapping):
			return self._failure(DecisionStatus.INVALID_RESPONSE)
		try:
			answers = {
				question.id: self._normalize_answer(question, raw["answers"][question.id])
				for question in request.policy.questions
			}
			usage = raw.get("usage") or {}
			decision_usage = DecisionUsage(
				input_tokens=usage.get("input_tokens"), output_tokens=usage.get("output_tokens")
			)
		except (KeyError, TypeError, ValueError):
			return self._failure(DecisionStatus.INVALID_RESPONSE)
		return DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers=answers,
			identity=self.identity,
			backend_adapter=self.adapter_id(),
			requested_model=self.identity.canonical_model,
			requested_model_version=self.identity.canonical_version,
			resolved_model=self.identity.canonical_model,
			resolved_model_version=self.identity.canonical_version,
			usage=decision_usage,
		)

	def _normalize_answer(self, question, raw: Mapping[str, Any]) -> DecisionAnswer:
		if not isinstance(raw, Mapping):
			raise ValueError("structured answer must be an object")
		return DecisionAnswer(
			question.id,
			question.kind,
			raw["value"],
			probabilities=raw.get("probabilities"),
			confidence=raw.get("confidence"),
		)

	def _failure(self, status: DecisionStatus) -> DecisionResponse:
		return DecisionResponse(status=status, identity=self.identity, backend_adapter=self.adapter_id())

	@staticmethod
	def _unconfigured_transport(payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
		raise ConnectionError("Structured LLM deployment transport is not configured")
