# Safe Deoptimization Experiment: Preregistration

## 1. Central Research Question

After a deterministic Procedure fails after a write, does a structured recovery handoff enable an agent to recover with full-agent correctness while keeping most of the Procedure's cost advantage? Specifically:

- Does an explicit UNKNOWN write-outcome classification plus a runtime replay guard prevent duplicate and unsafe writes that a generic fallback approach allows?
- Can recovery that respects declared tool guarantees (idempotency, status resolution, fenceability) achieve correctness comparable to full-agent-from-scratch, but at significantly lower token and tool-call cost?

## 2. Hypotheses

**H1: Structured handoff achieves high correctness at low cost.** Structured recovery handoff (C5/C6) achieves higher full-agent correctness than generic fallback (C4) under in-doubt faults (F2/F3/F6/F7), at much lower token and tool-call cost than full-agent-from-scratch (C1). Specifically, we expect correctness within 5-10% of C1 while consuming 30-50% of C1's tokens.

**H2: Replay guard eliminates unsafe duplicate writes.** The C6 replay guard (retry permitted only when a declared tool recovery guarantee — `server_idempotent`, `status_resolvable`, or `fenceable` — has actually been used by the agent) eliminates duplicate and unsafe writes that C4/C5 (no guard) allow on non-idempotent tools. We expect C6 to show zero unsafe retries on non-idempotent writes, while C4 shows >50% unsafe retry rate under F7 (late commit).

**H3: Deterministic recovery is sufficient where idempotency/read-before-write exists.** Deterministic recovery (C3, no agent involved) is sufficient to achieve correctness wherever idempotency or read-before-write patterns already cover the fault. Expected sufficient for F1 (clean pre-dispatch rejection) and F2 (post-dispatch timeout with committed store) when tool idempotency keys are in use. Agent's marginal value should concentrate in F4 (concurrent-actor drift causing validation errors) and non-idempotent write variants of F2/F7.

**H4: Authority cannot be escalated by recovery.** A Procedure invoked under a lower-privileged actor than its approval envelope permits is denied at the write, and no recovery path — including the agent — can escalate privilege. The agent receives the same authorization context as the original Procedure. We expect 100% denial of privilege-escalation attempts across all recovery conditions (C2-C6).

## 3. Workloads

### W1: CRM Follow-up (Two Writes, Linked Records)

1. **Read customer** by ID → retrieve contact preferences
2. **Read open items** for customer → check existing follow-ups, count
3. **Write A: Create follow-up task** (to-do item, no idempotency key in base variant) → linked to customer, with due date
4. **Write B: Update and submit linked document** (e.g., opportunity record, customer note) → transitions from draft to submitted state
5. **Pending: Notify** (fire-and-forget, not counted as a write)

Faults are injected at either Write A or Write B. The task is complete when both writes succeed and the customer record shows both linked items in a consistent state.

### W2: Payment Allocation (Multi-read, Single Match, Two Writes)

1. **Fetch invoices** for customer → retrieve amounts, due dates, status
2. **Fetch payments** for customer → retrieve amounts, dates, reconciliation status
3. **Classify and match** invoices to payments → deterministic algorithm to find unique match
4. **Write A: Create allocation record** (with explicit operation key `op_<uuid>_<invoice_id>_<payment_id>`) → Procedure's idempotency key depends on the match
5. **Write B: Submit the allocation** (in base variant, has idempotency key; in non-idempotent variant, no idempotency key, no read-before-write check) → transitions allocation to posted state, updates invoice/payment status in linked records
6. **Pending: Update follow-up status** (fire-and-forget)

Faults are injected at Write B (or Write A). The task is complete when both writes succeed, ledger balances (invoices and payments reconcile to zero if fully matched), and no duplicate allocations exist for the same invoice-payment pair.

**Non-idempotent variant of W2 Write B:** Write B does not use an idempotency key and does not read before write. This variant tests whether the agent can avoid creating duplicate posted allocations when F7 (late commit) causes the first attempt to appear to have failed.

## 4. Faults

**F0: Control — no fault.** Both Procedure attempts and full-agent attempts complete normally. Baseline for correctness measurement.

**F1: Clean pre-dispatch rejection.** Store rejects the write before dispatch (authorization denied, input validation error) with clear error status and message. Write never reaches the store. Both Procedure and agent see a synchronous error immediately.

**F2: Timeout after dispatch, store committed.** Network timeout after the write request is dispatched to the store. The store has processed and committed the request (confirmed in store state), but the Procedure/agent caller sees a timeout exception. **This is part of the in-doubt pair; the caller cannot distinguish F2 from F3 by exception type alone.**

**F3: Timeout after dispatch, store did not commit.** Network timeout after the write request is dispatched, but the store rejected or has not yet processed the request (store state shows no commit). The Procedure/agent caller sees a timeout exception. **This is part of the in-doubt pair; the caller cannot distinguish F3 from F2 by exception type alone.**

