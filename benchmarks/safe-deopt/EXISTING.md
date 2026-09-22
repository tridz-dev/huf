# HUF Procedure Runtime: Existing Guarantees

This document records what HUF's existing Procedure runtime (`huf.ai.graph.procedure_runtime` and supporting modules) already guarantees regarding ordering, idempotency, fallback recovery, and write safety — so a safe-deopt experiment paper can cite it accurately without overstating what exists today or understating what it actually does.

## 1. Procedure Runtime Core (`procedure_runtime.py`)

### Execution Model and Ordering Guarantees

**execute_procedure** (lines 942-1051):
- Executes a pinned Procedure graph to completion sequentially, in memory, using a single call — no RQ routing, no Flow Run persistence (GOAL.md section 10, synchronous fast path).
- Takes an already-pinned `PinnedVersion` (the graph is pinned at Procedure activation time, never re-read from the database during execution).
- Is **entirely frappe-free**: the only seam to the outside world is the `tool_invoker` callable passed in. Authorization and telemetry are delegated to the invoker, never handled here.
- Node visitors are recorded in `_VisitRecorder` (lines 342-388) in visit order, with callbacks fired:
  - `node_start`: fired BEFORE a node's handler runs (T-40 checkpointing: "step started" recorded ahead of side effects — GOAL.md ss2.2)
  - `node_end`: fired AFTER node completion, both success and failure
- `tool_invocations` list (lines 205-213, 421) records every attempt at a tool.call node, in order: `[{"node_id", "tool_id", "args", "success", "result", "error", ...}, ...]`

### Recovery Modes (T-40, GOAL.md ss2.3)

Every write-classified tool.call node MUST declare a recovery mode (`node.config["recovery"]`). The runtime enforces this statically before invoking any write tool (lines 586-597).

**RECOVERY_RETRY** (line 143):
- Bounded: exactly one extra attempt, never a loop (line 629).
- Safe only because the idempotency key reservation (see idempotency.py) makes a retried write a no-op if the first attempt actually committed (line 127).
- Invoked on failure after the first attempt (lines 628-644).

**RECOVERY_RESUME** (line 144):
- Fail this node closed; do not retry inline.
- The run as a whole is resumable only by re-invoking the Procedure from the top — NOT by resuming from a saved mid-node cursor.
- Already-completed steps are idempotent no-ops on replay (i.e., the read-before-write check or the idempotency key prevents duplicates).

**RECOVERY_ABORT** (line 145):
- Fail this node closed, no retry, no implied resume guidance beyond the normal fallback payload.
- The default when a node declares no recovery mode; a write-classified node MUST declare one explicitly (I8, lines 592-597).

**RECOVERY_COMPENSATE** (line 146):
- On failure, best-effort invoke `node.config["on_compensate"]` (a static tool_id + args) before failing the node closed (lines 646-710).
- The invocation is *best-effort* — never fatal. A compensation failure must not mask the original failure it is trying to clean up.
- After compensation, release the idempotency reservation so a subsequent attempt is not blocked by the window (line 666).

### Idempotency Key Requirement on Write Nodes

**_handle_tool_call** (lines 557-680):
- Lines 578-585: Write-classified nodes MUST carry an `idempotency_key` in args. A write without one fails closed immediately, before any tool invocation:
  ```
  f"tool.call node '{node.id}' invokes write tool '{tool_id}' without an idempotency_key 
  (D5: every write node must carry one, content-derived -- procedure version + procedure 
  name + normalised inputs + target document identity). Refusing to invoke."
  ```
- The key is never run-scoped. It is content-derived from procedure name, procedure version (pinned fingerprint), normalized node inputs, and target document identity (idempotency.py, lines 115-141).

### Concurrent Tool Execution (T-30)

- Parallel branches execute on real OS threads, but results are reassembled in declaration order regardless of completion order (lines 872-939, "Determinism").
- Two semaphores bound concurrency:
  - Per-graph: `graph_semaphore` acquired per parallel branch (lines 437-438)
  - Per-tool: `_tool_semaphore` acquired per tool invocation (lines 449-459)
- Sequential execution of branches happens within each branch's own worker thread; a branch's tool.call nodes never run concurrently with one another.

### Limits and Fail-Closed Semantics (I7)

- `_check_wall_time` (lines 463-469): max_wall_time_ms
- `_charge_external_call` (lines 471-477): max_external_calls
- Output budget (lines 742-780): max_rows, max_output_bytes — enforced by `enforce_output_budget` (huf.ai.output_budget module)
- Foreach iteration cap (lines 788-800): min(node.max_iterations, contract.max_foreach_iterations)
- All breaches raise `ProcedureLimitExceeded`, fail closed — never silently truncate or continue past the limit (I7).

## 2. Idempotency (`idempotency.py`)

### Key Derivation (D5)

