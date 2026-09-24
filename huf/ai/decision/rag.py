"""Permission-first RAG/context candidate filtering.

PLAN.md §3.8: Query-time filtering (T8.02) runs on already-authorized results from retriever.py.
The decision can only narrow (I-DR1), never add items. In Advise mode nothing is removed;
each passage is annotated with its relevance score. Enforce mode filters to selected_ids.
"""

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
	"""Narrow an already-authorized set while preserving source order.

	PLAN.md §3.8 I-DR1 guarantee: this function can only remove items from the input set,
	never add or invent new ones. The result is always a subset of the input documents.

	Args:
		documents: Already-authorized retrieval results (passages, chunks).
		selected_ids: The ids to keep (from Enforce decision).

	Returns:
		Tuple of documents in original order, filtered to selected_ids only.
	"""
	selected = set(selected_ids)
	result = []
	for document in documents:
		# Try multiple id attributes: chunk_id, id, name (in order of preference)
		# Handle both objects (with attributes) and dicts
		doc_id = None
		if isinstance(document, dict):
			doc_id = document.get("chunk_id") or document.get("id") or document.get("name")
		else:
			doc_id = (
				getattr(document, "chunk_id", None)
				or getattr(document, "id", None)
				or getattr(document, "name", None)
			)
		if doc_id and doc_id in selected:
			result.append(document)
	return tuple(result)


def apply_rag_filter_decision(
	documents: Iterable[Any],
	decision_result: Any,
	mode: str,
) -> tuple[Any, ...]:
	"""Apply a RAG Filter decision result to authorized retrieval results.

	PLAN.md §3.8: Runs on already-authorized results from retriever.py. In Enforce mode,
	narrows the set to selected_ids. In Advise mode, returns all documents unchanged (the
	hint is applied separately in the context builder). For any other mode or error, returns
	all documents unchanged.

	Args:
		documents: Tuple of already-authorized retrieval results (passages).
		decision_result: SurfaceDecision from decide_for_surface (may be None).
		mode: The binding mode ("Enforce" or "Advise" or other).

	Returns:
		Filtered documents. Always a subset of or equal to the input.
	"""
	if decision_result is None:
		# No binding or Off mode: keep all
		return tuple(documents)

	if mode == "Enforce" and decision_result.selected_ids is not None:
		# Enforce: narrow to selected_ids
		return retain_selected_context(documents, decision_result.selected_ids)

	# Advise or any other mode: keep all (hint is injected separately)
	return tuple(documents)
