# Final Adversarial Review v2 (T9, ACCEPTANCE_PLAN_V2.md)

Reviewer scope: T1-T8 deliverables in this track, plus the branch diff
`research/safe-deopt-experiment..research/safe-deopt-v2-integration` in
`worktrees/safe-deopt-v2-integration/huf` (HEAD `0e20f6204`), and PR #750's live body.
Date: 2026-09-23.

## Verdict

**NOT ready for final human review.** The stopping-rule condition in Sec.7 ("after these
checks pass") is not met. Two §3 mandatory sub-requirements are violated in the T4 code,
the "0 of 14" duplicate reassessment is wrong for at least 4 rows, a headline "Supported"
C4+G-vs-C6 claim rests on a metric that carries no model signal, and PR #750 does not
contain the v2 artifacts it links to. None of this needs new experiments of a new kind;
it needs a T4 fix + rerun of 10 rows, a corrected T5 reassessment, and doc/PR fixes.

Secret scan: **clean.** `AIza[A-Za-z0-9_-]{20,}` / `sk-[A-Za-z0-9_-]{20,}` over the full
v2 commit log patches, `benchmarks/safe-deopt/`, this track directory, and PR #750's body
returned only `sk-not-a-real-key-for-testing` in
`benchmarks/safe-deopt/tests/test_live_api_model_openai.py` (pre-existing placeholder,
commit `1e9eff168`, not from T1-T8).

## Critical

**C1. §3 "no prefilled status dictionary" is violated; T4's headline finding depends on it.**
`benchmarks/safe-deopt/llm_real_procedure_integration.py:562-566` — `_check_status` returns
`_GROUND_TRUTH_STATUS[id(real_invoker)]["write_b"]`, a module-level dict, and never queries
Frappe. `bench_scripts/run_llm_real_procedure_suite_v2.py:177` sets it to `"COMMITTED"`
*before* `run_llm_recovery_case` even runs the fault (the docstring at lines 721-724 claiming
it is set "right after calling run_fault_case, using the REAL tool_invocations" is false).
For S2-S5 `set_ground_truth_status` is never called, so `check_status` unconditionally
returns `"UNKNOWN"` regardless of persisted state. The value also flows into
`resume_via_retry_write_b(known_status=...)`, i.e. into the guard's decision. Consequently
the "GPT-4o-mini retried after COMMITTED and the real guard blocked it" finding
(CLAIM_TO_EVIDENCE_TABLE §2 row 3, §6 row 4; PR body; REPORT.md v7) is a guard reacting to a
hardcoded label, not to status resolved from persisted state.
Fix: implement `check_status` as a real read of the ToDo / commit ledger for the exact
operation key (UNKNOWN only when genuinely pending), rerun the 10 T4 rows, and downgrade the
affected claims until then.

**C2. "0 of 14 duplicates survive" is incorrect for the 4 `server_idempotent` rows.**
`analysis_openai_c5_duplicates_v2.md` asserts these 4 (lines 3445/3446/3465/3466) reflect
"the underlying fault's own double-commit shape". But T2 contract #1 proves F2 commits
*exactly once*, so a duplicate cannot come from the fault alone. Raw row 3445: workload
`W2-nonidempotent`, `tool_guarantee: server_idempotent`, transcript shows the model calling
`submit_allocation_unsafe`, `duplicate_writes: 1`. That is precisely the §2 case "declaring
`server_idempotent` is not enough": a declared server-idempotent cell produced a second
effect. Scoring also records `dispatched_unsafe_retries: 0` for a row whose transcript
contains an unsafe-tool dispatch — a scorer miscount. C5 lacking a guard does not excuse a
guarantee the *tool/store* declares.
Fix: reclassify these 4 as unresolved declared-guarantee failures (or harness labeling
defects), fix the `dispatched_unsafe_retries` scoring for this path, and change "0/14" to
"at most 8/14 explained as expected no-guard behavior; 4 unexplained; 2 F4-confounded".

**C3. The "useful_completion tied exactly (0.5 vs 0.5)" claim is vacuous.**
Over live-model C4+G and C6 rows in `scored_v2/scored_rows.jsonl`, useful_completion is a
pure function of fault: F2/F4/F6 = 100%, F1/F3/F7 = 0%, in both conditions and both
families (re-derived: F2 288/288, F6 288/288, F4 72/72, F1 0/72, F3 0/288, F7 0/288). F2 and
F3 are caller-indistinguishable (T2 #2) yet split 100/0, so the metric reads ground-truth
commit state, not model recovery behavior. "C4+G matches C6 on correctness"
(CLAIM table §3 row 2, §9 row 2 "now on stronger grounds", REPORT.md v7 line ~53, PR body)
therefore does not survive. Also, the 72 F4 rows are inside the "matched" set despite the
F4 exclusion.
Fix: reclassify as Unsupported (metric does not measure recovery quality), drop F4 from the
matched set, and say so; the token/cost/latency differences can stay Limited.

## High

**H1. §4 "rerun affected fault/guarantee cells" was not done.** `runs.jsonl` rows carry
`huf_commit_hash 86f1b0ee...`, not the pinned checkout; F4 (180 rows) was found broken by T2
but neither fixed nor rerun — it was only excluded from "guarantee conclusions" while staying
in cost and completion aggregates (EXCLUSIONS §1). F4 was an unintentional harness bug, not an
"intentionally-broken guarantee"; the robustness_only label is being used to avoid the
required rerun. Fix: either fix `_inject_f4` and rerun F4 cells at the original models/seeds,
or drop F4 from *all* aggregates and state that the plan's rerun requirement is unmet for it.

**H2. PR #750 does not contain the v2 work.** Remote head of `research/safe-deopt-experiment`
is `5a5ad72a2`; `research/safe-deopt-v2-integration` does not exist on origin. The v7 links
(`../blob/research/safe-deopt-v2-integration/Tracks/...`) are dead twice over: that branch is
unpushed, and `Tracks/` lives in the workspace repo, not `huf`. Fix: tell the reviewer where
the artifacts actually are (workspace path + local branch SHA `0e20f6204`), or push the branch
with approval.

**H3. PR #750 body still states contradicted claims without inline supersession.** Lines 14
and 50-53 still say "both models correctly avoid an unsafe retry once a real status check
confirms COMMITTED" (contradicted by T4's own GPT finding), "C6 costs 1.6x-3.7x more tokens"
(withdrawn), "3600 real API rows" (288 are quarantined), and "break-even timing is real".
§7 requires removing these or marking them superseded. Fix: strike or label each in place.

**H4. Pinned checkout is not pinned.** REPORT.md v7 cites HEAD `89918b20` while T4/T5/T6
results were produced by later commits (`d469c2608`, `5fdd5441c`, `950d488a2`) and T4 ran on
the bench with uncommitted files `docker cp`'d in. Fix: record in PINNED_CHECKOUT.md which
commit produced each result file, and the final SHA `0e20f6204`.

## Medium

- **M1.** CLAIM table's headline split "37 Supported / 1 Limited" counts rows with n=1 or n=2
  as Supported; the PR headlines 37. Lead with the stricter 27/10 split.
- **M2.** CLAIM §2 row 1 / §9 row 1 "0 duplicates in guarded conditions across 3312 rows" is
  correct as a number but inherits C2's scoring miscount; qualify until scorer is fixed.
- **M3.** EXCLUSIONS §6 lists OpenAI CUST-0001/0004 as both "escalation/model-caused" and
  "budget-caused (40/40 cap)"; one classification per failure. Also check T6's budget of 40
  tool calls was "large enough for valid completion" per §5 — two cap hits suggest not.
- **M4.** CLAIM §6 row 1 ("10 real runs") is traced only by `wc -l`; given C1, "through the
  real runtime" should be Limited until the rerun.
- **M5.** T4 report says `check_status->COMMITTED` for Gemini S1 too; same hardcoded source.

## Low / scope

- Scope creep: acceptable overall. Runtime files touched on the v2 branch (`procedure_runtime.py`,
  `permissions.py`, `fallback.py`, doctype JSON) come from the pre-existing PR #751/#753 commits
  merged for T1, not from T2-T8. T4 deleted `_replay_guard_standalone.py` (in scope). The
  README change in `0e20f6204` is doc-only.
- The pre-existing in-bench flake (EXCLUSIONS §5) is fine as disclosed.
- Track still lacks TRACK.yaml / TRACKS.md registration (noted by T4 itself).

## Section-by-section §1-§7 status

| § | Status | Blocking gap |
|---|---|---|
| 1 Freeze | Partial | H4 |
| 2 Contracts | Met (F4 gap properly found) | — |
| 3 Integration | **Not met** | C1 (no-prefilled-status; status must query persisted state). Dispatch vs commit counters separate: met. Drain before final check: met (S3 flush + ToDo count). Same identity S5: met. Avoid/escalate allowed: met. |
| 4 Reconcile | **Not met** | C2, C3, H1 |
| 5 Proc vs agent | Met, minor M3 | — |
| 6 Lifecycle | Met | — |
| 7 Delivery/stop | **Not met** | H2, H3; overclaim "matches on correctness" |

## Required before submission

1. Fix `_check_status` to read persisted state; rerun the 10 T4 rows; update claims.
2. Correct the 14-duplicate reassessment (4 server_idempotent rows) and the scorer's unsafe-dispatch count.
3. Withdraw/qualify the useful_completion equivalence claim; remove F4 from matched cells.
4. Resolve F4 rerun-vs-drop per H1.
5. Fix PR #750 body (supersede stale lines, fix artifact location) and pin result-to-commit mapping.
