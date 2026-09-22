# HUF integration evidence via the REAL Procedure runtime

Track-Item: v3-issue-d (`Tracks/SafeDeoptExperiment/PLAN_V3.md`, "Issue D").

This report is the deliverable the review demanded and W3 explicitly did not provide:
"Direct Frappe calls alone do not establish this." W3 (`w3_bench_report.md`) drove real
Frappe writes directly, never through `execute_procedure` itself. This report runs a
write-bearing workload THROUGH the actual `huf.ai.graph.procedure_runtime.execute_procedure`,
the real `huf.ai.graph.fallback.build_mid_run_fallback`, and a real recovery path -- with
fault injection happening at the `tool_invoker` boundary `execute_procedure` itself calls,
not at an in-memory store's write method.

## 1. Bench sync

Per `frappe-multihand`'s S8.1a, the dev worktree's commits are synced into the bench
checkout via git, never `docker cp`:

1. `git push origin research/safe-deopt-experiment` from the dev worktree -- fast-forward,
   `75dbeb1be..861d61bd0`.
2. Inside `frappe_docker_devcontainer-frappe-1`, fetched directly from GitHub into the
   bench's own `apps/huf` checkout (the shared bare mirror route was expected to be
   contended by another concurrent worktree, per this task's own briefing -- W3's exact
   documented fallback was used directly rather than re-discovering the same mirror
   conflict): `git fetch https://github.com/tridz-dev/huf.git research/safe-deopt-experiment`
   from `/workspace/development/safe-deopt-verify/apps/huf`, then
   `git merge --ff-only FETCH_HEAD` -- clean fast-forward, `be8e56c65..861d61bd0`.