**derive_idempotency_key** (lines 115-141):
- Pure function: takes procedure_name, procedure_version (pinned fingerprint), normalised_inputs, and target_identity.
- Content-derived, NOT run-scoped. Two independent runs with identical procedure, inputs, and target collide on the same key.
- Normalisation (lines 99-112) recursively sorts dicts, unrolls sets, so semantically identical inputs hash identically.
- The idempotency_key is passed as an arg to every write node and MUST be present in args when the node is invoked (procedure_runtime.py, lines 578-585).

### Reservation and Release (`reserve_idempotency_key`, `release_idempotency_key`)

**reserve_idempotency_key** (lines 160-175):
- Uses `frappe.cache().set(..., nx=True, ex=window_seconds)` — atomic set-if-not-exists with TTL.
- Returns True iff this call won the reservation; False when another caller already holds or recently held the same key.
- Closes the race between two CONCURRENT attempts that both pass this check before either finishes (lines 31-32: "the one gap a graph's own read-before-write cannot close by itself").

**release_idempotency_key** (lines 178-188):
- Releases early via cache delete — NOT required on success.
- Called on every path: success, failure, or after compensation (line 666 in procedure_runtime.py).

### Dedup Window (D5, TRACKER.md R-9)

**DEDUP_WINDOW_SECONDS** (line 96): 24 hours (86400 seconds)

**Purpose**: Understood as an *orphan-reservation TTL*, not a hold duration. 
- A window is a reservation that never gets released (worker crashed between reserve and release).
- It must eventually self-heal rather than block that key forever (lines 56-73 of idempotency.py docstring).
- It does NOT block sequential replays: a successful write releases immediately (line 649 in procedure_runtime.py), so a subsequent checkpoint-resume or duplicate invocation can reach the tool again.
- The graph's own read-before-write (e.g., benchmark-3's `existing_followup_check` condition) is what turns a sequential replay into an idempotent no-op; the window just unblocks the invoke itself (lines 48-54 of idempotency.py).

## 3. Fallback Protocol (`fallback.py`)

### Fallback Classes

Two mutually exclusive failure classes (T-32, I9):

**PROCEDURE_NOT_APPLICABLE** (lines 14-21):
- `contract.applies_when` evaluated false BEFORE any node ran (execute_procedure, line 984).
- By construction, zero side effects: no tool invocations, no node visits, no partial execution.
- Payload carries NO `completed_steps`, `failed_step`, `committed_writes`, `pending_writes`, `intermediate_outputs`, `error`, or `safe_recovery_actions` keys (lines 99-122, test_fallback.py lines 186-196).
- Its mere absence of these keys is proof to a caller that nothing ran.

**PROCEDURE_FAILED_MID_RUN** (lines 23-26, 244-296):
- One or more nodes ran; the run may have committed writes.
- Payload carries the full GOAL.md ss2.4 shape: `completed_steps`, `failed_step`, `committed_writes`, `pending_writes`, `intermediate_outputs`, `error`, `safe_recovery_actions`, `available_atomic_tools`.

### Committed Writes vs. Pending Writes

**_committed_and_pending_writes** (lines 154-197):

**committed_writes** (lines 154-165, **CRITICAL FINDING**):
- **Every *attempted* write tool.call in outcome.tool_invocations, whether it reported success or not.**
- Lines 158-165 state explicitly:
  ```python
  """``committed_writes`` -- every *attempted* write tool.call in
  ``outcome.tool_invocations``, whether it reported success or not: a write tool that
  raised or returned ``success=False`` may still have partially committed (the runtime
  has no transactional guarantee across a tool boundary), so this module never assumes
  a failed write is a no-op -- that is exactly the retry-duplicates-a-write trap T-32
  warns about. Each entry keeps ``success`` so the Agent can tell "definitely
  committed" from "attempted, outcome unknown" without this module guessing for it.
  ```
- This is **not** a record of confirmed-committed writes. It is a record of every write attempt.
- The `success` field distinguishes "definitely committed" from "attempted, outcome unknown".
- **This is exactly the COMMITTED/UNKNOWN conflation that a new C6 replay guard is meant to fix.** A paper citing `committed_writes` as evidence of real commit-state tracking will overstate what exists today and must account for this gap.

**pending_writes** (lines 186-195):
- Write-classified `tool.call` nodes declared anywhere in the graph (via `iter_reachable_nodes`, including foreach/parallel nested nodes) that were never attempted.
- Safe to skip entirely (never attempted, nothing to undo) or to run explicitly via an atomic tool call.

### build_mid_run_fallback

**Lines 244-296**:
- Takes a `ProcedureOutcome` with `status == FAILED` (enforced lines 265-269).
- Calls `_bounded_intermediate_outputs` to enforce output budget (lines 221-241, I7: never raise on breach, drop to a marker instead — lines 200-218, _never_raise_spill callback).
- Returns the full payload with `committed_writes`, `pending_writes`, and `available_atomic_tools` (line 295).

## 4. Test Coverage

### test_benchmark3_write_runtime.py

