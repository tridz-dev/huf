# W3 -- realistic 5-8 step workload, measured on a real bench

Track-Item: v2-issue-5 (`Tracks/SafeDeoptExperiment/PLAN_V2.md`, "Issue 5").

This report is standalone: **W3's numbers are NOT merged into `summary.csv`**. `summary.csv`
is W1/W2's in-memory fault-injection matrix, driven against a hand-rolled fake store under a
scripted fault injector -- a different ground-truth model and a different workload class from
W3's real-bench, real-DocType run. Averaging or concatenating the two would silently blend
incompatible measurement bases, which is exactly what this file exists to avoid.

## 1. Design

W3 is an 8-step "onboard a new order" flow, sized per the brief (5-8 steps, at least 2 real
writes):

| # | Step | Kind |
|---|------|------|
| 1 | `read_account` | read |
| 2 | `read_prior_orders` | read |
| 3 | `check_eligibility` | pure logic, no I/O |
| 4 | `create_draft_order` | **write A** |
| 5 | `compute_pricing` | pure logic, no I/O |
| 6 | `submit_order` | **write B** |
| 7 | `update_fulfillment_status` | pending / non-critical (performed for real on the bench run, see caveat below) |
| 8 | `notify` | pending / non-critical (logged only, never dispatched -- matches W1/W2's own treatment of `notify`) |

### In-memory version

`benchmarks/safe-deopt/workloads.py` gained (additive; W1's `CrmStore` and W2's
`PaymentAllocationStore` were not touched):

- `Account`, `PriorOrder`, `DraftOrder` dataclasses
- `check_eligibility(account, prior_orders)` and `compute_pricing(account, items_subtotal)` --
  pure functions, no store access
- `OrderProcessingStore` -- mirrors `CrmStore`/`PaymentAllocationStore`'s
  `_CommitLogMixin` + `Authorizer` shape: `create_draft_order` (write A, idempotent by
  `operation_key`) and `submit_order` (write B, idempotent by a distinct `operation_key`
  namespace) are the only two commit-logged writes; `update_fulfillment_status` and
  `notify` are pending/non-critical side channels, exactly like W1's `notify` and W2's
  `update_followup_status`.

This module remains frappe-free, per W1/W2's own design requirement.

### Real-bench version

No submittable DocType exists in `huf` (confirmed zero `is_submittable: 1` doctypes in
`BENCH_VERIFICATION.md`), and installing ERPNext or a workflow-bearing core doctype just for
this experiment was out of scope. Per the task's explicit fallback, "submit" is modeled as
the task brief's own suggested alternative: an `insert()` (write A) followed by a
subsequent `save()` (write B) on the same real `ToDo` record, using its own `status` field as
the draft/submitted proxy (`Open` -> `Closed`). A third `save()` (`priority` field) stands in
for "update related status field" -- performed for real rather than left pending, since it
was cheap and gives a genuine third write to observe. No new custom DocType was created for
W3 (unlike the earlier `Safe Deopt Test Submittable` fixture from `BENCH_VERIFICATION.md`'s
Check 2, which remains scoped to that check only) -- W3 reuses the stock `ToDo` doctype only.

## 2. Bench sync

Per `frappe-multihand`'s §8.1a, the dev worktree's commits are never `docker cp`'d into a
bench checkout. Sync performed:

1. `git push origin research/safe-deopt-experiment` from the dev worktree (fast-forward,
   `a219996f3..2056b35b8`) -- the worktree was already ahead of `origin`, no divergence.
2. Inside `frappe_docker_devcontainer-frappe-1`, `/workspace/development/.sources/huf.git`
   (the shared bare mirror used as the bench's `origin` remote) was fetched from GitHub, but
   its own `refs/heads/research/safe-deopt-experiment` did not update (only its
   `refs/remotes/origin/...` tracking ref did -- the mirror's local branch head is checked
   out by another worktree in the container, so a direct `+refs/heads/*:refs/heads/*` fetch
   was refused: "refusing to fetch into branch ... checked out at
   .../tracks/SafeDeoptExperiment/worktrees/safe-deopt-verify/huf"). This is exactly the
   "refusing to update checked out branch" case the skill anticipates.
3. Per the skill's documented fallback for that exact case, fetched **directly from the
   branch's real upstream (GitHub)** into the bench's own `apps/huf` checkout instead of
   through the local mirror:
   `git fetch https://github.com/tridz-dev/huf.git research/safe-deopt-experiment` from
   inside `/workspace/development/safe-deopt-verify/apps/huf`, then
   `git merge --ff-only FETCH_HEAD` -- clean fast-forward, `be8e56c65..2056b35b8`.

**Confirmed**: `git log --oneline -3` inside
`/workspace/development/safe-deopt-verify/apps/huf` now shows `2056b35b8` at `HEAD`
(`research: wire real model selection, runs.jsonl un-gating, and transcript persistence`),
working tree clean (`git status --short` empty). No `docker cp` was used at any point in this
sync.

Note: this sync brought the bench's `apps/huf` up to the dev worktree's HEAD as of the start
of this task (`2056b35b`) -- it does **not** include the W3 code added afterwards
(`workloads.py`'s `OrderProcessingStore`, `test_workload_w3.py`), since those are committed
in the same commit that finishes this task, after the sync step. The real-bench runs below
therefore do not import `workloads.py`'s `OrderProcessingStore` at all; they drive real
`frappe.get_doc(...)` calls directly (see §3), which is what the task's own fallback allows
("directly call the sequence of real ... operations in the same order a compiled Procedure
would").

## 3. Real-bench runs

Bench: `safe-deopt-verify.local` inside `frappe_docker_devcontainer-frappe-1`, driven via
`bench --site safe-deopt-verify.local console`, scripts piped in from
`safe-deopt-verify/tmp_checks/` (per `BENCH_VERIFICATION.md`'s own note that `/tmp` is not
writable in this container for the exec user).

**Console-piping gotcha found and worked around**: piping a multi-line Python script directly
into `bench console`'s IPython REPL as raw stdin does not behave like running a `.py` file --
function/class bodies compiled that way can silently lose access to names imported earlier in
the same "session" (IPython executes `exec(code_obj, self.user_global_ns, self.user_ns)` with
**two distinct dicts** for globals vs. locals; a plain `import`/`from...import` at the top
level lands in `user_ns` (locals) but a `def`'s `__globals__` is bound to `user_global_ns`,
so top-level imports become invisible inside function/class bodies compiled in a later
"cell"). Two failure modes were hit and fixed:
- A closure/`global` reference to a bare module-level name (e.g. a plain list used as a call
  counter) raised `NameError` when called back from inside `run_recovery`'s callback --
  fixed by moving all mutable state onto object attributes (`self.x`) instead of bare
  globals.
- Even with an attribute-based class, a class whose `__init__` referenced a name imported
  earlier (`MockedModel`) raised `NameError: name 'MockedModel' is not defined` -- root
  cause confirmed to be the globals/locals split above.
- **Fix**: pipe a single line that does
  `ns={}; exec(compile(open("<absolute path to script.py>").read(), "<name>.py", "exec"), ns, ns)`
  -- passing the SAME dict as both `globals` and `locals` to `exec` forces normal
  single-namespace module-execution semantics, exactly like running a real `.py` file. This
  is the technique both real-bench runs below actually used (visible in the exact commands
  below). This is worth fixing/documenting in `frappe-multihand`'s own examples if future
  console-piped scripts define any function or class.

Both runs below were executed twice each to sanity-check for gross timing noise; the
compiled-path average feeds `results/breakeven.json`'s
`w3_bench_measured_discovery_timing_seconds` (see §4).

### 3a. Compiled/procedural path

Direct sequential calls to real `frappe.get_doc(...).insert()` / `.save()` / `frappe.db.get_value`,
in the exact order a compiled Procedure's write-runtime would issue them -- **not** routed
through `execute_procedure` (which is deliberately frappe-free itself and only touches Frappe
through a caller-supplied `tool_invoker`; wiring a full pinned-`Procedure` graph definition
just to drive 3 writes was judged not worth the scaffolding for this task, matching the
allowance already used in `BENCH_VERIFICATION.md`'s Check 1). Script:
`safe-deopt-verify/tmp_checks/w3_compiled.py`. Command:

```
echo 'ns={}; exec(compile(open("/workspace/development/safe-deopt-verify/tmp_checks/w3_compiled.py").read(), "w3_compiled.py", "exec"), ns, ns)' \
  | bench --site safe-deopt-verify.local console
```

| Run | Wall time (s) | Real DB/tool calls |
|-----|---------------|---------------------|
| 1 | 3.9695196410175413 | 7 |
| 2 | 3.82298550195992 | 7 |
| **avg** | **3.8962525714887306** | 7 |

The 7 calls: `read_account` (1 `db.get_value`), `read_prior_orders` (1 `get_all`),
`create_draft_order` (1 `insert`), `submit_order` (1 `save` + 1 `db.commit`),
`update_fulfillment_status` (1 `save`), final verify (1 `db.get_value`). Both writes (and the
third, pending-turned-real status update) committed and were independently re-read back via
`frappe.db.get_value`, confirming `status="Closed"`, `priority="High"`.

**Timing caveat, stated honestly**: this wall time is dominated by `bench console`'s
per-statement IPython round-trip overhead (each `In [n]:` line has its own
parse/compile/echo cost), not pure MariaDB query latency -- this is a real, reproducible cost
of driving Frappe this way in this environment, but it should not be read as "a compiled
Procedure replay costs ~3.9s in production." A production `execute_procedure` call (no
console REPL in the loop) would be substantially faster. This is disclosed here precisely so
`breakeven.json`'s new field is not misread as a tighter claim than it is.

### 3b. Full-agent simulation (scripted, mocked-model, real-bench-writes)

Same 8-step sequence, but every read/write step is dispatched through
`recovery_harness.py`'s shared `run_recovery` tool-calling loop and `AtomicTool` abstraction
(condition `C1`, no guard), driven by a `MockedModel` script -- **scripted, not a real LLM
decision process**; no API key is available in this sandbox (see `recovery_harness.py`'s own
module docstring). This is a real-bench-writes / mocked-model run: the bench I/O cost is
real, the "agent's" tool-call choices are not. Labeled honestly per the brief's requirement
that "real bench" and "real model" be disclosed independently. Script:
`safe-deopt-verify/tmp_checks/w3_full_agent.py`. Command: same `ns={}; exec(compile(...), ns,
ns)` pattern, targeting that file.

| Run | Wall time (s) | `run_recovery` tool-call count | Total real DB/tool calls (all 8 steps) | Loop outcome |
|-----|---------------|-------------------------------|-----------------------------------------|--------------|
| 1 | 3.240590638946742 | 5 | 8 | `final_text` |
| 2 | 3.2398338080383837 | 5 | 8 | `final_text` |
| **avg** | **3.2402122234925628** | 5 | 8 | -- |

`run_recovery`'s own loop drove the first 5 tool calls (`read_account`,
`read_prior_orders`, `create_draft_order`, `submit_order`, `update_fulfillment_status`) as
discrete tool-call round-trips (transcript append + dispatch + result, matching how a real
from-scratch agent would have to discover and invoke each atomic action one at a time,
rather than as inline method calls in one procedural script); the model's 6th step was a
scripted `final_text` ("done"), ending the run. Total real DB/tool calls (8) is higher than
the compiled path's (7) because `submit_order` and `update_fulfillment_status` each perform
an explicit `frappe.db.commit()` as a separate accounted call in this script (the compiled
path shares one commit across two of its writes) -- a real difference in how the two scripts
were written, not a claim about inherent full-agent overhead; see §5 for what would need to
change to make this a fair apples-to-apples call-count comparison.

**Same timing caveat as 3a applies.** Additionally: this run's near-identical wall time to
the compiled path (3.24s vs. 3.90s) should NOT be read as "a full agent is as cheap as a
compiled Procedure on a real bench" -- both numbers are dominated by the same fixed
per-console-statement overhead, and this scripted mock skips the actual cost a real LLM would
add (multiple full-context model inference calls, one per tool-call turn, each with real
latency and token cost that a `MockedModel` fundamentally cannot represent). The real gap
this experiment is measuring elsewhere (`summary.csv`'s C1 vs. C5/C6 comparisons) is about
tool-call count and token cost under mocked timing, not literal bench wall-clock -- W3's
purpose here was specifically to get one REAL (non-mocked) wall-clock number onto the record
for `breakeven.json`, which it does (see §4), not to re-derive the full C1-vs-compiled cost
gap on real infrastructure (that would need a real, timed LLM in the loop).

## 4. Feed into `breakeven.json`

`results/breakeven.json` previously had `procedure_proposal_timing_seconds: null` (documented
as "not measured -- huf/ai/procedure_proposal.py imports frappe at module scope and this
sandbox has no frappe/bench installed"). That specific gap is still not closed --
`procedure_proposal.py` was not run here either, and the field is left `null` with its
original note intact.

Instead, a **new, clearly-separate field** was added:
`w3_bench_measured_discovery_timing_seconds: 3.8962525714887306` (the compiled path's average
from §3a), with a `w3_bench_measured_discovery_note` explaining exactly what it measures and
why it is not folded into `procedure_proposal_timing_seconds`: that field names the cost of
`procedure_proposal.py`'s discovery/proposal step specifically (still unmeasured), while this
new field is a real-bench-measured substitute discovery-cost proxy for a different thing
entirely -- the wall-clock cost of replaying a compiled procedure's real write path on real
infrastructure. Conflating the two would misrepresent what was actually measured, hence the
separate field rather than overwriting the `null`.

## 5. Known limitations / what this does NOT prove

- Both real-bench wall times are dominated by `bench console`/IPython per-statement overhead,
  not pure DB latency -- disclosed in §3a/§3b; do not read either number as a production
  per-call latency figure.
- The full-agent path's tool-call sequence is scripted (`MockedModel`), not decided by a real
  LLM -- it proves the atomic-tool/`run_recovery` plumbing works end-to-end against a real
  bench, not that a real agent would choose this exact sequence or take this long.
- The two scripts' call-count accounting differs slightly in how many `frappe.db.commit()`
  calls are counted (compiled: 1 shared commit; full-agent: 2, one per write) -- a
  fair-apples call-count comparison would need to normalize this; not done here since the
  point of this task was to get one real timing number on record, not to re-litigate the
  call-count-gap claim already covered by `summary.csv`'s mocked matrix.
- `update_fulfillment_status` was performed as a REAL third write on the bench (rather than
  left pending, as the in-memory `OrderProcessingStore` treats it) purely because it was
  cheap to do with the same `ToDo` record already open; this is a documented divergence
  between the in-memory workload's semantics (pending/non-critical) and what the real-bench
  script actually did (real write) -- called out here rather than silently glossed over.
- No new custom DocType was created for W3; it reuses the stock `ToDo` doctype, with its
  `status`/`priority` fields standing in for a submit workflow and a fulfillment-status field
  respectively, since `huf` has no submittable doctype of its own (per
  `BENCH_VERIFICATION.md`).
