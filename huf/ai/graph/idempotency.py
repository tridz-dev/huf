# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Cross-run write idempotency for Procedure execution (T-40, D5).

D5 (TRACKER.md) settled the shape of the key and refused run-scoping:

	Key = procedure version + procedure name + normalised inputs + target document identity.
	Not run-scoped.

A run-scoped key (e.g. ``run_id + node_id``) only protects a retry *within* the same
``Agent Procedure Run`` -- it says nothing about the Agent (or a queued job, or a human)
invoking the same Procedure a second time with the same effective inputs, which is exactly
how duplicate ERP documents get created (GOAL.md ss2.1: "A retry cannot accidentally create
another ToDo"). Content-derivation is what makes two independent runs of the same logical
operation collide on purpose.

This module is deliberately a thin, frappe-light layer:

* :func:`derive_idempotency_key` is pure -- no frappe import, unit-testable standalone
  (mirrors ``huf.ai.graph.transforms`` / ``huf.ai.graph.expressions``).
* :func:`reserve_idempotency_key` / :func:`release_idempotency_key` are the only frappe-
  touching functions, and they touch nothing but ``frappe.cache()`` -- the same
  "cache set nx/ex" convention already used by ``huf.ai.procedure_lock`` (GT-08) and
  ``huf.ai.agent_integration``'s queue lock. This is a *defense-in-depth* dedup layer,
  never the primary idempotency guard: the primary guard for benchmark-3-shaped
  Procedures is the graph's own read-before-write (an ``existing_followup_check``
  ``tool.call`` feeding a ``condition`` node) -- see
  ``benchmarks/benchmark-3-crm-followup/expected-procedure.md``. The reservation below
  exists to close the race the graph-level check cannot: two workers evaluating
  ``existing_followup_check`` concurrently, both seeing "not found", both proceeding to
  ``create_todo`` before either write commits.

Dedup window
------------

``DEDUP_WINDOW_SECONDS`` is the one parameter D5 deliberately left open (TRACKER.md R-9).
Proposed here as **24 hours**, understood as an *orphan-reservation TTL*, not a hold
duration a write normally waits out.

``huf.ai.graph.procedure_runtime._Runner._handle_tool_call`` reserves a write node's
``idempotency_key`` immediately before invoking the tool, and releases it again
immediately after -- on success, on failure, and after a compensating action -- every
normal path releases promptly. The reservation's job is narrower than "block this key for
the rest of the window": it exists only to close the race between two attempts that are
truly CONCURRENT (both pass the ``nx`` check in :func:`reserve_idempotency_key` before
either has finished), which is the one gap a graph's own read-before-write (e.g.
benchmark-3's ``existing_followup_check``) cannot close by itself. Holding the reservation
for the full window on every successful write would also block every legitimate
SEQUENTIAL replay within that window -- and a sequential replay (checkpoint-resume, or a
duplicate Procedure invocation well after the first one fully succeeded) is exactly what
must still be allowed to reach the tool, so the graph's own existing-check can correctly
turn it into an idempotent no-op. If it were never allowed to run again, recovery would
be permanently blocked instead of merely idempotent.

``window_seconds`` therefore only matters in the anomalous case: a worker crashes between
``reserve_idempotency_key`` and the matching release, leaving a reservation stuck with no
one left to release it. 24 hours is proposed for that TTL for three reasons:

1. It matches the existing precedent in this codebase for "how long does an abandoned
   write-adjacent hold stay around before it self-heals" --
   ``huf.ai.tools.code_execution._APPROVAL_TTL_HOURS`` is also 24h. Re-using that order of
   magnitude keeps the system's recovery vocabulary consistent rather than introducing a
   second, unrelated TTL for engineers to reason about.
2. It is long enough that a stuck reservation cannot itself cause a duplicate write within
   any realistic retry/recovery horizon (a transient ``frappe.db`` deadlock retried by an
   RQ job, a human re-running a stuck Agent request, a checkpoint-resume some hours
   later) -- all of which plausibly resolve well within a day.
3. It is short enough that an orphaned entry does not become unbounded state in the
   cache -- eviction after 24h costs nothing correctness-wise, since by then either the
   crashed attempt's write genuinely never happened (safe to retry, graph-level
   idempotency still applies) or it did happen and the graph's own existing-check will
   see it.