**Confirmed**: `git log --oneline -3` inside
`/workspace/development/safe-deopt-verify/apps/huf` shows `861d61bd0`
("research: surface blocked_retries and per-invariant violations as separate metric
columns") at `HEAD`, matching the dev worktree's `HEAD` at the start of this task exactly.
No `docker cp` was used to move any file that is part of this git history; the two new
files this task adds (`real_procedure_integration.py`,
`tests/test_real_procedure_integration.py`) were staged into the bench checkout via
`docker cp` ONLY as a temporary, pre-commit test-execution surface (since they did not yet
exist in git) -- they are delivered to the repository the normal way, by the commit at the
end of this task, and the bench checkout was never treated as a substitute for that commit.

Bench identity: `safe-deopt-verify` / `safe-deopt-verify.local`, per
`Tracks/SafeDeoptExperiment/BENCH_VERIFICATION.md`. Verified running:
`docker exec frappe_docker_devcontainer-frappe-1 sh -c 'ls /workspace/development/safe-deopt-verify'`
returned the expected bench directory layout; `bench --site safe-deopt-verify.local console`
started cleanly.

## 2. The real Procedure graph

`benchmarks/safe-deopt/real_procedure_integration.py`'s `build_two_write_procedure_graph`
builds the smallest write-bearing shape `execute_procedure` can actually run, mirroring
W1's CRM-followup read -> write A -> write B chain:

```
read_target (tool.call, read)
  -> write_a (tool.call, write, recovery=resume, operation_key=<content-derived>)
    -> write_b (tool.call, write, recovery=resume, operation_key=<content-derived>)
      -> output (output)
```

Each write node's `operation_key`/`idempotency_key` is computed once at graph-build time
(D5: `"{procedure_name}:{node_id}:{target_identity}"`), never inferred at call time. A
small dict-backed `classify_tool` (`make_classifier`) marks `read_target` as `read`,
`write_a_create_todo` as `create`, `write_b_update_status` as `write` -- fed to BOTH
`execute_procedure(classify_tool=...)` (so its own idempotency/recovery machinery in
`_Runner._handle_tool_call` engages) and `build_mid_run_fallback(classify_tool=...)` (one
source of truth, never duplicated).

The real `tool_invoker` used on the bench (`w_issued_real_run.py`, run via
`bench --site safe-deopt-verify.local console`, using the `ns={}; exec(compile(...), ns,
ns)` technique from `w3_bench_report.md` to avoid the IPython globals/locals bug):

- `read_target` -> `frappe.db.exists("ToDo", {"description": target_identity})`
- `write_a_create_todo` -> `frappe.get_doc({"doctype": "ToDo", "description": ...}).insert()`
  + `frappe.db.commit()`
- `write_b_update_status` -> looks up the ToDo by description, sets `status = "Closed"`,
  `.save()` + `.commit()`

## 3. Fault injection at the tool_invoker boundary

`wrap_tool_invoker_with_fault(real_invoker, target_tool_id=..., injector, fault_id,
guarantee_level)` returns a new `ToolInvoker` that passes every non-targeted `tool_id`
straight through, and for the targeted one (`write_b_update_status`), routes the call
through `benchmarks/safe-deopt/faults.py`'s existing `FaultInjector.inject` -- the SAME
fault semantics already used for W1/W2's in-memory-store boundary, now wrapping the real
Frappe-backed `tool_invoker` call instead. `ObservedResult` (faults.py's shape) is
translated to `ToolInvocation` (procedure_runtime.py's shape) -- the only place this
adapter bridges the two modules' independently-designed vocabularies.

## 4. Results -- each fault through the REAL execute_procedure + REAL build_mid_run_fallback

All four runs below executed for real on `safe-deopt-verify.local`, each against a fresh,
uniquely-identified `ToDo` target (`safe-deopt-issued-f1` / `-f3` / `-f5` / `-f7`) so no
run's idempotency reservation or ground truth could bleed into another's.

| Fault | Guarantee level | `execute_procedure` outcome | Real DB state after (`ToDo.status`) | `build_mid_run_fallback` produced? | Result |
|---|---|---|---|---|---|
| F1 (clean rejection) | none | `FAILED` -- `"rejected before dispatch: write_b_update_status (...)"` | `Open` (write A committed, write B never dispatched) | Yes -- `failed_step: "write_b"`, `committed_writes` contains `write_a` (success) and `write_b` (attempted, failed) | **PASS** |
| F3 (uncommitted timeout) | status_resolvable | `FAILED` -- `"timeout: no confirmation received for write_b_update_status (...)"` | `Open` (real write never dispatched -- F3 deliberately never calls through) | Yes -- same shape as F1, `failed_step: "write_b"` | **PASS** |
| F5 (lost result / committed-but-response-lost) | none | `SUCCESS` (node succeeded -- `ObservedResult.ok=True`, `value=None`) | `Closed` (real write DID land) | No -- run is SUCCESS, `fallback_payload: null` (by construction: `build_mid_run_fallback` only applies to FAILED outcomes) | **PASS** (see note below) |
| F7 (late commit) | fenceable | `FAILED` -- `"timeout: no confirmation received for write_b_update_status (...)"` | `Open` (write HELD, not yet landed -- correct: nothing has triggered `FaultInjector.wrap_read` yet for this operation_key) | Yes -- same shape, `failed_step: "write_b"` | **PASS** |

**F5 note, stated honestly**: `execute_procedure`'s `_handle_tool_call` treats any
`ToolInvocation(success=True, ...)` as a succeeded node regardless of whether `result` is
`None` -- so a "lost result" (real write commits, caller told success with no evidence)
makes the WHOLE PROCEDURE run report `SUCCESS`, and `build_mid_run_fallback` correctly
never fires for it (it only ever handles `FAILED` outcomes, per its own contract --
verified by inspection and by this run). This is not a bug in the adapter or in
`execute_procedure`: it is F5's exact, intended shape ("committed but response lost") and
this run demonstrates that shape holds all the way through the real runtime -- the real
`ToDo` really is `Closed`, and the run's own `tool_invocations` record shows
`{"tool_id": "write_b_update_status", "success": true, "result": null}`, i.e. the runtime
genuinely has no way to distinguish this from a garbled-but-successful call by inspecting
its own outcome alone. This is exactly the gap the paper's guarantee-level machinery
(`status_resolvable` / `get_operation_status`) exists to close on the AGENT side, not
something `execute_procedure` itself is expected to detect.

**F7 additional check**: triggering `injector.wrap_read(operation_key, ...)` for the same
key after the fault (as `faults.py`'s own docstring specifies: "the FIRST call after the
fault triggers the held write to land") was verified separately in the unit test
`test_f7_late_commit_holds_real_write_until_read` (passes against a fake store) -- the
real-bench run above stops at the fault-injection point itself (one `execute_procedure`
call = one Procedure attempt), matching how a real agent's recovery turn would need to
issue a SEPARATE read/probe action to trigger F7's delayed commit; that separate action is
outside `execute_procedure`'s own single-run scope by design.

## 5. Authority/permission denial through the REAL tool_invoker-embedded path

Per the task's explicit ask, this is NOT the workload-authorizer layer
`BENCH_VERIFICATION.md`'s Check 2 already covered -- authorization here is embedded
directly in the `tool_invoker` closure that `execute_procedure` calls, exactly as
`huf.ai.graph.permissions.authorize_tool_call` is embedded in `run_agent_procedure_run`'s
real invoker (per `procedure_runtime.py`'s own module docstring).

Reused the same fixture `BENCH_VERIFICATION.md`'s Check 2 built (`Safe Deopt Test
Submittable`, `is_submittable: 1`, submit restricted to System Manager) since no
submittable doctype exists in stock `huf`/`frappe` on this bench (confirmed again here;
no new app installed). `write_b`'s tool_id (`write_b_privileged_status_update`) was
pointed at this doctype's `.submit()` call, gated by a real `frappe.has_permission(...,
ptype="submit", doc=name, user=...)` check performed INSIDE the invoker closure --
`execute_procedure` itself never sees or decides this; it only sees the resulting
`ToolInvocation(success=False, error=...)`.

Acting user: `safe-deopt-lowpriv-issued@example.com`, role `Blogger` (no submit
permission on the fixture doctype).

**Result: PASS**

```
lowpriv_has_submit_permission: false
outcome_status: failed
outcome_error: "PermissionError: user safe-deopt-lowpriv-issued@example.com lacks submit
                permission on Safe Deopt Test Submittable ghdu84ii5k"
real_db_state_after: {"exists": true, "name": "ghdu84ii5k", "docstatus": 0}
```

`docstatus: 0` confirms the document was never actually submitted -- the denial is real,
not just a returned error string with a silent submit underneath. `build_mid_run_fallback`
fired correctly (`failed_step: "write_b"`, `committed_writes` records write A's success and
write B's failed attempt).

**Note on `frappe.has_permission` and `ToDo`**: the first attempt at this check reused the
stock `ToDo` doctype for write B (mirroring the earlier faults' shape) and found
`frappe.has_permission("ToDo", ptype="write", user=<Blogger>)` returns `True` -- `ToDo` is
not permission-gated in a way that denies a `Blogger` role, so that shape could not
demonstrate a real denial. Switched to the same restricted fixture doctype
`BENCH_VERIFICATION.md` already built for exactly this reason, rather than silently
reporting a false "authority passed" result. Documented here rather than hidden, per the
task's honesty requirement.

## 6. Pytest results (adapter logic tested without a live bench)

`benchmarks/safe-deopt/tests/test_real_procedure_integration.py` -- 8 tests. Discovered
during this work: `execute_procedure`'s write-node idempotency reservation
(`huf.ai.graph.idempotency.reserve_idempotency_key`) calls `frappe.cache()`, which is
`None` outside a bootstrapped Frappe site -- so a full run through a write node genuinely
needs a live site, not just an importable `huf` package. Tests are split accordingly:

- **Frappe/bench-free** (4 tests, always run): graph shape (two writes, distinct
  `operation_key`s, `recovery` declared), the classifier, and the adapter's pure
  `tool_id`-routing/passthrough logic against a hand-rolled fake `tool_invoker`.
- **`@requires_live_site`** (4 tests: F1, F3, F5, authority denial -- skipped outside a
  live Frappe site, confirmed run for real against `safe-deopt-verify` above instead): the
  full run through a write node.

On the bench (`safe-deopt-verify.local`, `PYTHONPATH=. env/bin/python -m pytest
benchmarks/safe-deopt/tests/test_real_procedure_integration.py -v`): **8 passed** (all,
including the `@requires_live_site` ones, since a real site is present there).

On this dev worktree (no `frappe` installed): **1 skipped** (whole-module
`pytest.importorskip`, since `huf` itself imports `frappe` at package init) -- this is the
expected, honest behavior for an environment without `frappe`/`huf` installed, not a
failure.

Full suite regression check, this worktree:

```
python -m pytest benchmarks/safe-deopt/tests/ -v
168 passed, 1 skipped, 4 subtests passed
```

The 1 skip is `test_real_procedure_integration.py`'s whole-module skip (no `frappe`
locally); nothing this task touched broke any of the other 168 passing tests (Issue A's
concurrent work on `recovery_harness.py`/`run_experiment.py` was not modified by this task
at all, per the collision-avoidance instruction).

## 7. Summary

| Case | Real `execute_procedure` run? | Real `build_mid_run_fallback`? | Real Frappe write outcome | Pass/Fail |
|---|---|---|---|---|
| F1 clean rejection | Yes | Yes | write A committed, write B never dispatched | PASS |
| F3 uncommitted timeout | Yes | Yes | write A committed, write B never dispatched | PASS |
| F5 committed-but-response-lost | Yes | N/A (SUCCESS, by design) | write A + write B both committed | PASS |
| F7 late commit | Yes | Yes | write A committed, write B held (not yet landed) | PASS |
| Authority denial (real tool_invoker closure) | Yes | Yes | write A committed, write B denied, not submitted | PASS |

Nothing in this task was fabricated or extrapolated: every row above is a literal
re-read of `frappe.db` state and the actual `ProcedureOutcome`/fallback payload produced
by the real code paths, on the real bench, in this session.
