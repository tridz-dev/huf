from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MAX_WAIT_SECONDS = 10
DEFAULT_WAIT_SECONDS = 5
POLL_INTERVAL_SECONDS = 1


def clamp_wait(value: Any) -> int:
	"""Return a wait duration in whole seconds, clamped to [0, MAX_WAIT_SECONDS].

	None and non-numeric values fall back to DEFAULT_WAIT_SECONDS.
	"""
	try:
		seconds = int(value)
	except (TypeError, ValueError, OverflowError):
		return DEFAULT_WAIT_SECONDS
	return max(0, min(seconds, MAX_WAIT_SECONDS))


def next_seq(last_seq: Any) -> int:
	"""Return the sequence number that follows ``last_seq`` (missing counts as 0)."""
	return int(last_seq or 0) + 1


def is_replay(acked_seq: Any, seq: int) -> bool:
	"""True when ``seq`` has already been acknowledged by ``acked_seq``."""
	return seq <= int(acked_seq or 0)


def select_deliverable(events: Iterable[Mapping[str, Any]], acked_seq: Any) -> list[Mapping[str, Any]]:
	"""Return events newer than ``acked_seq``, sorted by ascending ``seq``.

	When several events share a ``seq``, only the first one in input order is kept.
	"""
	acked = int(acked_seq or 0)
	seen: set[int] = set()
	unique: list[Mapping[str, Any]] = []
	for event in events:
		seq = int(event["seq"])
		if seq <= acked or seq in seen:
			continue
		seen.add(seq)
		unique.append(event)
	return sorted(unique, key=lambda event: int(event["seq"]))


def has_gap(events: Iterable[Mapping[str, Any]], acked_seq: Any) -> bool:
	"""True when the deliverable events do not run consecutively from ``acked_seq + 1``."""
	acked = int(acked_seq or 0)
	seqs = [int(event["seq"]) for event in select_deliverable(events, acked)]
	return seqs != list(range(acked + 1, acked + 1 + len(seqs)))
