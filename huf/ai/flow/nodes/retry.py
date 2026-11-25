"""Retry with backoff for ``tool.call`` steps.

Config (on the step): ``retry {attempts, backoff, delay_seconds, max_delay_seconds}``. ``attempts`` is the total
number of tries. ``backoff`` is ``fixed`` (always ``delay_seconds``) or ``exponential``
(``delay_seconds * 2 ** (try - 1)``, capped at ``max_delay_seconds``).

A failed try parks the run on a timer (``park.park_run``, reason ``retry``). When the timer wakes the run, this
wrapper (not the executor) sees the waiting record, clears it and runs the step again. The try number lives in
``waiting.extra.attempt`` and is reported as ``attempts`` in the step output. After the last try the failure
follows the step's normal ``on_error`` route. The sweeper runs once a minute, so delays are rounded up to 60 s.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from huf.ai.flow import park
from huf.ai.flow.park import ParkRequest

RETRYABLE_TYPES = ("tool.call",)
MIN_DELAY_SECONDS = 60
MAX_ATTEMPTS = 10


def policy_of(node: dict) -> dict | None:
	"""The step's retry policy, or None when it has none (or is not a retryable step)."""
	if node.get("type") not in RETRYABLE_TYPES:
		return None
	policy = (node.get("config") or {}).get("retry")
	if not isinstance(policy, dict):
		return None
	try:
		attempts = min(int(policy.get("attempts") or 1), MAX_ATTEMPTS)
	except (TypeError, ValueError):
		return None
	if attempts < 2:
		return None
	return {**policy, "attempts": attempts}


def backoff_seconds(policy: dict, attempt: int) -> int:
	"""Seconds to wait after failed try number ``attempt`` (1-based)."""
	try:
		base = max(int(policy.get("delay_seconds") or 0), 0)
	except (TypeError, ValueError):
		base = 0
	if policy.get("backoff") == "exponential":
		delay = base * 2 ** (attempt - 1)
		try:
			cap = int(policy.get("max_delay_seconds") or 0)
		except (TypeError, ValueError):
			cap = 0
		if cap > 0:
			delay = min(delay, cap)
	else:
		delay = base
	return max(delay, MIN_DELAY_SECONDS)


def run_with_retry(flow_run, node: dict, settings: dict, run_once):
	"""Run ``run_once()`` (-> result mapping); on failure park for a retry while tries remain.

	Returns the result mapping, or the paused ``Outcome`` from ``park_run``.
	"""
	policy = policy_of(node)
	if policy is None:
		return run_once()

	from huf.ai.flow.engine import _context_of, _persist_context, _transition_run

	attempt = 1
	waiting = park.is_reentry(flow_run, node)
	if waiting and waiting.get("reason") == "retry":
		attempt = int((waiting.get("extra") or {}).get("attempt") or 1) + 1
		_transition_run(flow_run, {"waiting": None}, from_statuses=("Running",))

	result = run_once()
	if result.get("status") != "failed":
		# A tool answers in "result" (the engine records it as the step's output when "output" is absent).
		key = next((k for k in ("output", "result") if isinstance(result.get(k), dict)), None)
		if attempt > 1 and key:
			result[key] = {**result[key], "attempts": attempt}
		return result

	if attempt < policy["attempts"]:
		resume_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=backoff_seconds(policy, attempt))
		_persist_context(flow_run, _context_of(flow_run, settings), settings)
		return park.park_run(
			flow_run, node, ParkRequest(reason="retry", resume_at=resume_at, extra={"attempt": attempt, "error": result.get("error")})
		)

	output = result.get("output") if isinstance(result.get("output"), dict) else {}
	return {**result, "output": {**output, "attempts": attempt}}
