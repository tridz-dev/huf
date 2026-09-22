# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Fault injection for the safe-deopt experiment (Track-Item: 4).

This module wraps a workload store's write-B call (``CrmStore.submit_linked_record`` /
``PaymentAllocationStore.submit_allocation`` / ``submit_allocation_unsafe``) with an
INVOKER-LEVEL fault layer. A fault controls two independent things:

1. What the REAL store does -- whether the wrapper actually calls through to the real
   write method (so it lands, or not, in the store's ground-truth ``commit_log``).
2. What the CALLER (the tool-invocation layer / agent) is TOLD -- which may be a lie,
   relative to (1).

None of this module ever mutates or reaches into ``store.commit_log`` to rewrite history --
that list stays ground truth, written only by the store itself. Faults only decide whether
to call the real method and what to hand back to the caller instead of (or in addition to)
its real return value.

Alongside the faults, this module implements the mechanics behind three "tool recovery
guarantee levels" a write tool can declare (the fourth, ``none``, needs no extra code --
see module docstring below for what each means):

- ``server_idempotent``: the store's own idempotent write methods already guarantee that a
  retry with the SAME ``operation_key`` is a safe no-op if the original committed. Nothing
  to add here beyond the store's existing behavior; ``demonstrate_server_idempotent_retry``
  exercises it.
- ``status_resolvable``: :func:`get_operation_status` answers ``"COMMITTED"`` /
  ``"NOT_COMMITTED"`` / ``"UNKNOWN"`` by consulting the real ``commit_log`` -- ground truth,
  not the lie a fault told the caller.
- ``fenceable``: :func:`cancel_operation` lets a caller fence off a held write (used by F7)
  so that, if called before the held write lands, it can never commit.
- ``none``: no extra tooling; a later guard must refuse to retry at all. F2/F3/F6/F7 all
  work identically whether or not any guarantee level is available -- the guarantee levels
  only add machinery a *guard* can use later, they don't change what the fault itself does.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

__all__ = [
	"FAULT_IDS",
	"GUARANTEE_LEVELS",
	"TimeoutFault",
	"ValidationErrorFault",
	"ObservedResult",
	"FaultInjector",
	"get_operation_status",
	"cancel_operation",
	"demonstrate_server_idempotent_retry",
]


FAULT_IDS = ("F0", "F1", "F2", "F3", "F4", "F5", "F6", "F7")
GUARANTEE_LEVELS = ("server_idempotent", "status_resolvable", "fenceable", "none")

OperationStatus = Literal["COMMITTED", "NOT_COMMITTED", "UNKNOWN"]


class TimeoutFault(Exception):
	"""The sentinel exception a caller sees for an in-doubt write (F2/F3/F6).

	F2 and F3 MUST raise this with an identical message/shape regardless of whether the
	real write actually committed (F2) or not (F3) -- that indistinguishability is the
	entire point of those two faults.
	"""

	def __init__(self, *, operation_key: str, action: str) -> None:
		self.operation_key = operation_key
		self.action = action
		super().__init__(f"timeout: no confirmation received for {action} (operation_key={operation_key!r})")


class ValidationErrorFault(Exception):
	"""Raised for F4: a concurrent actor mutated the target record before this write
	attempted to dispatch, so the write fails validation against stale caller assumptions.
	"""

	def __init__(self, *, operation_key: str, action: str, detail: str) -> None:
		self.operation_key = operation_key
		# `action` kept for symmetry with TimeoutFault; not required by callers.
		self.action = action
		self.detail = detail
		super().__init__(f"validation error at write B for {action} (operation_key={operation_key!r}): {detail}")


@dataclass
class ObservedResult:
	"""What the fault layer hands back to the caller -- NOT necessarily the truth.

	``ok`` is True only for a caller-visible success (F0, and F5's fake success). ``value``
	carries the (possibly fake/garbled/None) payload. ``error`` carries the exception
	instance for a caller-visible failure (F1/F2/F3/F4), or ``None`` for a success.
	"""

	ok: bool
	value: Any
	error: Exception | None = None
	fault_id: str = "F0"


@dataclass
class _HeldWrite:
	"""Bookkeeping for F7's "commit lands only after the recovery agent's first read"."""

	fn: Callable[[], Any]
	cancelled: bool = False
	committed: bool = False
	result: Any = None


