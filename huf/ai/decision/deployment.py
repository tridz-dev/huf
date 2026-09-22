"""Deterministic deployment selection, separate from policy fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from huf.ai.decision.types import DecisionIdentity


@dataclass(frozen=True, slots=True)
class DeploymentCandidate:
	"""A callable deployment for one canonical model."""

	identity: DecisionIdentity
	backend: Any
	enabled: bool = True
	priority: int = 100
	health_status: str = "healthy"

	def __post_init__(self) -> None:
		if self.priority < 0:
			raise ValueError("Deployment priority cannot be negative")


@dataclass(frozen=True, slots=True)
class DeploymentChain:
	requested_identity: DecisionIdentity
	candidates: tuple[DeploymentCandidate, ...]
	selection_source: str = "priority"

	@property
	def fallback_count(self) -> int:
		return max(0, len(self.candidates) - 1)

	@property
	def fallback_chain(self) -> tuple[str, ...]:
		return tuple(candidate.identity.deployment for candidate in self.candidates if candidate.identity.deployment)


def resolve_deployment_chain(
	requested_identity: DecisionIdentity,
	candidates: tuple[DeploymentCandidate, ...],
) -> DeploymentChain:
	"""Return enabled healthy deployments matching the requested canonical identity."""
	eligible = [
		candidate for candidate in candidates
		if candidate.enabled
		and candidate.health_status not in {"disabled", "unhealthy"}
		and _matches_model(requested_identity, candidate.identity)
	]
	ordered = tuple(sorted(eligible, key=lambda item: (item.priority, item.identity.deployment or "")))
	return DeploymentChain(requested_identity=requested_identity, candidates=ordered)


def _matches_model(requested: DecisionIdentity, candidate: DecisionIdentity) -> bool:
	for field in ("model_class", "model_family", "canonical_model", "canonical_version"):
		value = getattr(requested, field)
		if value is not None and getattr(candidate, field) != value:
			return False
	return True
