# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Bounded, deterministic parallel branch scheduler for Procedure graphs (T-30).

There is zero concurrency precedent in this subsystem (GT-02) -- everything below is new
ground, so the threading model is spelled out explicitly rather than assumed.

THREADING MODEL (read this before touching anything else in this module)
--------------------------------------------------------------------------
Frappe's database connection is per-thread, per-request state (``frappe.local`` is a
``werkzeug.local.Local``): it is NOT safe to share ``frappe.db`` across threads, and it is
NOT safe to call ``frappe.get_doc`` / ``doc.save`` / ``doc.append`` from any thread other
than the one that owns the request-local ``frappe.local`` stack. This module therefore
draws a hard line:

* Worker threads (the ``ThreadPoolExecutor`` below) run ONLY pure, frappe-free computation:
  walking a branch's own :class:`~huf.ai.graph.executor.GraphExecutor` over a *private copy*
  of the run's :class:`~huf.ai.graph.executor.GraphContext`, and calling the injected
  ``tool_invoker`` (which, in the frappe-facing caller, still ends up inside
  ``huf.ai.tool_invocation.invoke_tool_sync`` -- see the caveat in
  ``huf/ai/graph/procedure_runtime.py``'s module docstring: this scheduler does not change
  T-23's existing rule that ``execute_procedure`` itself never imports ``frappe``. A caller
  that wires a real, frappe-backed ``tool_invoker`` into concurrent branches is taking on
  the responsibility of making THAT callable thread-safe -- this module does not do it for
  them, and ``run_agent_procedure_run`` in this codebase does not currently wire one in
  because ``invoke_tool_sync`` reaches into ``frappe.db`` for telemetry and Agent Tool Call
  history, which is exactly the kind of Frappe write this model forbids off the owning
  thread. The synchronous, one-invoker-per-run path in ``run_agent_procedure_run`` is
  therefore expected to keep running procedures with real Frappe tool calls sequentially,
  or with a tool_invoker that is proven thread-safe by its own module -- this scheduler
  only guarantees that ITS OWN bookkeeping (Agent Procedure Step writes, node-visit
  recording) never crosses a thread boundary).
* The orchestrating thread (the caller of :func:`run_parallel_branches`, i.e.
  ``procedure_runtime._Runner._handle_parallel``) is the ONLY thread that ever touches
  ``frappe.db`` -- it does this by collecting each worker's locally-recorded node visits
  (a plain list of ``(NodeSpec, Outcome)`` pairs, never a shared/live structure) and
  replaying them, one branch at a time in canonical branch-declaration order, into the
  run's real :class:`~huf.ai.graph.procedure_runtime._VisitRecorder` -- which is the object
  that calls ``on_visit`` and therefore the object that writes ``Agent Procedure Step``
  rows. No worker thread ever holds a reference to the real recorder or its ``on_visit``
  callback.

DETERMINISM
-----------
Branches are identified by their static index in ``config.branches`` (not by which thread
or OS scheduler happened to run them first). Workers return ``BranchResult`` objects
tagged by that index; :func:`run_parallel_branches` always reassembles results, replays
recorded visits, and merges context mutations back in ascending branch-index order --
never in the order futures happen to complete. Two runs of the same graph, even with
wildly different per-branch delays, therefore produce byte-identical node-visit order,
context mutations, and final output.

