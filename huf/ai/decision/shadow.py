"""Opt-in, read-only shadow comparison for Decision Runtime results."""

from __future__ import annotations

from dataclasses import dataclass
from random import random
from typing import Any, Callable

from huf.ai.decision.types import DecisionResponse, DecisionStatus


@dataclass(frozen=True, slots=True)
class DecisionShadowConfig:
	enabled: bool = False
	sample_rate: float = 0.0
	max_runs: int = 0

	def __post_init__(self) -> None:
		if not 0 <= self.sample_rate <= 1:
			raise ValueError("sample_rate must be in [0, 1]")
		if self.max_runs < 0:
			raise ValueError("max_runs must be >= 0")


@dataclass(frozen=True, slots=True)
class DecisionShadowResult:
	sampled: bool
	matched: bool | None = None
	primary_status: DecisionStatus | None = None
	shadow_status: DecisionStatus | None = None
	answer_mismatches: tuple[str, ...] = ()
	error: str | None = None


def should_shadow(
	config: DecisionShadowConfig,
	*,
	read_only: bool,
	contains_writes: bool,
	runs_used: int,
	random_value: float | None = None,
) -> bool:
	"""Return whether an explicitly enabled, read-only decision may be shadowed."""
	if not config.enabled or not read_only or contains_writes or config.max_runs <= runs_used:
		return False
	value = random() if random_value is None else random_value
	return 0 <= value < config.sample_rate


def run_shadow(
	primary: DecisionResponse,
	shadow_evaluate: Callable[[], DecisionResponse],
	*,
	config: DecisionShadowConfig,
	read_only: bool,
	contains_writes: bool,
	runs_used: int,
	random_value: float | None = None,
) -> DecisionShadowResult:
	"""Compare a second normalized result without affecting the primary result."""
	if not should_shadow(config, read_only=read_only, contains_writes=contains_writes, runs_used=runs_used, random_value=random_value):
		return DecisionShadowResult(sampled=False)
	try:
		shadow = shadow_evaluate()
		mismatches = _answer_mismatches(primary, shadow)
		return DecisionShadowResult(
			sampled=True,
			matched=primary.status == shadow.status and not mismatches,
			primary_status=primary.status,
			shadow_status=shadow.status,
			answer_mismatches=mismatches,
		)
	except Exception as exc:  # shadow must never change the completed result
		return DecisionShadowResult(sampled=True, matched=False, primary_status=primary.status, error=str(exc))


def _answer_mismatches(primary: DecisionResponse, shadow: DecisionResponse) -> tuple[str, ...]:
	keys = set(primary.answers) | set(shadow.answers)
	return tuple(sorted(key for key in keys if _answer_value(primary.answers.get(key)) != _answer_value(shadow.answers.get(key))))


def _answer_value(answer: Any) -> Any:
	return getattr(answer, "value", answer)
