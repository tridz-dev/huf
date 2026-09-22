"""Fail-closed context relevance and compaction helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def retain_relevant_context(
	items: Iterable[Any],
	selected_ids: Iterable[str] | None,
	*,
	required_ids: Iterable[str] = (),
	decision_succeeded: bool = False,
) -> tuple[Any, ...]:
	"""Narrow optional context while always retaining required items.

	Uncertain or failed semantic decisions retain the complete authorized input, so
	context compaction cannot silently discard mandatory context.
	"""
	items = tuple(items)
	required = set(required_ids)
	if not decision_succeeded or selected_ids is None:
		return items
	selected = required | set(selected_ids)
	return tuple(item for item in items if _identifier(item) in selected)


def _identifier(item: Any) -> str | None:
	return getattr(item, "id", None) or getattr(item, "name", None)
