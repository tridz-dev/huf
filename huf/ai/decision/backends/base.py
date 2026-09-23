"""Provider-neutral backend protocol."""

from __future__ import annotations

from typing import Any, Protocol

from huf.ai.decision.types import DecisionBackendRequest, DecisionCapabilities, DecisionResponse


class DecisionBackend(Protocol):
	"""Translate one normalized batched request to and from a decision engine."""

	@classmethod
	def adapter_id(cls) -> str: ...

	def capabilities(self) -> DecisionCapabilities: ...

	def evaluate(self, request: DecisionBackendRequest) -> DecisionResponse: ...

	def healthcheck(self) -> bool: ...

	@classmethod
	def from_deployment(cls, spec: Any, transport: Any) -> DecisionBackend:
		"""Optional classmethod for backends that support deployment-driven instantiation.

		Called by registry.resolve_backend when a deployment spec and transport are provided,
		allowing backends to configure themselves from deployment metadata instead of using
		zero-argument constructors.

		Args:
			spec: A DeploymentSpec frozen dataclass containing identity, effective_capabilities,
				wire_protocol, endpoint_path, and latency_budget_ms.
			transport: A callable or transport object built by transports (T2A.03), used to
				send requests to the decision engine.

		Returns:
			An instance of the backend configured for the given deployment.

		Raises:
			May raise any exception during transport validation or initialization; these
			propagate to the caller.

		Note:
			This classmethod is entirely optional. Backends that do not define it will always
			be instantiated via zero-argument constructors, and deployment/transport parameters
			will be ignored.
		"""
		...