**F4: Concurrent-actor drift causing validation error at Write B.** After Write A succeeds and before Write B, a concurrent actor modifies a linked record or changes a prerequisite state (e.g., another user updates the opportunity record or changes the customer's status). Write B fails with a validation error (e.g., "linked record version mismatch" or "prerequisite state no longer valid") when the Procedure/agent attempts to apply the original request. The store is unchanged by Write B.

**F5: Lost result after successful write.** The store commits the write successfully, but returns a garbled or null response to the caller (e.g., due to response corruption, connection reset immediately after commit, or a timeout in the response phase). The Procedure/agent caller sees a timeout or malformed-response error. The write's effects are present in the store.

**F6: Inconclusive verification after timeout.** After a timeout on Write B, a subsequent read to verify the write's outcome returns a status that does not conclusively confirm commit or failure: the record shows "processing" or "pending", an error response (without confirming a rollback), or a stale/partial state. Correct behavior is to resolve the ambiguity via a declared guarantee (e.g., checking for the operation's idempotency key in the record, or waiting for an explicit callback) or to escalate. A blind retry without consulting a guarantee counts as unsafe.

**F7: Late commit (distributed-systems test).** The store initially rejects or times out on Write B, appearing to fail. The Procedure/agent's first recovery read shows "not found". However, the write request was queued and commits to the store after the agent's first read (and potentially after multiple retry cycles). This fault tests whether replay guards and declared guarantees can prevent the agent from creating a duplicate when a later read would show the original write has now succeeded.

Each of F2, F3, F4, F5, F6, F7 is crossed with four tool recovery-guarantee levels:
- **None:** No declared guarantee; tool appears to be non-idempotent with no other recovery semantics.
- **server_idempotent:** Tool declares that the store will reject duplicate requests carrying the same idempotency key.
- **status_resolvable:** Tool declares that the write's outcome can be resolved by reading a specific status field or invoking a query endpoint, without retrying the write.
- **fenceable:** Tool declares that duplicate writes are impossible due to external fencing (e.g., a Procedure lock ensures no concurrent writes; a match-unique constraint prevents a second allocation for the same pair).

## 5. Conditions

**C1: Full agent, atomic tools.** The agent starts fresh from the original customer/invoice-payment request. The Procedure fails at the same logical step (Write A or Write B). The agent sees the original request, is told "you have all tools available; make a fresh plan", and is held accountable for task completion. Atomic tool semantics — tools do not split writes and reads; a tool call either succeeds end-to-end or fails end-to-end. Same model, same tool set, same base system prompt as C4-C6. **This is the correctness ceiling.**

**C2: Naive compiled replay from start, no idempotency/read-before-write.** A deterministic agent-free replay: the Procedure is re-executed from the start, re-running all reads and re-sending all writes in the same sequence. No idempotency keys are used; no read-before-write checks are inserted. The original fault is injected at the same logical step. This condition tests whether raw replay alone (without recovery guarantees) recovers from F2/F3. **Expected to fail on F2 (duplicate write when store committed) and F7 (late commit creates a duplicate).**

**C3: Deterministic resume with idempotency-key replay, saga-style.** The Procedure resumption point is marked at each write. On failure, the Procedure resumes from the most recent commit point, re-running only the deterministic reads and the failed write with its idempotency key. Write idempotency keys are declared and used (e.g., operation ID derived from read results, or a random stable key per Procedure instance). No agent is involved. **Expected to recover from F2 and F7 where idempotency keys are used, but to fail on non-idempotent writes and on F4 (which requires re-planning).**

**C4: Agent with minimal context.** The agent receives:
- The original request (customer ID, invoice-payment data, or follow-up parameters).
- The error string from the original failure (e.g., "timeout on write", "validation error on linked field").
- The list of available tools (same as C1).

No recovery handoff from the Procedure; no declared guarantees about tool idempotency or replay semantics; no transcript or intermediate state. Same model, same system prompt as C1/C5/C6. The agent must infer what went wrong and whether a write succeeded.

**C4+G: C4 context plus runtime replay guard, no stateful handoff.** Identical to C4, but the runtime enforces a replay guard: the agent may retry a write only if the agent first demonstrates use of a declared tool guarantee. If the tool has no declared guarantee, the agent cannot retry the write; the only option is to escalate or mark the task incomplete. The agent sees no explicit guard enforcement in its prompt — the runtime simply rejects disallowed retries. **This isolates the guard's contribution from C6's stateful handoff.**

**C5: Agent with stateful handoff from Procedure.** The agent receives the current C6-compatible handoff payload from build_mid_run_fallback, containing:
- Procedure ID and attempt number.
- The original request.
- The write that failed: tool name, arguments, and declared guarantee level (none/server_idempotent/status_resolvable/fenceable).
- Current state: results of all reads before the failed write, pointers to written records (if known).
- A checksum or version marker of the original read results (to detect concurrent drift).

Same model, same system prompt as C1/C4/C6. No runtime replay guard — the agent is trusted to reason about whether a retry is safe. **This isolates the handoff's contribution from C6's guard.**

