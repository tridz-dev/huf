"""Deterministic offline backend for runtime development and conformance."""

from __future__ import annotations

from typing import Mapping

from huf.ai.decision.types import (
	DecisionAnswer,
	DecisionBackendRequest,
	DecisionCapabilities,
	DecisionResponse,
	DecisionStatus,
	DecisionUsage,
	QuestionKind,
)


class FakeDecisionBackend:
	"""Answer each primitive deterministically without network or provider dependencies."""

	def __init__(
		self,
		*,
		answers: Mapping[str, DecisionAnswer] | None = None,
		status: DecisionStatus = DecisionStatus.SUCCESS,
		capabilities: DecisionCapabilities | None = None,
	):
		self._answers = dict(answers or {})
		self._status = status
		self._capabilities = capabilities or DecisionCapabilities(
			primitives=frozenset(QuestionKind),
			parallel_questions=True,
			probabilities=True,
			confidence=True,
			input_modalities=frozenset({"text", "json"}),
		)
		self.call_count = 0
		self.last_request: DecisionBackendRequest | None = None

	@classmethod
	def adapter_id(cls) -> str:
		return "fake"

	def capabilities(self) -> DecisionCapabilities:
		return self._capabilities

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse:
		self.call_count += 1
		self.last_request = request
		if self._status != DecisionStatus.SUCCESS:
			return DecisionResponse(
				status=self._status,
				identity=request.identity,
				backend_adapter=self.adapter_id(),
				requested_model=request.identity.canonical_model,
				requested_model_version=request.identity.canonical_version,
			)
		answers = {}
		for question in request.policy.questions:
			answer = self._answers.get(question.id)
			if answer is None:
				if question.kind == QuestionKind.SELECT:
					value = question.options[0].id if question.options else "none"
					probabilities = {option.id: float(option.id == value) for option in question.options}
				elif question.kind == QuestionKind.SCORE:
					value = question.options[0].id
					probabilities = {option.id: float(option.id == value) for option in question.options}
				else:
					value = 0.5
					probabilities = None
				answer = DecisionAnswer(
					question_id=question.id,
					kind=question.kind,
					value=value,
					probabilities=probabilities,
					confidence=1.0,
				)
			else:
				pass
			answers[question.id] = answer
		return DecisionResponse(
			status=DecisionStatus.SUCCESS,
			answers=answers,
			identity=request.identity,
			backend_adapter=self.adapter_id(),
			requested_model=request.identity.canonical_model,
			requested_model_version=request.identity.canonical_version,
			resolved_model=request.identity.canonical_model,
			resolved_model_version=request.identity.canonical_version,
			usage=DecisionUsage(),
		)

	def healthcheck(self) -> bool:
		return True