class FaultInjector:
	"""Wraps a workload store's write-B call and, for F6/F7, its read call too.

	Usage
	-----
	``injector = FaultInjector()``
	``observed = injector.inject("F2", "status_resolvable", store.submit_allocation, allocation="ALLOC-0001", operation_key="...")``

	``real_write_fn`` is the store's bound write method (e.g. ``store.submit_allocation``);
	it is called with the given ``*args, **kwargs`` when-and-only-when the fault says the
	real write should be attempted. The store's own ``commit_log`` records ground truth
	regardless of what :meth:`inject` returns to the caller.

	For F4, pass ``concurrent_mutation=callable`` (invoked with no arguments right before
	dispatch, to simulate the concurrent actor) via keyword; if omitted, the injector
	synthesizes a generic validation error itself rather than relying on the store to raise
	one naturally (some stores may not validate against drift on their own).

    For F6, call :meth:`wrap_read` around the harness's subsequent "read the target record"
    calls -- it will return an ambiguous/garbled result for a bounded number of calls after
    an F6 fault fired, then let real reads back through.

    For F7, the injector holds the real write (never calling it during :meth:`inject`) and
    only invokes it the next time :meth:`wrap_read` is called for the same operation_key
    (modeling "the recovery agent's first read triggers the delayed commit"), unless
    :func:`cancel_operation` fenced it off first.
	"""

	def __init__(self) -> None:
		self._lock = threading.Lock()
		# F6 bookkeeping: operation_key -> remaining ambiguous-read count.
		self._ambiguous_reads: dict[str, int] = {}
		self._ambiguous_kind: dict[str, str] = {}
		# F7 bookkeeping: operation_key -> held write descriptor.
		self._held_writes: dict[str, _HeldWrite] = {}
		# Every held/timed-out operation's fault id, for get_operation_status/logging.
		self._fault_history: dict[str, str] = {}

	# -- main entrypoint -----------------------------------------------------

	def inject(
		self,
		fault_id: str,
		guarantee_level: str,
		real_write_fn: Callable[..., Any],
		*args: Any,
		action: str | None = None,
		operation_key: str | None = None,
		concurrent_mutation: Callable[[], None] | None = None,
		ambiguous_read_count: int = 1,
		ambiguous_kind: str = "processing",
		**kwargs: Any,
	) -> ObservedResult:
		"""Run ``fault_id`` around a single write-B attempt.

		``operation_key`` is required for F2/F3/F6/F7 (used for status/read bookkeeping) and
		is otherwise best-effort read from ``kwargs["operation_key"]`` if present.
		``action`` defaults to ``real_write_fn.__name__``.
		"""
		if fault_id not in FAULT_IDS:
			raise ValueError(f"unknown fault_id {fault_id!r}, expected one of {FAULT_IDS}")
		if guarantee_level not in GUARANTEE_LEVELS:
			raise ValueError(f"unknown guarantee_level {guarantee_level!r}, expected one of {GUARANTEE_LEVELS}")

		action = action or getattr(real_write_fn, "__name__", "write_b")
		operation_key = operation_key or kwargs.get("operation_key") or "<unknown>"
		# The real store method may require operation_key as one of its own kwargs (e.g.
		# ``submit_allocation``): make sure it's present there too, since ``operation_key``
		# here is also used independently for fault/status/read bookkeeping. Some write
		# methods (e.g. ``submit_allocation_unsafe``) deliberately take no such parameter,
		# so only inject it when the target actually accepts it.
		if "operation_key" not in kwargs and operation_key != "<unknown>":
			try:
				accepts_operation_key = "operation_key" in inspect.signature(real_write_fn).parameters
			except (TypeError, ValueError):
				accepts_operation_key = False
			if accepts_operation_key:
				kwargs = dict(kwargs)
				kwargs["operation_key"] = operation_key

		method = getattr(self, f"_inject_{fault_id.lower()}")
		return method(
			real_write_fn,
			args,
			kwargs,
			action=action,
			operation_key=operation_key,
			concurrent_mutation=concurrent_mutation,
			ambiguous_read_count=ambiguous_read_count,
			ambiguous_kind=ambiguous_kind,
		)

	# -- individual faults -----------------------------------------------------

	def _inject_f0(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Control: real write happens, caller told success."""
		value = real_write_fn(*args, **kwargs)
		return ObservedResult(ok=True, value=value, error=None, fault_id="F0")

	def _inject_f1(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Clean rejection before dispatch: wrapper refuses to call through at all."""
		error = RuntimeError(f"rejected before dispatch: {action} (operation_key={operation_key!r})")
		return ObservedResult(ok=False, value=None, error=error, fault_id="F1")

	def _inject_f2(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Timeout after dispatch, store DOES commit. Caller told 'timeout' regardless."""
		real_write_fn(*args, **kwargs)  # lands in commit_log; return value discarded from caller's view
		self._fault_history[operation_key] = "F2"
		error = TimeoutFault(operation_key=operation_key, action=action)
		return ObservedResult(ok=False, value=None, error=error, fault_id="F2")

	def _inject_f3(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Timeout after dispatch, store does NOT commit. Caller-visible result identical to F2."""
		# Deliberately do NOT call real_write_fn: nothing lands in commit_log.
		self._fault_history[operation_key] = "F3"
		error = TimeoutFault(operation_key=operation_key, action=action)
		return ObservedResult(ok=False, value=None, error=error, fault_id="F3")

	def _inject_f4(self, real_write_fn, args, kwargs, *, action, operation_key, concurrent_mutation, **_ignored) -> ObservedResult:
		"""Concurrent actor drift: mutate the target out from under the write, then attempt it."""
		if concurrent_mutation is not None:
			concurrent_mutation()
		try:
			real_write_fn(*args, **kwargs)
		except Exception as exc:  # the store's own natural validation error, if it raises one
			self._fault_history[operation_key] = "F4"
			error = ValidationErrorFault(operation_key=operation_key, action=action, detail=str(exc))
			return ObservedResult(ok=False, value=None, error=error, fault_id="F4")
		# Store didn't validate on its own (e.g. idempotent no-op or silent success) --
		# surface a synthesized validation error ourselves, since F4's whole point is that
		# the caller must be told write B failed validation due to drift.
		self._fault_history[operation_key] = "F4"
		error = ValidationErrorFault(operation_key=operation_key, action=action, detail="target record changed concurrently before write B dispatched")
		return ObservedResult(ok=False, value=None, error=error, fault_id="F4")

	def _inject_f5(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Lost result: real write commits, caller told success but given a garbled/empty payload."""
		real_write_fn(*args, **kwargs)
		self._fault_history[operation_key] = "F5"
		# "ok=True" (a tool call that didn't raise) but the payload carries no evidence of
		# what happened -- the caller cannot tell success from garbage by inspecting value.
		return ObservedResult(ok=True, value=None, error=None, fault_id="F5")

	def _inject_f6(self, real_write_fn, args, kwargs, *, action, operation_key, ambiguous_read_count, ambiguous_kind, **_ignored) -> ObservedResult:
		"""Like F2 (timeout, but store DOES commit), plus N subsequent ambiguous reads."""
		real_write_fn(*args, **kwargs)
		self._fault_history[operation_key] = "F6"
		with self._lock:
			self._ambiguous_reads[operation_key] = ambiguous_read_count
			self._ambiguous_kind[operation_key] = ambiguous_kind
		error = TimeoutFault(operation_key=operation_key, action=action)
		return ObservedResult(ok=False, value=None, error=error, fault_id="F6")

	def _inject_f7(self, real_write_fn, args, kwargs, *, action, operation_key, **_ignored) -> ObservedResult:
		"""Late commit: timeout reported now, real write HELD until the next wrap_read()."""
		held = _HeldWrite(fn=lambda: real_write_fn(*args, **kwargs))
		with self._lock:
			self._held_writes[operation_key] = held
		self._fault_history[operation_key] = "F7"
		error = TimeoutFault(operation_key=operation_key, action=action)
		return ObservedResult(ok=False, value=None, error=error, fault_id="F7")

	# -- read-side interception (F6 / F7) -----------------------------------

	def wrap_read(self, operation_key: str, real_read_fn: Callable[[], Any]) -> Any:
		"""Wrap a "read the target record" call made after a fault fired.

		- F6: for the configured number of calls, returns an ambiguous sentinel instead of
		  calling ``real_read_fn`` at all; after that budget is exhausted, calls through.
		- F7: the FIRST call after the fault triggers the held write to land (unless it was
		  cancelled via :func:`cancel_operation`), but this call itself still returns
		  whatever the real read says BEFORE that write is applied (pre-write / not-found
		  state) -- the harness is expected to call again afterwards to observe the landed
		  write, or after a delay. Subsequent calls just call through.
		- Anything else (no fault registered for this key): calls through untouched.
		"""
		with self._lock:
			remaining = self._ambiguous_reads.get(operation_key, 0)
			if remaining > 0:
				self._ambiguous_reads[operation_key] = remaining - 1
				kind = self._ambiguous_kind.get(operation_key, "processing")
				if kind == "error":
					raise RuntimeError(f"read error: ambiguous state for operation_key={operation_key!r}")
				if kind == "stale":
					# Let the real read run first so we can return a snapshot of pre-fault
					# state -- but here we don't have a stale snapshot stored, so signal a
					# stale/ambiguous marker rather than fabricate data out of thin air.
					return "STALE_REPLICA_VALUE"
				return "PROCESSING"

			held = self._held_writes.get(operation_key)

		if held is not None and not held.committed and not held.cancelled:
			# First read after F7's fault: capture pre-write truth, THEN trigger the delayed
			# commit for subsequent reads/writes to observe.
			pre_write_value = real_read_fn()
			with self._lock:
				still_pending = self._held_writes.get(operation_key)
				if still_pending is not None and not still_pending.cancelled and not still_pending.committed:
					still_pending.result = still_pending.fn()
					still_pending.committed = True
			return pre_write_value

		return real_read_fn()

	def flush_held_write(self, operation_key: str) -> bool:
		"""Force a held F7 write to land now (e.g. harness models "a fixed delay" instead of
		"first read"). Returns True iff the write committed as a result of this call.
		"""
		with self._lock:
			held = self._held_writes.get(operation_key)
			if held is None or held.committed or held.cancelled:
				return False
		held.result = held.fn()
		with self._lock:
			held.committed = True
		return True

	def cancel(self, operation_key: str) -> bool:
		"""Fence off a held F7 write so it can never land. Returns True iff a pending held
		write existed and was successfully fenced (i.e. it had not already committed).
		"""
		with self._lock:
			held = self._held_writes.get(operation_key)
			if held is None:
				return False
			if held.committed:
				return False
			held.cancelled = True
			return True


# ---------------------------------------------------------------------------
# Tool recovery guarantee mechanics
# ---------------------------------------------------------------------------


def get_operation_status(store: Any, operation_key: str, *, injector: FaultInjector | None = None) -> OperationStatus:
	"""``status_resolvable`` guarantee: answer COMMITTED/NOT_COMMITTED/UNKNOWN by consulting
	the store's real ``commit_log`` -- ground truth, never the lie a fault told the caller.

	During F7's ambiguous window (write held, not yet committed, not cancelled), the true
	status genuinely is unresolved -- this returns "UNKNOWN" for that case. Once resolved
	(committed, or cancelled/never-committed-and-no-longer-pending), it returns definitively.
	"""
	for entry in getattr(store, "commit_log", []):
		if entry.operation_key == operation_key and entry.committed:
			return "COMMITTED"

	if injector is not None:
		with injector._lock:  # noqa: SLF001 -- intentional, this is the mechanism's own module
			held = injector._held_writes.get(operation_key)
			if held is not None and not held.committed and not held.cancelled:
				return "UNKNOWN"

	return "NOT_COMMITTED"


def cancel_operation(store: Any, operation_key: str, *, injector: FaultInjector) -> bool:
	"""``fenceable`` guarantee: cancel a held (F7) operation before it lands.

	Returns True iff the operation was successfully fenced (no commit will ever be produced
	for it going forward). Returns False if there was nothing pending to cancel, or if it
	had already committed by the time cancellation was requested -- ``store.commit_log`` is
	always the final word on which case occurred.
	"""
	return injector.cancel(operation_key)


def demonstrate_server_idempotent_retry(write_fn: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, Any]:
	"""``server_idempotent`` guarantee: calling ``write_fn`` twice with the SAME
	``operation_key`` (already present in ``kwargs``) is a safe no-op the second time, per
	the store's own idempotency behavior (no extra machinery needed beyond that). Returns
	``(first_result, second_result)`` for the caller to compare/assert on.
	"""
	first = write_fn(*args, **kwargs)
	second = write_fn(*args, **kwargs)
	return first, second