**Scenario**: Write-bearing CRM follow-up Procedure (T-40 acceptance).
- Setup: in-memory ToDo store, hand-written fake invoker, hand-rolled Redis-like cache for idempotency testing.
- Proves: unmarked write node is refused, duplicate invocation within dedup window is a no-op, mid-run failure produces the correct partial-failure shape, replay after failure converges to exactly the right document count.
- **Does NOT prove**: real Frappe `frappe.get_doc("ToDo", ...).insert()` under real MariaDB, real `Agent Tool Call`/`Agent Procedure Step` row persistence through a bench worker crash, or real `huf.ai.tool_invocation.invoke_tool_sync` authorization/telemetry wiring.

**Key Test**: "recovery run heals without duplicating" (benchmark3_invariants.py, implicit in the recovery run assertion).
- Mechanism: After a mid-run failure, re-invoke the Procedure from the top.
  - Previously-completed write nodes return idempotent no-ops (the read-before-write check prevents duplicates).
  - New tool invocations are recorded in the second run's `tool_invocations`.
  - The test asserts that the final document count matches the logical expectation (no duplicate ToDos).

### test_procedure_runtime_benchmark4.py

**Status**: Currently SKIPS because `benchmarks/benchmark-4-reconciliation/` is absent from the repo (lines 36-52, unittest.SkipTest).

**Scenario** (if fixtures existed): Batch-scale reconciliation under T-30 concurrent runtime.
- Proves: scheduler bounds, determinism under simulated I/O latency, parallel fan-out (two fetch branches) followed by bounded foreach (payment classification).
- Simulates tool layer via hand-written fake invoker (matching algorithm from expected-procedure.md implemented in Python).

### test_fallback.py

**Coverage**: Frappe-free acceptance test of fallback builders (T-32).

**Two applicability cases**:
1. NOT_APPLICABLE (lines 145-208): zero side effects, no tool invocations (FakeInvoker never called).
2. FAILED_MID_RUN: one test class per Procedure node type (tool.call, transform, condition, foreach, validate, output).

**Missing-Tool Case** (lines 286-303, `TestToolCallFailure::test_read_tool_call_failure_is_marked_safe_to_retry`):
- Graph: one tool.call node with `tool_id="get_customer"` (read-only).
- Invoker: empty table (get_customer absent), so the tool fails.
- Outcome: `status=FAILED`, `node_id="get_customer"`.
- Fallback payload: `committed_writes=[]` (a read tool is never a write), `safe_recovery_actions` contains "safe to retry".

**Critical Note**: This is a tool-invocation failure (the tool was attempted, returned an error). It is **NOT_COMMITTED-before-dispatch evidence** — the call was dispatched (it reached the tool_invoker), it just failed. This is different from an in-doubt (timeout-after-dispatch) fault, which would not appear in `committed_writes` either (because the outcome would be `success=False`, and the test would need to account for possible partial commit via the Agent's own read-verify logic). The test proves that a missing/failed read-only tool does not get flagged as a potentially-committed write, which is correct; it does not prove in-doubt recovery.

## 5. Known Limitations and Gaps

### Transactional Boundaries

- The runtime has no transactional guarantee across a tool boundary. A write tool that returns `success=True` may have partially committed, and a write that returns `success=False` may have fully committed (procedure_runtime.py lines 161-165).
- The `committed_writes` field in a fallback payload records **attempts**, not confirmed commits (fallback.py lines 158-165).
- This is the COMMITTED/UNKNOWN conflation that a new C6 replay guard (out of scope for this document) is meant to address.

### Dedup Window Self-Healing

- The 24-hour dedup window is designed to self-heal orphaned reservations (worker crashed between reserve and release).
- It does not prevent true duplicate writes under concurrent, independent invocations — it only closes the race between two attempts that are truly concurrent on reserve/release.
- The graph's own read-before-write (e.g., an `existing_check` condition node) is the primary guard against duplicates.

### No Persistent Cursor for Resume

- Recovery via `resume` mode is not a saved mid-node cursor; it is re-invocation of the Procedure from the top.
- Already-completed steps become idempotent no-ops only because the graph includes read-before-write logic, not because the runtime tracks persistent execution state.

### Output Budget (I7)

- Intermediate outputs in a fallback payload are bounded via `enforce_output_budget` with a "never-raise" spill callback (fallback.py lines 207-218).
- A breach is dropped to a marker, not persisted anywhere — no spill sink (e.g., Agent Context Artifact integration) is in scope for this task.

### Parallel Execution is Sequential

- Branches are executed sequentially on real OS threads, not truly concurrently. Results are reassembled in declaration order for determinism.
- Real bounded concurrency (T-30) is not in this task's scope.

---

**Document Version**: 2026-09-22
**Scope**: HUF Procedure runtime (T-23/T-40/T-32) as of safe-deopt-experiment branch
**Reviewer Target**: safe-deopt paper — cite these guarantees (and limitations) accurately
