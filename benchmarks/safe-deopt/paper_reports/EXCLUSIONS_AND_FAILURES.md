# Exclusions and Failures (T8, ACCEPTANCE_PLAN_V2.md ss7)

Plain list of everything excluded from analysis, quarantined, or that failed, with exact
source citations. No editorializing.

## 1. F4 fault: robustness_only, excluded from valid-guarantee conclusions

- `CONTRACT_TEST_RESULTS.md` #3: F4 validation-rejection contract has a confirmed gap
  ("commit-then-fabricate" — the fault injector commits for real, then fabricates a
  validation error on top). Marked `@pytest.mark.robustness_only` in
  `benchmarks/safe-deopt/tests/test_guarantee_contracts.py` (registered via
  `tests/conftest.py`).
- Per `ACCEPTANCE_PLAN_V2.md` Sec.2: "Intentionally-broken guarantees go in a separately
  labeled robustness experiment, excluded from valid-guarantee conclusions."
- Scope of exclusion in the main dataset: 180 rows out of 3600 in
  `benchmarks/safe-deopt/results/runs.jsonl` have `fault == "F4"` (traced: direct count over
  the raw file, matches `RECOVERY_RESULTS_RECONCILED.md` sec 7(a)'s stated figure). These
  rows are excluded from guarantee-contract conclusions specifically, not from general
  correctness/cost aggregates (`RECOVERY_RESULTS_RECONCILED.md` sec 7(a)).
- Scope in the T4 5-scenario integration suite: F4 is not used in any of the 5 scenarios;
  the prior (v1) round's scenario-to-fault mapping had mistakenly assigned F4 to what is now
  correctly scenario S4/fault F1 — corrected in
  `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` ("What changed vs. the prior round" item 3).
- Scope in the OpenAI C5 duplicate finding: 2 of the 14 duplicate-committed-effect rows
  (fault F4, seeds 42/43) are excluded from being counted as genuine guarantee-contract
  violations for this reason (`analysis_openai_c5_duplicates_v2.md`, per-case reassessment
  table). Of the remaining 12, 4 (server_idempotent, F2/F6, seeds 42/43) are now
  reclassified as genuine unresolved guarantee violations, not F4-related -- see
  `RECOVERY_RESULTS_RECONCILED.md` sec 6 (corrected 2026-09-23) and
  `analysis_openai_c5_duplicates_v2.md`.
- **Scope in the matched C4+G-vs-C6 comparison (added 2026-09-23, per
  `FINAL_ADVERSARIAL_REVIEW_V2.md` H1/C3):** `results/scored_v2/matched_c4g_vs_c6.json`'s
  648-cell matched set included 72 F4 rows (36 per condition) despite F4's robustness_only
  status everywhere else in this project -- an inconsistency, now resolved: **F4 is
  excluded from the matched C4+G-vs-C6 comparison.** See `analysis_c4g_vs_c6_v2.md`
  "F4 inclusion" for the re-derived 612-vs-612-row table; every metric is materially
  unchanged (same direction/magnitude) with F4 removed.
- **F4 rerun status (H1): fix landed 2026-09-23, rerun COMPLETED 2026-09-23.**
  `faults.py`'s `_inject_f4` previously always called the real write function and then
  unconditionally fabricated a `ValidationErrorFault` regardless of what the real write
  did -- every live model that hit an F4 cell was TOLD its write failed validation when it
  had, in fact, already committed. This has been fixed (commit `8c5466504`, worktree
  `worktrees/safe-deopt-v2-integration`): `_inject_f4` now checks the store's own
  `commit_log` after dispatch and only reports a rejection when write B genuinely produced
  no new committed effect; when no `concurrent_mutation` is supplied it synthesizes a real
  competing write (not a fabricated error), so F4 keeps the ability to produce a genuine
  rejection. The regression test no longer carries `robustness_only` and passes
  deterministically.

  **The 180 affected cells were rerun against live models on 2026-09-23** using
  `benchmarks/safe-deopt/rerun_f4_cells.py` (calls `run_experiment.run_cell` directly, same
  logic as every other row in `runs.jsonl`): 150 cells at `MODEL=gemini-3.5-flash-lite`
  (seeds 42-51) and 30 cells at `MODEL=gpt-4o-mini` (seeds 42-43), across conditions
  C1/C4/C4+G/C5/C6 and workloads W1/W2/W2-nonidempotent. All 180 new rows have
  `tokens_are_real_accounting: true` (verified row-by-row; the rerun script hard-aborts on
  any row that comes back mocked). Total real API spend: **$0.0645** (well under the
  $0.15-0.20 estimate and the $3 hard-abort ceiling) -- $0.0616 gemini + $0.0029 gpt-4o-mini,
  logged per-row in `results/runs_f4_rerun.jsonl`. Old F4 rows are preserved at
  `results/runs.jsonl.pre-f4-fix.bak`; the 180 rows in `results/runs.jsonl` proper were
  replaced in place (same 3600-row count, only the F4 rows' contents changed) and
  `results/scored_v2/*` was regenerated from the corrected file.

  **What changed once F4 was honest:** previously ALL 72 F4 rows in the C4+G/C6 matched set
  showed `useful_completion=True` (36/36 each) because the old injector's fabricated
  rejection always triggered the SAME scripted-looking recovery path regardless of the real
  outcome. With the fix, 24/36 per condition are `useful_completion=True` and 12/36 are
  `False` for the `W2-nonidempotent` workload specifically (the fixed injector now honestly
  reports a rejection there with no compensating retry available, so those 12-per-condition
  cells make no model call at all -- zero tokens/cost, `tokens_are_real_accounting=True`,
  correctly quarantined by `canonical_scoring.py` under the SAME "zero tokens/cost, real
  accounting, no transcript" rule already applied to F0/F5's legitimate no-call rows, not a
  new bug). See `analysis_c4g_vs_c6_v2.md` "F4 rerun 2026-09-23" for the full recomputed
  matched-cell table. Per H1's own stated options ("fix `_inject_f4` and rerun" or "drop F4
  from all aggregates and disclose the rerun requirement is unmet"), this project has now
  done the former: **F4 is included in the matched C4+G-vs-C6 comparison** going forward,
  since it is no longer produced by a broken injector. The token/cost/latency reduction for
  C4+G vs C6 found earlier is materially unchanged with F4 correctly included.

## 1b. Classifier fix (2026-09-23): the 48 F4-rerun zero-token rows are `legitimate-no-model`, not `invalid`

An external review flagged that treating those 48 rows (item 1 above, "these 12-per-condition
cells make no model call at all") as quarantined `invalid` alongside the unrelated 288-row bad
population (item 2 below) conflated two different things: a genuine, evidence-backed
deterministic short-circuit vs. data with no supporting evidence at all. `canonical_scoring.py`'s
`classify_row` now checks `_is_legitimate_f4_short_circuit` (fault == "F4", workload ==
"W2-nonidempotent", `duplicate_write_occurred` and `task_completed` both true) before its
quarantine branch, so these 48 rows are now classified `legitimate-no-model`: excluded from
the API-call-cost table (`per_condition_family.csv`) but included in the new end-to-end task
view (`end_to_end_per_condition_family.csv`), per `ACCEPTANCE_PLAN_V2.md` Sec.4. The 288-row
population in item 2 is unaffected -- it has no fault-detected evidence and no defensible
reason for zero model calls, so it stays quarantined. Full reconciliation of the resulting
288 -> 336 -> 288+48 count history: `RECOVERY_RESULTS_RECONCILED.md` "Update 2026-09-23
(part 2)".

## 2. 288 quarantined zero-token rows

- Source: `analysis_percondition_costs_v2.md`, `RECOVERY_RESULTS_RECONCILED.md` sec 1-2.
- All 288 rows share one shape (verbatim reason from
  `results/scored_v2/quarantined_rows.jsonl`): "llm-condition row with zero tokens/cost
  claiming real accounting; transcript_path is null."
- Breakdown by model: gpt-4o-mini = 48, gemini-3.5-flash-lite = 240 (traced: direct count
  over `results/scored_v2/quarantined_rows.jsonl`, matches doc exactly).
- These rows are never pooled with real API rows in any per-condition, per-family, or
  matched-cell table produced by `canonical_scoring.py`. Deterministic successes within
  this population may be retained per plan Sec.4 language, but are not labeled as API
  executions; malformed/unexplained rows are quarantined outright.
- Total dataset size: 3600 rows in `results/runs.jsonl`; 3312 classified `live-model`; 288
  classified `invalid` (quarantined); 0 `legitimate-no-model`; 0 `mock`
  (`RECOVERY_RESULTS_RECONCILED.md`, raw script summary).

## 3. C2 and C3: no real data

- Source: `analysis_percondition_costs_v2.md` bottom line, `RECOVERY_RESULTS_RECONCILED.md`
  sec 9.
- `results/runs.jsonl` (the 3600-row real dataset) contains only conditions C1, C4, C4+G,
  C5, C6 — 720 rows each. Zero C2 or C3 rows (traced: grep over the raw file for
  `"condition": "C2"` / `"C3"` returns 0 matches).
- C2 and C3 exist only in `results/runs.mock.jsonl` (60 mock rows each, part of a 420-row
  all-mock file) — never real model executions.
- T4's (`results/llm_recovery_integration_v2.jsonl`) and T6's
  (`results/procedure_vs_naive_runs.jsonl`) newer real-model result files use a different
  schema without the C1-C6 taxonomy and likewise contain no C2/C3-equivalent real runs.
- Consequence: H3 ("deterministic recovery alone, C3, suffices...") is untested by real
  data; no C2/C3 comparison is presented anywhere in the reconciled tables.

## 4. S2/F1/F3 scenario-mapping bug — localized, not a dataset-wide issue

- Source: `RECOVERY_RESULTS_RECONCILED.md` sec 7(b).
- The bug was local to `benchmarks/safe-deopt/llm_real_procedure_integration.py`'s own
  scenario-to-fault-id naming/dispatch table used only by T4's small 5-scenario integration
  harness. It never existed in `run_experiment.py`, the script that generated the 3600-row
  `runs.jsonl` (it calls `faults.py`'s fault-id functions directly, without that naming
  layer).
- No cell in `runs.jsonl` required a rerun because of this bug. It was corrected within
  T4's own separate, much smaller result files
  (`results/llm_recovery_integration.jsonl` — 8 rows, v1 — and
  `results/llm_recovery_integration_v2.jsonl` — 10 rows, v2, corrected).

## 5. Pre-existing test flake (environment issue, not caused by T4's changes)

- Source: `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` "Pytest status" section.
- `TestServerIdempotency::test_concurrent_reservation_blocks_the_losing_attempt_before_dispatch`
  failed when the full `benchmarks/safe-deopt/tests` directory was run together inside the
  full-Frappe bench environment (`frappe.cache()` returns None outside `bench run-tests`'s
  own fixture setup). Reproduced identically with T4's changes stashed out, and the same
  test file run alone passes 16/16. Not investigated further since it is unrelated to any
  file T4 modified.

## 6. Naive-arm failures in the Procedure-vs-naive dataset (T6) — reported, not excluded

These are not exclusions from the dataset (all 20 executions are retained and reported),
but are failures within the dataset, classified per `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 6:

| Instance | Family | Classification |
|---|---|---|
| CUST-0002 | gemini | Model-caused (final_text, no cap hit, incorrect final state) |
| CUST-0006 | gemini | Model-caused (same pattern) |
| CUST-0001 | openai | Model-caused / escalation (model chose to escalate; not harness/budget-caused) |
| CUST-0004 | openai | Model-caused / escalation |
| CUST-0006 | openai | Model-caused / escalation |
| CUST-0001+0004 | openai | Budget-caused (hit the 40/40 tool-call cap without converging) |

No harness-caused (silently-dropped-call) failures occurred. One harness defect (an OpenAI
`response_format` 400 error, `procedure_vs_naive.py` / `recovery_harness.py`) was found and
fixed **before** the paid dataset ran, and does not appear as a failure mode in the final
20-execution dataset (`REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 1, sec 6).

## 7. Lifecycle/break-even: intentionally left unmeasured

- Source: `LIFECYCLE_CLAIM_AUDIT.md` sec 2-3.
- `propose_procedure_from_run` (`huf/ai/procedure_proposal.py`) was never invoked against a
  live Frappe bench in this project — it imports `frappe` at module scope, unavailable in
  the sandbox that produced this dataset. `results/breakeven.json`'s `n_timing_seconds` and
  `procedure_proposal_timing_seconds` fields are `null` (never fabricated).
- Human review effort/cost of accepting a Procedure proposal is unmeasured anywhere in this
  project (confirmed by grep across the track and benchmark code for "human review" / "review
  effort" / "review cost" — no measured figure found).
- Per plan Sec.6, this is an explicit, disclosed omission, not a blocker for a paper
  reporting steady-state execution + recovery behavior.

## 8. Superseded prior reports (kept on disk, not deleted)

Per `ACCEPTANCE_PLAN_V2.md`'s own supersession table, these prior artifacts are superseded
and must not be cited as current: `analysis_c4g_vs_c6.md`, `analysis_openai_c5_duplicates.md`,
`analysis_percondition_costs.md`, `REPORT_LLM_RECOVERY_INTEGRATION.md`,
`REPORT_PROCEDURE_VS_NAIVE.md`, `FINAL_ADVERSARIAL_REVIEW.md` (reviewed the pre-v2 scope).
All remain on disk as historical record per the plan's explicit "kept, not deleted" rule.
