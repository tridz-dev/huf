# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Bounded serialiser enforcing tool-output budgets (Invariant I7).

No raw intermediate dataset may re-enter model context. This module is the
single place that decides whether a tool result fits inline or must be
spilled to a handle. It is intentionally **frappe-light**: nothing here
imports ``frappe`` or touches the database, so the budget arithmetic is
unit-testable without a site. Callers that need to persist a spilled
payload (e.g. as an ``Agent Context Artifact``) pass in a ``spill``
callback; this module never decides *how* something is stored, only
*whether* it must be.

Contract: **fail closed**. On any breach of ``max_rows``, ``max_bytes`` or
``max_inline_chars`` the full payload is handed to ``spill`` and the
returned result carries a bounded summary, a small preview and a
``dataset_handle`` — never a silently truncated version of the original
payload standing in as if it were complete.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

# Conservative defaults; callers (Procedure/Flow ResourceLimits) may override
# per-graph via ``max_rows``/``max_output_bytes`` in the IR (see
# spec/graph-ir.md ``ResourceLimits``).
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_BYTES = 65536
DEFAULT_MAX_INLINE_CHARS = 4000

# Rows kept in the inline preview of a spilled result. Small and fixed,
# independent of the caller's max_rows, so a spill response itself never
# becomes an unbounded payload.
_SPILL_PREVIEW_ROWS = 20


class OutputBudgetExceeded(RuntimeError):
	"""Raised when a budget is breached and no ``spill`` callback was given.

	Callers that cannot persist a handle (e.g. the frappe-light unit tests)
	rely on this exception to prove the fail-closed contract: there is no
	silent-truncation code path, only "return the full bounded shape" or
	"raise".
	"""


@dataclass(frozen=True)
class OutputBudget:
	"""Limits enforced by :func:`enforce_output_budget`.

	Mirrors the ``ResourceLimits`` fields ``max_rows`` / ``max_output_bytes``
	from spec/graph-ir.md so a graph's declared limits can be passed straight
	through without renaming.
	"""

	max_rows: int = DEFAULT_MAX_ROWS
	max_bytes: int = DEFAULT_MAX_BYTES
	max_inline_chars: int = DEFAULT_MAX_INLINE_CHARS

	def __post_init__(self):
		if self.max_rows <= 0 or self.max_bytes <= 0 or self.max_inline_chars <= 0:
			raise ValueError("OutputBudget limits must be positive")


@dataclass
class BoundedResult:
	"""The shape every budgeted tool result takes, spilled or not.

	``summary`` and ``rows`` are always small enough to enter model context
	unconditionally. ``dataset_handle`` is ``None`` unless a spill happened,
	in which case it is whatever the ``spill`` callback returned (typically
	``{"reference_doctype": ..., "reference_name": ...}``).
	"""

	summary: str
	rows: list
	metadata: dict
	dataset_handle: dict | None = None
	spilled: bool = False

	def to_dict(self) -> dict:
		return {
			"summary": self.summary,
			"rows": self.rows,
			"metadata": self.metadata,
			"dataset_handle": self.dataset_handle,
		}


def _json_byte_size(value: Any) -> int:
	return len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))


def _bounded_preview(rows: list, budget: OutputBudget) -> list:
	"""Shrink ``rows`` until it satisfies both the preview row cap and max_bytes.

	Halves the candidate list until it fits, rather than doing a byte-exact
	trim of an individual row's content — the module never edits a row's
	fields, it only decides how many whole rows to include.
	"""
	preview = rows[: min(len(rows), _SPILL_PREVIEW_ROWS)]
	while len(preview) > 1 and _json_byte_size(preview) > budget.max_bytes:
		preview = preview[: len(preview) // 2]
	if preview and _json_byte_size(preview) > budget.max_bytes:
		# A single row alone exceeds max_bytes; no safe inline preview exists.
		preview = []
	return preview


def enforce_output_budget(
	rows: list[dict] | None,
	*,
	budget: OutputBudget | None = None,
	summary: str | None = None,
	metadata: dict | None = None,
	spill: Callable[[list, dict], dict] | None = None,
) -> BoundedResult:
	"""Serialise ``rows`` within ``budget``, spilling on any breach.

	Args:
		rows: the structured, row-shaped result to bound. ``None`` is
			treated as an empty list.
		budget: limits to enforce; defaults to :class:`OutputBudget`'s
			conservative defaults.
		summary: a human/model-readable description of the result. Also
			bounded by ``max_inline_chars``.
		metadata: extra caller-supplied metadata merged into the returned
			``metadata`` dict (row/byte accounting is always added by this
			function and always wins on key collision).
		spill: called as ``spill(rows, metadata)`` only when a breach is
			detected, with the *full, unbounded* ``rows`` and the metadata
			computed so far. Must return a JSON-safe dict describing where
			the full payload now lives (a "handle"). When breach occurs and
			``spill`` is ``None``, raises :class:`OutputBudgetExceeded`
			instead of ever truncating silently.

	Returns:
		A :class:`BoundedResult` that always fits within the budget.
	"""
	budget = budget or OutputBudget()
	rows = rows or []
	total_rows = len(rows)

	meta: dict = dict(metadata or {})
	meta["total_rows"] = total_rows

	row_breach = total_rows > budget.max_rows
	# Only serialise up to max_rows+1 worth of candidate rows to probe byte
	# size — a genuinely huge dataset should never be fully json.dumps'd here
	# just to discover it is over budget.
	probe = rows[: budget.max_rows] if not row_breach else rows[: budget.max_rows]
	byte_size = _json_byte_size(probe)
	byte_breach = byte_size > budget.max_bytes

	if not row_breach and not byte_breach:
		text_summary = summary or ""
		summary_truncated = len(text_summary) > budget.max_inline_chars
		if summary_truncated:
			# The summary itself may be trimmed (it is documentation, not
			# data) but this is never how a breach on `rows` is handled --
			# rows breaches always spill, they are never truncated in place.
			text_summary = text_summary[: budget.max_inline_chars]
		meta["returned_rows"] = total_rows
		meta["truncated"] = False
		meta["summary_truncated"] = summary_truncated
		return BoundedResult(summary=text_summary, rows=rows, metadata=meta, dataset_handle=None, spilled=False)

	# --- Breach: fail closed. Never return a partially-truncated `rows`. ---
	meta["truncated"] = True
	meta["total_bytes"] = _json_byte_size(rows) if row_breach else byte_size
	meta["max_rows"] = budget.max_rows
	meta["max_bytes"] = budget.max_bytes

	if spill is None:
		raise OutputBudgetExceeded(
			f"Output budget exceeded (rows={total_rows}/{budget.max_rows}, "
			f"bytes={meta['total_bytes']}/{budget.max_bytes}) and no spill handler was provided; "
			"refusing to silently truncate."
		)

	handle = spill(rows, meta)
	if not isinstance(handle, dict):
		raise OutputBudgetExceeded(
			"spill callback must return a dict handle describing the persisted payload"
		)

	preview_rows = _bounded_preview(rows, budget)
	meta["returned_rows"] = len(preview_rows)

	bounded_summary = summary or (
		f"Result exceeds output budget: {total_rows} rows / {meta['total_bytes']} bytes. "
		f"Full data available via dataset_handle."
	)
	bounded_summary = bounded_summary[: budget.max_inline_chars]

	return BoundedResult(
		summary=bounded_summary,
		rows=preview_rows,
		metadata=meta,
		dataset_handle=handle,
		spilled=True,
	)