If this number needs revisiting per-Procedure, the recommended path is a
``contract.limits.dedup_window_seconds`` override read by
:func:`~huf.ai.graph.procedure_runtime.run_agent_procedure_run`'s caller, not a code
change here -- not built in this task because Benchmark 3 does not need it and I8/D5 do
not ask for it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = [
	"DEDUP_WINDOW_SECONDS",
	"derive_idempotency_key",
	"derive_operation_key",
	"reserve_idempotency_key",
	"release_idempotency_key",
]

DEDUP_WINDOW_SECONDS = 24 * 60 * 60  # 24 hours -- see module docstring "Dedup window"


def _normalise(value: Any) -> Any:
	"""Recursively normalise a value so semantically-identical inputs hash identically.

	Dict keys are sorted (``json.dumps(..., sort_keys=True)`` handles this at the
	serialisation boundary already, but nested non-dict-ordered structures such as sets
	are normalised here first since ``json.dumps`` cannot serialise them at all).
	"""
	if isinstance(value, dict):
		return {k: _normalise(v) for k, v in sorted(value.items())}
	if isinstance(value, (list, tuple)):
		return [_normalise(v) for v in value]
	if isinstance(value, set):
		return sorted(_normalise(v) for v in value)
	return value


def derive_idempotency_key(
	*,
	procedure_name: str,
	procedure_version: str,
	normalised_inputs: Any,
	target_identity: str,
) -> str:
	"""Content-derived idempotency key, per D5.

	``procedure_name`` + ``procedure_version`` (the pinned fingerprint, I6) + the node's
	normalised inputs + ``target_identity`` (the identity of the document this write acts
	on, e.g. ``f"{invoice.customer}:{invoice.name}"`` per
	``benchmarks/benchmark-3-crm-followup/expected-procedure.md``) are hashed together.
	Deliberately excludes any run id, attempt number, or wall-clock timestamp -- including
	any of those would make this run-scoped, which D5 explicitly rejected.

	Pure function: no frappe import, no I/O. Two calls with equal arguments always produce
	the same key, which is the entire point.
	"""
	payload = {
		"procedure_name": procedure_name,
		"procedure_version": procedure_version,
		"inputs": _normalise(normalised_inputs),
		"target_identity": target_identity,
	}
	blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
	return hashlib.sha256(blob).hexdigest()


def derive_operation_key(*, procedure_name: str, node_id: str, target_identity: str) -> str:
	"""Human-legible companion to :func:`derive_idempotency_key`.

	Not used for dedup matching (the hash is) -- carried alongside it on every write
	node/``Agent Tool Call``/``Agent Procedure Step`` purely so a person reading the audit
	trail can tell *what operation* a hash refers to without recomputing it. Deliberately
	NOT run-scoped either, for the same D5 reason: ``recipe_run + node + customer +
	invoice`` per GOAL.md ss2.1's own example is procedure-name + node + target, not run id.
	"""
	return f"{procedure_name}:{node_id}:{target_identity}"


def _reservation_cache_key(idempotency_key: str) -> str:
	return f"agent_procedure_idempotency_{idempotency_key}"


def reserve_idempotency_key(idempotency_key: str, *, window_seconds: int = DEDUP_WINDOW_SECONDS) -> bool:
	"""Atomically reserve ``idempotency_key`` for ``window_seconds``.

	Returns True iff this call won the reservation (no other caller holds it right now) --
	the caller may proceed with the write. Returns False when another attempt already
	holds (or recently held and is still within the window) the same key -- the caller
	must treat this as a duplicate invocation and must NOT perform the write.

	Mirrors ``huf.ai.procedure_lock.acquire_run_lock``'s ``cache().set(..., nx=True)``
	convention exactly -- same primitive, different key namespace and a much longer TTL
	(a run lock is per-advance-step; a dedup reservation must outlive one worker's crash
	and a retry dispatched by a different worker).
	"""
	import frappe

	return bool(frappe.cache().set(_reservation_cache_key(idempotency_key), 1, ex=window_seconds, nx=True))


def release_idempotency_key(idempotency_key: str) -> None:
	"""Release a reservation early -- used by a ``compensate`` recovery step that undoes
	its own write and wants a subsequent attempt to be able to retry immediately rather
	than waiting out the full window. Safe to call even if nothing is held.
	"""
	import frappe

	try:
		frappe.cache().delete(_reservation_cache_key(idempotency_key))
	except (RuntimeError, OSError, AttributeError, KeyError) as exc:
		frappe.logger("huf").debug(f"Idempotency reservation release failed for {idempotency_key}: {exc!s}")