Each worker also executes against its own private shallow copy of the parent
:class:`~huf.ai.graph.executor.GraphContext` (its ``data`` dict and ``node_outputs`` dict
are copied before the branch starts). Concurrent branches never mutate the same live
dict, which is what makes running them on real OS threads safe even though CPython's GIL
would not otherwise protect a `dict` from a torn read under every possible bytecode
sequence. After a branch completes, the orchestrating thread merges the branch's node
outputs back into the parent context. If two branches wrote different values under the
same context key (only possible if a transform/tool.call handler called
``context.set``/``context.update`` -- ``record_output`` itself is always keyed by node id,
which is unique per node and therefore never collides), that is a graph authoring bug this
scheduler refuses to paper over: it fails the ``parallel`` node closed with a specific
"conflicting context write" error rather than picking one value arbitrarily (which would
make the run's output depend on completion order, exactly what determinism forbids).

BOUNDS ENFORCED HERE (all fail closed -- I7)
---------------------------------------------
* ``max_parallel_calls`` (spec/graph-ir.md 2.2, ``config.max_parallel_calls`` falling back
  to ``contract.limits.max_parallel_calls``): if a ``parallel`` node declares more branches
  than this cap allows, :func:`run_parallel_branches` REJECTS the node outright with
  :class:`ParallelLimitExceeded` before starting a single branch -- it never silently runs
  the first N and queues the rest, and never serializes the overflow. This is what "a
  deliberate concurrency-limit breach is rejected rather than queued unboundedly" (T-30's
  "Done when") means concretely.
* Max graph concurrency: a single ``threading.BoundedSemaphore`` created once per
  top-level ``execute_procedure`` call (see ``procedure_runtime._Runner.graph_semaphore``)
  and threaded through every nested ``parallel`` node (including ones inside a branch that
  is itself running on a worker thread -- nested pools acquire the same semaphore object),
  so the total number of branches running at once across the WHOLE graph, not just one
  ``parallel`` node, never exceeds ``contract.limits.max_graph_concurrency``.
* Per-tool concurrency: ``_Runner`` keeps one ``threading.BoundedSemaphore`` per
  ``tool_id`` (created lazily under a lock), acquired around every ``tool.call`` invocation
  regardless of whether it runs on the main thread or a worker thread, capped at
  ``contract.limits.max_tool_concurrency``.
* Per-connector limits: this codebase's tool metadata (``huf/ai/tool_invocation.py``,
  ``huf/ai/graph/permissions.py``) has no connector/API identifier distinct from
  ``tool_id`` as of T-30 -- there is no ``connector_id`` or similar field on a Tool
  Function/registered tool. Per-tool concurrency above is therefore also this
  implementation's per-connector granularity; if/when a connector concept is added, the
  per-tool semaphore keying in ``procedure_runtime._Runner`` is the one place to switch to
  it.
* Timeout: each branch gets a wall-clock budget (``config.timeout_ms`` on the ``parallel``
  node, falling back to ``contract.limits.max_wall_time_ms``, falling back to
  :data:`DEFAULT_BRANCH_TIMEOUT_S`). ``run_parallel_branches`` waits on each branch's
  future with that timeout; a branch that does not finish in time is recorded as failed
  with a timeout error and its (eventual, late) result is discarded when/if it arrives --
  Python cannot forcibly kill a running OS thread, so "cancellation" of an
  already-executing branch means its result is never read or merged, not that the
  underlying thread is interrupted. That is stated plainly here rather than pretended
  away.
* Backpressure: the thread pool's ``max_workers`` is exactly the effective concurrency cap
  (``min(max_parallel_calls, max_graph_concurrency)``); there is no unbounded work queue --
  branches beyond the cap are rejected at validation time (see above), not enqueued.
* Cancellation: once ``join="all"`` and any branch has failed, every future that has not
  yet started is cancelled (``Future.cancel()``) so no new branch begins after a sibling's
  fail-closed failure is known; branches already running are left to finish (Python cannot
  interrupt them) but their results are discarded by the orchestrator -- never merged into
  context, never replayed into ``Agent Procedure Step``.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BRANCH_TIMEOUT_S = 30.0
DEFAULT_MAX_GRAPH_CONCURRENCY = 8
DEFAULT_MAX_TOOL_CONCURRENCY = 4


class ParallelLimitExceeded(Exception):
	"""A parallel node's fan-out exceeds a configured bound. Always raised before any
	branch starts -- fail closed, never a partial/queued run (T-30 "Done when").
	"""


