"""Jev/System One semantic backend with provider transport kept injectable."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
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


class JevTransport(Protocol):
	def __call__(self, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]: ...


class JevSystemOneBackend:
	"""Translate HUF primitives to Jev ``noul``, ``choice``, and ``score``."""

	def __init__(
		self,
		*,
		transport: JevTransport | None = None,
		provider: str = "OpenCode Zen",
		deployment: str = "Jev 1.13 @ OpenCode Zen",
		provider_model_id: str = "jev-1.13-free",
	):
		self.transport = transport or self._unconfigured_transport
		self.identity = DecisionIdentity(
			model_class="System One",
			model_family="Jev",
			canonical_model="Jev 1.13",
			canonical_version="1.13",
			provider=provider,
			deployment=deployment,
			provider_model_id=provider_model_id,
		)

	@classmethod
	def adapter_id(cls) -> str:
		return "jev_system_one"

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
			"state": request.state if isinstance(request.state, str) else json.dumps(request.state, ensure_ascii=False),
			"questions": {question.id: self._question_payload(question) for question in request.policy.questions},
		}
		try:
			status_code, raw = self.transport(payload)
		except TimeoutError:
			return self._failure(request, DecisionStatus.TIMEOUT)
		except PermissionError:
			return self._failure(request, DecisionStatus.AUTHENTICATION_FAILED)
		except Exception:
			return self._failure(request, DecisionStatus.UNAVAILABLE)
		if status_code in (401, 403):
			return self._failure(request, DecisionStatus.AUTHENTICATION_FAILED)
		if status_code == 429:
			return self._failure(request, DecisionStatus.RATE_LIMITED)
		if status_code >= 500:
			return self._failure(request, DecisionStatus.UNAVAILABLE)
		if status_code < 200 or status_code >= 300 or not isinstance(raw, Mapping):
			return self._failure(request, DecisionStatus.INVALID_RESPONSE)
		try:
			answers = {
				question.id: self._normalize_answer(question, raw["answers"][question.id])
				for question in request.policy.questions
			}
			usage_data = raw.get("usage") or {}
			usage = DecisionUsage(
				input_tokens=usage_data.get("input_tokens"),
				output_tokens=usage_data.get("output_tokens"),
			)
		except (KeyError, TypeError, ValueError, IndexError):
			return self._failure(request, DecisionStatus.INVALID_RESPONSE)
		return DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers=answers,
			identity=self.identity,
			backend_adapter=self.adapter_id(),
			requested_model=self.identity.canonical_model,
			requested_model_version=self.identity.canonical_version,
			resolved_model=self.identity.canonical_model,
			resolved_model_version=self.identity.canonical_version,
			usage=usage,
		)

	@staticmethod
	def _unconfigured_transport(payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
		"""Registry-safe default; deployment resolution must inject provider transport."""
		raise ConnectionError("Jev deployment transport is not configured")

	def _question_payload(self, question) -> dict[str, Any]:
		if question.kind == QuestionKind.JUDGE:
			return {"type": "noul", "instructions": question.instructions}
		if question.kind == QuestionKind.SELECT:
			return {
				"type": "choice",
				"instructions": question.instructions,
				"criteria": {option.id: option.description for option in question.options},
			}
		return {
			"type": "score",
			"instructions": question.instructions,
			"criteria": [option.description or option.id for option in question.options],
		}

	def _normalize_answer(self, question, raw: Mapping[str, Any]) -> DecisionAnswer:
		if not isinstance(raw, Mapping):
			raise ValueError("Jev answer must be an object")
		confidence = raw.get("confidence")
		probabilities = raw.get("probabilities")
		if probabilities is not None and not isinstance(probabilities, Mapping):
			raise ValueError("Jev probabilities must be an object")
		if question.kind == QuestionKind.JUDGE:
			return DecisionAnswer(question.id, question.kind, float(raw["noul"]), confidence=confidence)
		if question.kind == QuestionKind.SELECT:
			return DecisionAnswer(
				question.id, question.kind, str(raw["choice"]),
				probabilities=dict(probabilities) if probabilities is not None else None,
				confidence=confidence,
			)
		levels = list(question.options)
		if probabilities:
			index = max(probabilities, key=lambda key: float(probabilities[key]))
		else:
			index = str(round(float(raw["score"])))
		if not str(index).isdigit() or int(index) >= len(levels):
			raise ValueError("Jev score level is outside the HUF rubric")
		mapped_probabilities = {
			levels[int(key)].id: float(value)
			for key, value in (probabilities or {}).items()
			if str(key).isdigit() and int(key) < len(levels)
		}
		return DecisionAnswer(
			question.id, question.kind, levels[int(index)].id,
			probabilities=mapped_probabilities or None,
			confidence=confidence,
		)

	def _failure(self, request: DecisionBackendRequest, status: DecisionStatus) -> DecisionResponse:
		return DecisionResponse(status=status, identity=self.identity, backend_adapter=self.adapter_id())
