# Guarantee-contract test results (Task T2, ACCEPTANCE_PLAN_V2.md ss2)

Status: **Done for this worktree.** Deterministic, no-LLM, no-network tests added at
`benchmarks/safe-deopt/tests/test_guarantee_contracts.py` (+ `tests/conftest.py` for the
`robustness_only` marker registration). Run against the code as it exists on
`research/safe-deopt-experiment` in `/Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-experiment/huf`.

Pre-existing suite: 193 passed, 1 skipped (unchanged). With the new file: **209 passed, 1
skipped** (193 + 16 new tests, all passing; the pre-existing skip is untouched --
`test_real_procedure_integration.py`'s own `pytest.importorskip("huf.ai.graph.procedure_runtime")`,
since `huf` is not importable stock in this environment).

## Per-contract results

| # | Contract | Status | Test(s) |
|---|---|---|---|
| 1 | Committed timeout | **Holds** | `TestCommittedTimeout::test_f2_commits_once_but_reports_timeout` |
| 2 | Uncommitted timeout (same shape as #1) | **Holds** | `TestUncommittedTimeout::test_f3_same_shape_as_f2_but_never_commits` |
| 3 | F4 validation rejection (no committed mutation) | **Fixed 2026-09-23 (was: gap found, robustness_only)** | `TestF4ValidationRejection` (3 tests, all normal/passing, no `robustness_only` marker) |
| 4 | Late commit (pending -> UNKNOWN -> commits unless fenced) | **Holds** | `TestLateCommit::test_f7_pending_then_commits_on_recovery_read`, `test_f7_fenced_before_recovery_read_never_commits` |
| 5 | Server idempotency (real mechanism) | **Holds** | `TestServerIdempotency::test_same_key_and_payload_cannot_produce_a_second_effect`, `test_concurrent_reservation_blocks_the_losing_attempt_before_dispatch` |
| 6 | Status resolution (COMMITTED/NOT_COMMITTED/UNKNOWN) | **Holds** | `TestStatusResolution` (5 tests) |
| 7 | Fencing (successful fence actually blocks the original) | **Holds** | `TestFencing` (3 tests) |

## Evidence detail

**1 -- Committed timeout.** `FaultInjector.inject("F2", ...)` on
`PaymentAllocationStore.submit_allocation`: asserted `ObservedResult.ok is False` and
`error` is `TimeoutFault`, while `store.commit_log` gained exactly one `committed=True`
entry for that `operation_key`, and the allocation/invoice state actually changed
(`status == "submitted"`, invoice decremented). Confirms F2 both commits for real and
reports failure to the caller.

**2 -- Uncommitted timeout, same shape.** Ran F2 and F3 with the identical
`operation_key`/`action` against two independent stores, then asserted `ok`, `value`,
exception type, and `str(error)` are byte-for-byte identical between the two -- i.e. the
caller cannot distinguish them from the response alone -- while ground truth diverges:
F2's store shows one committed entry and `status="submitted"`; F3's store shows zero
committed entries and `status="draft"`.

**3 -- F4 validation rejection. FIXED 2026-09-23 (was: gap confirmed, "commit-then-fabricate").**
`_inject_f4` now checks the store's own `commit_log` after dispatch and only reports a
validation rejection when write B genuinely produced no new committed effect; when no
`concurrent_mutation` is supplied it synthesizes a real competing write (rather than a
fabricated error) so a genuine rejection is still possible. `test_f4_commit_then_fabricate_bug_is_present`
was renamed to `test_f4_does_not_fabricate_when_the_real_write_actually_commits` and now
asserts the FIXED behavior (`observed.ok is True`, no fabricated error, when the drift only
touches a sibling field the store never validates); a new
`test_f4_synthesizes_a_genuine_rejection_when_no_concurrent_mutation_is_given` covers the
default (no-`concurrent_mutation`) path every real `run_experiment.py` cell uses. Neither
carries `robustness_only` any more. Original gap description, for history:
`FaultInjector._inject_f4` (`benchmarks/safe-deopt/faults.py`) calls
`real_write_fn(*args, **kwargs)` and only decides what to fabricate for the caller based
on whether that call *raised* -- it never checks whether the real write actually
committed. `PaymentAllocationStore.submit_allocation` does not validate against any
invoice-level drift at all (it only checks the allocation's own `operation_key` /
`status` / permission state). So when the "concurrent actor" mutates a *sibling* record
(the invoice's `outstanding_amount`) rather than the allocation being submitted itself,
`real_write_fn` neither raises nor no-ops: it commits normally (one new `committed=True`
`commit_log` entry, `status` flips to `"submitted"`), and the injector *still* fabricates
a `ValidationErrorFault` on top of that real commit. The caller is told "validation
failed" while the write landed for real -- exactly the "commit, then fabricate a
validation error" shape the task asked to check for, and it reproduces deterministically
(`test_f4_commit_then_fabricate_bug_is_present`, marked `@pytest.mark.robustness_only`,
asserts this CURRENT broken behavior explicitly so the suite stays green while flagging
the gap loudly).

A contrast test (`test_f4_does_not_fabricate_when_store_naturally_rejects`, not marked --
this one holds) shows F4 is *not* universally broken: when the concurrent mutation
collides with something `submit_allocation` actually checks (submitting the same
allocation through a different `operation_key` first), the store's own
`already_submitted`/duplicate-key checks mean no second committed mutation results for
the fault's own `operation_key`, even though the injector still fabricates a validation
error. The bug is specifically in the *synthesized-fallback* path when the store
performs no relevant validation of its own.

**Not fixed here, on purpose.** Per the task's instruction, this was not patched:
`faults.py` is a shared harness module also being read/exercised by other in-flight work
in this same worktree on this branch (a concurrent agent explicitly flagged
`recovery_harness.py`, `procedure_vs_naive.py`, `llm_real_procedure_integration.py` as its
own in-progress files during this task), and changing F4's semantics now is a
harness-behavior change with a scope well beyond "confined to test code" -- it would
change what every existing F4-consuming test and harness observes. This is flagged here
and in the test file's docstring rather than silently patched or silently left
undocumented, per ACCEPTANCE_PLAN_V2.md ss2's "never advertise an unimplemented guarantee
... intentionally-broken guarantees go in a separately labeled robustness experiment."

**4 -- Late commit.** Immediately after `inject("F7", ...)`: zero committed entries, and
`get_operation_status(..., injector=injector)` correctly resolves `"UNKNOWN"` (not a false
`NOT_COMMITTED`). The first `wrap_read()` call returns the pre-write value (`"draft"`) but
triggers the held write to land for subsequent observers -- verified the allocation
flips to `"submitted"`, one committed entry appears, and status becomes `"COMMITTED"`
immediately after that same call returns. A second scenario fences the operation via
`cancel_operation` *before* any recovery read: the first read still returns the
pre-commit value, but the held write never lands (`flush_held_write` also then returns
`False`), and status resolves to a terminal `"NOT_COMMITTED"`.

**5 -- Server idempotency, exercised behaviorally through the REAL mechanism.** This
worktree has no `frappe` package installed at all (`import frappe` raises
`ModuleNotFoundError`, not just "no site" -- consistent with what
`recovery_harness.py`'s own docstring already documents), and `huf/__init__.py` does an
unconditional `import frappe` at package top level, which blocks importing
`huf.ai.graph.idempotency` directly. To exercise the REAL, unmodified
`reserve_idempotency_key`/`release_idempotency_key` functions (rather than accepting a
declared label or re-implementing the logic in the test), the test installs the smallest
possible `frappe` stub into `sys.modules` -- a `.cache()` returning a `set(key, value,
ex=None, nx=False)` / `delete(key)` object mirroring the real Redis-backed cache
contract idempotency.py's own docstring describes, plus `.logger(name)` for
`huf/__init__.py`'s import-time logging setup. Nothing in `huf/ai/graph/idempotency.py`
itself is modified, mocked, or bypassed; only the module-level `import frappe` boundary
is satisfied. Two tests: (a) a `reserve -> dispatch -> release` pattern (mirroring
`procedure_runtime._Runner._handle_tool_call`'s own shape) run twice with the identical
key against the real `PaymentAllocationStore.submit_allocation` shows exactly one
committed effect even though the write function was invoked from two separate
"attempts"; (b) a direct concurrent-race test shows a second `reserve_idempotency_key`
call for a still-held key returns `False` (loses the race) and only wins after
`release_idempotency_key`. Both assert actual committed-effect counts / reservation
booleans, never a declared guarantee label.

**6 -- Status resolution.** Five cases: a `COMMITTED` op's status refers to that exact
key (a different, never-touched key independently resolves `NOT_COMMITTED`, not
conflated); a never-attempted key is a terminal `NOT_COMMITTED`; an `F3` (uncommitted
timeout) key stays `NOT_COMMITTED` even after a further `flush_held_write` attempt (there
is nothing pending under that key, so nothing can later flip it); an `F7` pending key
resolves `UNKNOWN` (explicitly asserted not to be either terminal value); and calling
`get_operation_status` *without* an injector for a pending F7 key falls back to
`NOT_COMMITTED` rather than fabricating `COMMITTED` -- i.e. missing evidence never
produces a false positive.

**7 -- Fencing.** A successful `cancel_operation` before any read/flush means the
original held write can never land: `flush_held_write` afterward returns `False`, two
subsequent `wrap_read()` calls (which would otherwise trigger the commit) leave the
allocation at `"draft"` with zero committed entries, and status resolves terminally to
`NOT_COMMITTED`. A companion test shows a *failed* fence attempt (nothing pending, or
already committed) correctly reports `False` and must not be treated as protection.
An end-to-end test drives `conditions.ReplayGuard` directly: a session that only
performed a bare read is rejected when attempting the fenceable retry (rule 3: a read
never unlocks anything); a session that actually recorded a successful fence is admitted,
and the resulting retry produces exactly one committed effect for that operation_key (the
retry itself, not a resurrection of the fenced-off original).

## Files

- `benchmarks/safe-deopt/tests/test_guarantee_contracts.py` -- the 7 contracts, 16 test functions
- `benchmarks/safe-deopt/tests/conftest.py` -- registers the `robustness_only` pytest marker,
  scoped to this tests directory only (does not touch the repo-root `pyproject.toml`)

No file under `huf/ai/graph/` or other real HUF runtime source was modified. No paid API
calls, no network access, and no LLM calls were made by any of these tests.
