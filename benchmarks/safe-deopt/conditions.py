# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Deterministic (no-LLM) recovery conditions for the safe-deopt experiment (Track-Item: 5).

This module implements the mechanical baselines a recovery strategy can follow after a
fault-injected write-B call comes back in-doubt or clearly failed (F1-F7 in ``faults.py``):

- **C2 -- naive compiled replay**: blindly re-run the write with no idempotency-key reuse
  and no outcome check first. This is the "just retry" baseline that the workloads'
  ``submit_allocation_unsafe`` write shape exists specifically to catch: replaying it
  produces a real duplicate.
- **C3 -- deterministic resume / idempotency-key replay**: retry the SAME write call with
  the SAME ``operation_key`` against the store's idempotent write path. This is safe by
  construction (a no-op if the original attempt actually committed; a real write if it did
  not) purely because the *store itself* dedups on ``operation_key`` -- this condition adds
  no guard logic of its own, it just demonstrates the "saga-style" baseline recovery.
- **C6 -- the replay guard**: a real guard that sits in FRONT of any retry attempt and
  decides, from ground truth plus what THIS recovery session has actually done so far,
  whether a retry may proceed at all. This is the interesting node: see ``ReplayGuard``'s
  docstring for the exact admission rule.

None of this module talks to an LLM. It is pure Python, exercised directly by
``tests/test_conditions.py`` and, later, by a harness that runs these conditions against
``faults.FaultInjector``-wrapped stores from ``workloads.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from faults import FaultInjector, GUARANTEE_LEVELS, get_operation_status

__all__ = [
	"ReplayRejected",
	"RecoverySession",
	"ReplayGuard",
	"naive_replay_recover",
	"deterministic_resume_recover",
]


# ---------------------------------------------------------------------------
# C2 -- naive compiled replay
# ---------------------------------------------------------------------------


def naive_replay_recover(
	store: Any,
	write_fn: Callable[..., Any],
	*args: Any,
	max_retries: int = 1,
	fresh_operation_key_fn: Callable[[int], str] | None = None,
	**kwargs: Any,
) -> list[Any]:
	"""C2: blindly re-run ``write_fn`` up to ``max_retries`` times, from scratch, with no
	idempotency-key reuse and no outcome check beforehand.

	Two equally "naive" shapes are supported, matching the task brief's either/or:

	1. ``write_fn`` takes no ``operation_key`` at all (e.g. ``store.submit_allocation_unsafe``)
	   -- every call is unconditionally a brand-new write. This is the primary shape used to
	   prove C2 is unsafe.
	2. ``write_fn`` DOES take ``operation_key`` (e.g. the idempotent ``submit_allocation``),
	   but this function deliberately mints a FRESH, different key on every retry (via
	   ``fresh_operation_key_fn``, or a simple counter-based default) to simulate "acting as
	   if there were no idempotency" -- defeating the store's own dedup on purpose.

	Returns the list of raw return values from each attempt (including the first). This
	function performs NO status check, NO read-before-write, and reuses nothing from a prior
	attempt -- that is the entire point of C2 as a strategy to show is unsafe.
	"""
	results: list[Any] = []
	accepts_operation_key = "operation_key" in kwargs

	for attempt in range(max_retries + 1):
		call_kwargs = dict(kwargs)
		if accepts_operation_key:
			if fresh_operation_key_fn is not None:
				call_kwargs["operation_key"] = fresh_operation_key_fn(attempt)
			else:
				call_kwargs["operation_key"] = f"{kwargs['operation_key']}::naive-retry-{attempt}"
		results.append(write_fn(*args, **call_kwargs))

	return results


# ---------------------------------------------------------------------------
# C3 -- deterministic resume / idempotency-key replay
# ---------------------------------------------------------------------------


