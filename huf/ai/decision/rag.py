"""Permission-first RAG/context candidate filtering."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


def get_retrieval_candidates(documents: Iterable[Any], *, eligible: Callable[[Any], bool]) -> tuple[Any, ...]:
	"""Return deduplicated documents that pass authoritative visibility filters."""
	result = []
	seen = set()
	for document in documents:
		identifier = getattr(document, "id", None) or getattr(document, "name", None)
		if identifier is None or identifier in seen or not eligible(document):
			continue
		seen.add(identifier)
		result.append(document)
	return tuple(result)


def retain_selected_context(documents: Iterable[Any], selected_ids: Iterable[str]) -> tuple[Any, ...]:
	"""Narrow an already-authorized set while preserving source order."""
	selected = set(selected_ids)
	return tuple(document for document in documents if (getattr(document, "id", None) or getattr(document, "name", None)) in selected)