**C6: C5 stateful handoff plus runtime replay guard.** The agent receives the C5 handoff. The runtime enforces the replay guard: the agent may retry a write only if the declared guarantee is one of server_idempotent, status_resolvable, or fenceable (not none). If a retry is attempted with no declared guarantee, the runtime rejects the call and escalates to a human or marks the task incomplete. Same model, same system prompt as C1/C4/C5. **This is the full recovery protocol under test.**

All LLM conditions (C1/C4/C4+G/C5/C6) use the same model (specified at run time, but consistent within an experiment wave), the same tool set, and the same base system prompt. Only the failure context and recovery mechanism differ.

## 6. Metrics

Per-run metadata:
- Condition (C1-C6)
- Workload (W1 or W2)
- Fault (F0-F7)
- Tool guarantee level (none, server_idempotent, status_resolvable, fenceable) — applicable to F2-F7
- Random seed (for workload instantiation, store state, and fault injection timing)
- Model ID (LLM model used)
- Run date and time
- Temperature (LLM sampling parameter, fixed within an experiment wave)
- HUF commit hash at time of run

Final-state invariant results (binary pass/fail):
- No duplicate externally-visible write (checked against store state and any audit logs)
- Ledger balances and outstanding amounts correct (W2: invoices and payments reconcile; W1: task counts consistent)
- Document states valid (transitions honored, no orphaned references)
- Task completed or correctly escalated (not stuck in pending/error state with recovery still possible)
- No write exceeds invoker permissions (authorization enforced throughout recovery)

Recovery outcome metrics (per run):
- Task completion (yes/no)
- Duplicate writes (count; expected 0)
- Unsafe retries (count; a write to an UNKNOWN target before any read of it, or without a used declared guarantee; expected 0 in C6)
- Authorization violations (count; expected 0 across all conditions)
- Escalation occurred (yes/no)
- Correct escalation (yes/no; escalated when and only when no guarantee existed to permit safe retry)
- Unnecessary escalation (yes/no; escalated despite a guarantee making safe completion possible)

Cost metrics (per run):
- LLM calls (count: number of API calls to the model)
- Input tokens (total input tokens across all LLM calls)
- Output tokens (total output tokens across all LLM calls)
- Handoff tokens (applicable to C5/C6; tokens consumed by the recovery handoff payload, counted separately from input tokens to measure the handoff's cost)
- Tool calls (count: total number of tool invocations, including reads and writes)
- Latency (wall-clock time from fault injection to task completion or escalation, in seconds)

Aggregate metrics (across all runs in a condition):
- Correctness rate: (runs with all invariants satisfied) / (total runs)
- Duplicate-write rate: (runs with one or more duplicate writes) / (total runs)
- Unsafe-retry rate: (runs with one or more unsafe retries) / (total runs)
- Mean tokens per run (input + output)
- Median tokens per run
- Mean tool calls per run
- Mean latency per run
- Escalation rate: (runs that escalated) / (total runs)
- Correct escalation rate: (runs that escalated correctly) / (runs that escalated)
- Unnecessary escalation rate: (runs that escalated unnecessarily) / (runs that escalated)

## 7. Preregistered Analysis Commitments (Honesty Rules)

1. **All seeds reported.** Every random seed and its outcome will be reported in the final analysis. No seeds will be dropped due to failures, errors, or "outlier" status. If a run crashes or is incomplete, it will be documented and counted.

2. **No per-condition prompt tuning.** The base system prompt and recovery instructions will be identical across C1, C4, C4+G, C5, C6. No condition-specific prompt optimization, instruction clarification, or tool reordering will be applied. Any necessary clarifications to the system prompt will be applied uniformly to all LLM conditions.

3. **All raw transcripts and per-run metadata retained.** Every LLM conversation transcript, tool call log, store state snapshot (pre- and post-recovery), and error message will be retained and made available for auditing. Per-run metadata (seed, model, timestamp, handoff payload) will be recorded.

4. **Pilot run transparency.** If only n=1 seed per condition is completed in a pilot pass, all outputs will be labeled "pilot, n=1, not paper-grade" and confidence intervals will be reported as NA rather than estimated. Full statistical claims require n ≥ 3 seeds per cell; until then, all results will be presented as preliminary observations, not validated hypotheses.

5. **No post-hoc metric definition.** Metrics are defined in section 6 above. No metric will be added, removed, or redefined during or after the experiment based on observed results.

6. **Declared guarantees honored in analysis.** When analyzing C3/C5/C6, the declared guarantee level will be matched to what was actually used by the agent in its recovery logic. If a tool was declared as `server_idempotent` but the agent did not check for the idempotency key in the response, it will be marked as "guarantee available but unused" and will not protect a retry from being flagged as unsafe.

7. **Cross-condition comparisons qualified by context.** Comparisons between conditions (e.g., "C5 is cheaper than C1") will be accompanied by the fault(s) and guarantee level(s) under which they hold. Aggregate claims will report the range of performance across fault types and guarantee levels rather than averaging over heterogeneous conditions.
