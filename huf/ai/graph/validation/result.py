"""Result types of the graph validator: every rejection is a specific, actionable reason, never a bare boolean.

Split out of ``validator.py``, which re-exports these names.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ValidationError:
	"""One specific, actionable reason a graph was rejected.

	``node_id`` is ``None`` for a graph-level problem (e.g. a missing ``contract``).
	``field`` is a dotted/indexed path relative to the node (or the graph root when
	``node_id`` is ``None``), e.g. ``"config.tool_id"`` or ``"contract.limits.max_rows"``.
	"""

	code: str
	node_id: str | None
	field: str | None
	message: str

	def __str__(self) -> str:  # pragma: no cover -- convenience only
		where = self.node_id or "<graph>"
		if self.field:
			where = f"{where}.{self.field}"
		return f"[{self.code}] {where}: {self.message}"


@dataclasses.dataclass(frozen=True)
class ValidationResult:
	"""Outcome of :func:`validate_graph`. ``envelope`` is populated only when ``ok`` is true --
	a graph that fails validation never gets a derived permission envelope, since deriving one
	from a structurally broken document would itself be a claim this module cannot stand behind.
	"""

	ok: bool
	profile: str
	errors: tuple[ValidationError, ...] = ()
	envelope: dict | None = None

	def raise_if_invalid(self) -> None:
		if not self.ok:
			raise GraphValidationError(self)


class GraphValidationError(Exception):
	"""Raised by :meth:`ValidationResult.raise_if_invalid`. Carries the full result, including
	every :class:`ValidationError`, not just the first -- a caller that only wants "did it pass"
	can catch this and stop; a caller building a review UI can read ``.result.errors``."""

	def __init__(self, result: ValidationResult):
		self.result = result
		super().__init__("; ".join(str(err) for err in result.errors) or "graph validation failed")
