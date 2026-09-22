"""Provider-neutral backend protocol."""

from __future__ import annotations

from typing import Protocol

from huf.ai.decision.types import DecisionBackendRequest, DecisionCapabilities, DecisionResponse


class DecisionBackend(Protocol):
	"""Translate one normalized batched request to and from a decision engine."""

	@classmethod
	def adapter_id(cls) -> str: ...

	def capabilities(self) -> DecisionCapabilities: ...

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse: ...

	def healthcheck(self) -> bool: ...