def deterministic_resume_recover(
	store: Any,
	write_fn: Callable[..., Any],
	*args: Any,
	operation_key: str,
	max_retries: int = 1,
	**kwargs: Any,
) -> list[Any]:
	"""C3: retry the SAME write call with the SAME ``operation_key`` against the store's
	idempotent write path (a "saga-style" baseline resume -- mirrors
	``procedure_runtime.RECOVERY_RESUME`` / ``idempotency.derive_operation_key``'s
	"same logical write, replayed with its own identity" shape, without importing either
	module).

	Safety here comes entirely from the underlying store's own operation_key-keyed dedup
	(``CrmStore``/``PaymentAllocationStore`` in ``workloads.py``): if the original attempt
	actually committed, replaying with the same key is a logged no-op; if it did not commit,
	replaying performs the real write exactly once. This function adds no extra guard logic
	of its own -- it exists to demonstrate that baseline, for comparison against C6's guard,
	which does NOT trust the write path's own dedup blindly (a guard is still needed when the
	tool has no such guarantee at all).

	Returns the list of raw return values from each attempt (including the first).
	"""
	results: list[Any] = []
	for _ in range(max_retries + 1):
		results.append(write_fn(*args, operation_key=operation_key, **kwargs))
	return results


# ---------------------------------------------------------------------------
# C6 -- the replay guard
# ---------------------------------------------------------------------------


class ReplayRejected(RuntimeError):
	"""Raised by :meth:`ReplayGuard.attempt_write` when a retry may not proceed.

	Carries the ``operation_key``, the ``tool_guarantee`` level considered, and a ``reason``
	string a harness/report can quote verbatim to explain why the guard refused.
	"""

	def __init__(self, *, operation_key: str, tool_guarantee: str, reason: str) -> None:
		self.operation_key = operation_key
		self.tool_guarantee = tool_guarantee
		self.reason = reason
		super().__init__(f"replay rejected for operation_key={operation_key!r} (tool_guarantee={tool_guarantee!r}): {reason}")


@dataclass
class RecoverySession:
	"""Mutable bookkeeping for what a SINGLE recovery session has actually done so far.

	This is intentionally session-scoped, not store-scoped or global: the guard's whole
	point is that a session may only unlock a retry via a guarantee it has ITSELF exercised
	successfully in this recovery attempt -- not via a guarantee that merely exists in the
	abstract, and not via a bare read.

	Fields
	------
	- ``reads_done``: operation_keys this session has performed *some* read against (e.g.
	  "checked the record"). Recorded for audit/observability only -- see the guard's
	  docstring for why this field, by itself, NEVER unlocks anything.
	- ``status_resolved``: operation_key -> the definitive ``"COMMITTED"``/``"NOT_COMMITTED"``
	  outcome this session obtained by actually calling ``get_operation_status`` (or
	  equivalent) for that key. A key absent from this dict, or present only because of an
	  ``"UNKNOWN"`` result, does not count as resolved.
	- ``fenced``: operation_keys this session has fenced off via a successful
	  ``cancel_operation`` call (i.e. the fencing call returned True) before attempting the
	  retry.
	"""

	reads_done: set[str] = field(default_factory=set)
	status_resolved: dict[str, str] = field(default_factory=dict)
	fenced: set[str] = field(default_factory=set)

	# -- recording helpers, for a harness driving the session ---------------

	def record_read(self, operation_key: str) -> None:
		self.reads_done.add(operation_key)

	def record_status_check(self, operation_key: str, status: str) -> None:
		"""Record the result of an ACTUAL ``get_operation_status`` call. Only "COMMITTED" and
		"NOT_COMMITTED" are meaningful resolutions; "UNKNOWN" is recorded too (so a harness
		can see it was checked) but never satisfies the guard's resolved-NOT_COMMITTED rule.
		"""
		self.status_resolved[operation_key] = status

	def record_fence(self, operation_key: str, *, fenced: bool) -> None:
		"""Record the result of an ACTUAL ``cancel_operation`` call. Only a successful fence
		(``fenced=True``) adds the key to ``self.fenced``; a failed/no-op cancel attempt does
		NOT unlock anything, and any previously recorded fence is not removed by a later
		failed attempt (once fenced, a held write can never land -- see ``faults.py``).
		"""
		if fenced:
			self.fenced.add(operation_key)


