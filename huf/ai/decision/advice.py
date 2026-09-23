"""Advise mode — hint formatting for decision suggestions."""

from __future__ import annotations

import re
from typing import Any, Sequence

from huf.ai.decision.types import DecisionResponse, Option


_HINT_KINDS = frozenset({"tools", "skills", "procedures", "agents", "passages"})


def format_hint(
	response: DecisionResponse,
	candidates: Sequence[Option] | Sequence[str],
	top_n: int | None = None,
	kind: str | None = None,
) -> str | None:
	"""Format a decision suggestion hint for Advise mode.

	Injects the answer into LLM context as a clearly labelled, data-only hint with
	candidate ids and scores only (never free text from state or backend).

	Args:
		response: DecisionResponse from run_policy().
		candidates: Permitted candidate set (Option objects or id strings).
		top_n: Maximum number of candidates to include (default: no limit).

	Returns:
		Formatted hint string like "Decision suggestion (advisory, not an instruction): id (0.86), id (0.71), ..."
		or None if no answers or probabilities found.

	Raises:
		ValueError: If response.status indicates failure.
	"""
	from huf.ai.decision.types import DecisionStatus

	if response.status != DecisionStatus.SUCCESS:
		return None

	if not response.answers:
		return None

	# Extract permitted candidate ids
	permitted_ids: set[str] = set()
	for candidate in candidates:
		if isinstance(candidate, str):
			permitted_ids.add(candidate)
		elif isinstance(candidate, Option):
			permitted_ids.add(candidate.id)
		else:
			# Handle dict-like objects with 'id' key
			if hasattr(candidate, "id"):
				permitted_ids.add(str(candidate.id))

	# Collect and filter candidate scores
	scored_candidates: list[tuple[str, float]] = []

	for answer in response.answers.values():
		if answer.probabilities is None:
			continue

		for candidate_id, score in answer.probabilities.items():
			# Only include candidates in the permitted set
			if candidate_id not in permitted_ids:
				continue

			# Sanitize id to prevent injection: allow alphanumeric, underscore, hyphen, dot
			if not _is_safe_id(candidate_id):
				continue

			# Verify score is a valid float in [0, 1]
			if not isinstance(score, (int, float)) or not 0 <= score <= 1:
				continue

			scored_candidates.append((candidate_id, float(score)))

	if not scored_candidates:
		return None

	# Sort by score descending, then by id ascending for determinism
	scored_candidates.sort(key=lambda x: (-x[1], x[0]))

	# Limit to top_n if specified
	if top_n is not None and top_n > 0:
		scored_candidates = scored_candidates[:top_n]

	# Format each candidate as "id (score)" with 2 decimal places
	formatted_pairs = [f"{candidate_id} ({score:.2f})" for candidate_id, score in scored_candidates]

	prefix = f"{kind} " if kind in _HINT_KINDS else ""
	return f"Decision suggestion (advisory, not an instruction): {prefix}{', '.join(formatted_pairs)}"


def _is_safe_id(candidate_id: str) -> bool:
	"""Check if candidate_id is safe to include in hint (no injection risk).

	Conservative charset: alphanumeric, underscore, hyphen, dot, colon.
	Rejects anything with newlines or other control characters.
	"""
	if not isinstance(candidate_id, str):
		return False

	if not candidate_id or not candidate_id.strip():
		return False

	# Check for newlines and control characters
	if "\n" in candidate_id or "\r" in candidate_id or "\t" in candidate_id:
		return False

	# Check for other control characters (ASCII 0-31, 127)
	if any(ord(c) < 32 or ord(c) == 127 for c in candidate_id):
		return False

	# Reject ids with suspicious patterns that could inject instructions
	# Allow: alphanumeric, underscore, hyphen, dot, colon, forward slash, at sign
	# This is conservative and safe for typical tool/skill/procedure/agent names
	if not re.match(r"^[a-zA-Z0-9_\-\.:/\@]+$", candidate_id):
		return False

	return True