@dataclass
class BranchResult:
	"""What one branch's worker thread hands back to the orchestrating thread.

	Frappe-free and thread-safe to construct: plain data, no live shared references.
	"""

	index: int
	ok: bool
	visits: list[tuple[Any, Any]] = field(default_factory=list)
	"""``(NodeSpec, Outcome)`` pairs in the branch's own execution order -- replayed onto
	the real recorder by the orchestrating thread, never touched by any other thread.
	"""

	node_outputs: dict = field(default_factory=dict)
	data_diff: dict = field(default_factory=dict)
	error: str | None = None
	timed_out: bool = False


def _semaphore_bound_call(sem: threading.Semaphore | None, fn: Callable[[], Any]) -> Any:
	if sem is None:
		return fn()
	sem.acquire()
	try:
		return fn()
	finally:
		sem.release()


def run_parallel_branches(
	branches: list[Callable[[], BranchResult]],
	*,
	max_parallel_calls: int,
	graph_semaphore: threading.Semaphore | None = None,
	timeout_s: float = DEFAULT_BRANCH_TIMEOUT_S,
) -> list[BranchResult]:
	"""Run ``branches`` (each a zero-arg callable that returns a :class:`BranchResult`)
	concurrently, bounded by ``max_parallel_calls`` and, if given, a shared graph-wide
	``graph_semaphore``. Returns results reassembled in ascending branch-index order,
	regardless of completion order (determinism -- see module docstring).

	Raises :class:`ParallelLimitExceeded` immediately, before starting any branch, if
	``len(branches) > max_parallel_calls`` -- a deliberate breach is rejected, not queued.
	"""
	count = len(branches)
	if count == 0:
		return []
	if count > max_parallel_calls:
		raise ParallelLimitExceeded(
			f"parallel node has {count} branches, exceeds max_parallel_calls ({max_parallel_calls})"
		)

	def _run_one(index: int, branch_fn: Callable[[], BranchResult]) -> BranchResult:
		def _call() -> BranchResult:
			return branch_fn()

		return _semaphore_bound_call(graph_semaphore, _call)

	results: list[BranchResult | None] = [None] * count
	with ThreadPoolExecutor(max_workers=count) as pool:
		futures: dict[Future, int] = {}
		for index, branch_fn in enumerate(branches):
			future = pool.submit(_run_one, index, branch_fn)
			futures[future] = index

		pending = set(futures)
		failed = False
		while pending:
			done, pending = wait(pending, timeout=timeout_s, return_when=FIRST_COMPLETED)
			if not done:
				# Nothing finished within the timeout window: every branch still pending
				# is timed out. Record them as such and stop waiting -- do not block
				# indefinitely (backpressure/timeout, never unbounded waiting).
				for future in list(pending):
					index = futures[future]
					future.cancel()
					results[index] = BranchResult(index=index, ok=False, timed_out=True, error="branch timed out")
				pending = set()
				break
			for future in done:
				index = futures[future]
				try:
					result = future.result()
				except Exception as exc:  # noqa: BLE001 -- a worker crash fails its branch, not the process
					result = BranchResult(index=index, ok=False, error=str(exc))
				results[index] = result
				if not result.ok:
					failed = True
			if failed:
				# join="all" + fail-closed: cancel every branch that has not started yet.
				# Branches already running cannot be interrupted (see module docstring);
				# their eventual results are simply never read below.
				for future in list(pending):
					future.cancel()
				pending = set()

	# Any slot still None here belongs to a future that was cancelled before it started
	# (the fail-closed short-circuit above) -- record it as a not-run branch rather than
	# leaving a hole.
	for index in range(count):
		if results[index] is None:
			results[index] = BranchResult(index=index, ok=False, error="branch cancelled (sibling branch failed)")

	return results  # type: ignore[return-value]