class ReplayGuard:
	"""C6: the guard that decides whether a retry of a write may proceed at all.

	Wraps an atomic-tool invoker (any callable write, e.g. a store's bound write method) and
	enforces the admission rule below BEFORE ever calling through. It never mutates
	``store.commit_log`` and never invents outcomes -- it only ever consults ground truth
	(via ``get_operation_status``, when resolvable) and the ``RecoverySession``'s own record
	of what THIS session has actually done.

    THE ADMISSION RULE (hard rule -- read this before touching ``attempt_write``)
    -------------------------------------------------------------------------
    1. COMMITTED (per ground truth, i.e. ``get_operation_status`` -- when resolvable -- or,
       for ``server_idempotent`` tools, per the store's own dedup) is retried, but retrying a
       known-committed write is *never itself dangerous* only because the underlying idempotent
       method is what's called and it will no-op. HOWEVER, per the task brief, if the guard can
       positively confirm COMMITTED via ``status_resolvable`` (an actual resolved check) and the
       tool is NOT ``server_idempotent`` (i.e. calling through again is not provably safe), the
       guard REJECTS the retry outright -- there is nothing left to accomplish and no idempotent
       protection if it is somehow called again. Concretely: a resolved COMMITTED status blocks
       any further retry unless the write path is ``server_idempotent`` (in which case the guard
       simply lets the store's own dedup absorb the redundant call).
    2. UNKNOWN outcome (the write's true outcome is not resolved as COMMITTED) is retried ONLY
       when one of:
         a. ``tool_guarantee == "server_idempotent"``: always allowed. The store's own
            operation_key-based dedup makes a retry safe unconditionally -- no session state
            is required.
         b. ``tool_guarantee == "status_resolvable"`` AND
            ``recovery_session.status_resolved.get(operation_key) == "NOT_COMMITTED"``: the
            session must have ACTUALLY called (the equivalent of) ``get_operation_status`` for
            this exact key and gotten a definitive NOT_COMMITTED back -- not "UNKNOWN", not "a
            read happened", not "resolved for some other key".
         c. ``tool_guarantee == "fenceable"`` AND ``operation_key in recovery_session.fenced``:
            the session must have ACTUALLY called (the equivalent of) ``cancel_operation`` for
            this exact key and had it succeed (fence the held write) BEFORE the retry.
       Otherwise (including ``tool_guarantee == "none"``, and including
       ``status_resolvable``/``fenceable`` tools whose guarantee-specific check was never
       actually exercised by this session) the guard REJECTS unconditionally.
    3. A bare "a read happened" (``recovery_session.reads_done``) NEVER by itself unlocks a
       retry of an unresolved-outcome write, for ANY guarantee level, including ``none``. Only
       an actual resolved-guarantee use (2a/2b/2c above) does. This is deliberate: a read can be
       ambiguous/garbled (F6) or reflect pre-write state (F7's first read) and is not proof of
       either outcome.
    4. ``tool_guarantee == "none"``: ``attempt_write`` raises :class:`ReplayRejected`
       UNCONDITIONALLY for any retry of a write whose outcome is not resolved COMMITTED via
       ``get_operation_status`` -- there is no guarantee-specific escape hatch to exercise.
       Only reads, compensating actions, and escalation are permitted recovery moves under
       ``none``; this guard only ever gates writes, so those other moves are simply outside
       its scope (a harness performs them directly, not through this guard).
	"""

	def __init__(self, *, injector: FaultInjector | None = None) -> None:
		self._injector = injector

	def attempt_write(
		self,
		write_fn: Callable[..., Any],
		*args: Any,
		operation_key: str,
		tool_guarantee: str,
		recovery_session: RecoverySession,
		store: Any = None,
		**kwargs: Any,
	) -> Any:
		"""Attempt (or reject) a retry of ``write_fn`` for ``operation_key``.

		``store`` is used, when supplied, to resolve ground-truth COMMITTED/NOT_COMMITTED
		status via ``get_operation_status`` -- required to honor rule 1 and rule 2b above.
		When ``store`` is omitted, ground-truth commit status can only come from the
		session's own ``status_resolved`` record (still sufficient to test/exercise rules
		2b/2c/4 in isolation, e.g. in unit tests that pre-seed the session).

		Raises :class:`ReplayRejected` per the admission rule; otherwise calls
		``write_fn(*args, operation_key=operation_key, **kwargs)`` and returns its result.
		"""
		if tool_guarantee not in GUARANTEE_LEVELS:
			raise ValueError(f"unknown tool_guarantee {tool_guarantee!r}, expected one of {GUARANTEE_LEVELS}")

		# -- resolve ground-truth status, where possible -----------------------
		# IMPORTANT: only consult get_operation_status (a ground-truth oracle) when the
		# declared guarantee actually entitles the recovery session to that information --
		# server_idempotent (the store's own dedup ledger IS the guarantee) and
		# status_resolvable (the tool explicitly offers a status query). For "none" and
		# "fenceable", the guard must reason only from what recovery_session actually
		# recorded (an explicit status_resolved entry, or a successful fence) -- giving it
		# a free oracle lookup there would let the guard "know" things the declared
		# guarantee model says it has no way to know, silently weakening the "none" rule
		# and the "fenceable" rule to behave like status_resolvable.
		resolved_status = recovery_session.status_resolved.get(operation_key)
		ground_truth_committed = resolved_status == "COMMITTED"
		if not ground_truth_committed and store is not None and tool_guarantee in (
			"server_idempotent",
			"status_resolvable",
		):
			if get_operation_status(store, operation_key, injector=self._injector) == "COMMITTED":
				ground_truth_committed = True

		# -- rule 1: known-COMMITTED ---------------------------------------------
		if ground_truth_committed:
			if tool_guarantee == "server_idempotent":
				return write_fn(*args, operation_key=operation_key, **kwargs)
			raise ReplayRejected(
				operation_key=operation_key,
				tool_guarantee=tool_guarantee,
				reason="operation_key is already known COMMITTED and the tool is not server_idempotent; "
				"no further retry is needed or permitted",
			)

		# -- rule 4: no guarantee at all ------------------------------------------
		if tool_guarantee == "none":
			raise ReplayRejected(
				operation_key=operation_key,
				tool_guarantee="none",
				reason="tool declares no recovery guarantee; an unresolved-outcome write may never be retried "
				"-- only reads, compensating actions, or escalation are permitted",
			)

		# -- rule 2a: server_idempotent ------------------------------------------
		if tool_guarantee == "server_idempotent":
			return write_fn(*args, operation_key=operation_key, **kwargs)

		# -- rule 2b: status_resolvable, actually resolved NOT_COMMITTED --------
		if tool_guarantee == "status_resolvable":
			if recovery_session.status_resolved.get(operation_key) == "NOT_COMMITTED":
				return write_fn(*args, operation_key=operation_key, **kwargs)
			raise ReplayRejected(
				operation_key=operation_key,
				tool_guarantee="status_resolvable",
				reason="the recovery session has not actually resolved this operation_key's status to "
				"NOT_COMMITTED via get_operation_status; a bare read does not count",
			)

		# -- rule 2c: fenceable, actually fenced ---------------------------------
		if tool_guarantee == "fenceable":
			if operation_key in recovery_session.fenced:
				return write_fn(*args, operation_key=operation_key, **kwargs)
			raise ReplayRejected(
				operation_key=operation_key,
				tool_guarantee="fenceable",
				reason="the recovery session has not successfully fenced (cancel_operation) this "
				"operation_key before attempting the retry",
			)

		# Unreachable: every GUARANTEE_LEVELS value is handled above.
		raise AssertionError(f"unhandled tool_guarantee {tool_guarantee!r}")
