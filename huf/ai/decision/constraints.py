"""Hard-constraint filtering primitives used before Decision Runtime calls."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def apply_hard_constraints(candidates: Iterable[Any], eligible: Callable[[Any], bool]) -> tuple[Any, ...]:
	"""Return only candidates admitted by the authoritative hard-filter predicate."""
	result = []
	seen = set()
	for candidate in candidates:
		identifier = getattr(candidate, "id", None) or getattr(candidate, "name", None) or getattr(candidate, "model", None)
		if identifier in seen or identifier is None or not eligible(candidate):
			continue
		seen.add(identifier)
		result.append(candidate)
	return tuple(result)
