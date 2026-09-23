# Recovery Results Reconciled -- T5 (ACCEPTANCE_PLAN_V2.md Sec.4)

**Update 2026-09-23: F4 fixed and rerun.** `_inject_f4`'s commit-then-fabricate bug (see
EXCLUSIONS_AND_FAILURES.md ss1) was fixed in commit `8c5466504`, and the 180 affected rows
were regenerated against live models (real cost $0.0645) and merged into `results/runs.jsonl`
in place. `canonical_scoring.py` was rerun on the corrected file; the class_counts and
quarantine numbers below are now stale by this delta: `invalid` rose from 288 to **336**
(+48, all newly and legitimately quarantined `W2-nonidempotent` F4 rows that are honestly
zero-cost/no-model-call now, where the old buggy injector had fabricated tokens/cost that
made them look like ordinary live rows) and `live-model` fell from 3312 to **3264**. Every
other number in this document (token reconciliation, per-condition-family tables not
involving F4, OpenAI duplicate findings) is unaffected -- only F4's own numbers moved. See
`analysis_c4g_vs_c6_v2.md` "F4 rerun 2026-09-23" for the corrected matched-cell comparison.
The rest of this document is left as originally written (pre-rerun) for the audit trail.

**Update 2026-09-23 (part 2): classifier fixed to distinguish the two zero-token
populations; 288 -> 336 -> 288+48, and the OpenAI C5 duplicate count 14 -> 12
reconciled explicitly.** An external review of this project found that lumping ALL
zero-token LLM-condition rows into `invalid` was over-broad: the 48 new F4-rerun rows
above are honestly zero-cost for a *good* reason (a genuine, fault-detected competing
write short-circuits the attempt before any model dispatch is needed -- real
persisted-state evidence, `duplicate_write_occurred: true`, `task_completed: true`),
which is not the same shape as the ORIGINAL 288 rows (fault F0/F5 -- i.e. no fault fired
at all, so nothing legitimately explains a no-fault LLM-condition cell needing zero model
calls). `canonical_scoring.py`'s `classify_row` now checks for this exact signature
(`_is_legitimate_f4_short_circuit`: `fault == "F4"`, `workload == "W2-nonidempotent"`,
`duplicate_write_occurred` and `task_completed` both true) BEFORE falling through to the
quarantine branch, so:

- The **288 original zero-token rows stay `invalid`/quarantined** -- unchanged, still
  excluded from every aggregate. This fix does not un-quarantine anything that was
  genuinely bad data.
- The **48 F4-rerun zero-token rows move from `invalid` to a new `legitimate-no-model`
  bucket** (they were incorrectly folded into the 288->336 quarantine bump described
  above; that bump is now understood to have been two different things counted as one).
- **288 -> 336 -> reconciled as 288 + 48, not a single population:** the 336 figure
  quoted right above this section was the *pre-classifier-fix* total (`invalid` count
  after the F4 rerun, before this fix's `legitimate-no-model` split existed). Post-fix,
  `results/scored_v2/summary.json`'s `class_counts` read
  `{"invalid": 288, "legitimate-no-model": 48, "live-model": 3264}` -- i.e. 336 was
  always "288 genuinely-bad rows + 48 legitimately-zero-cost F4 rows" merged into one
  number by the classifier's prior inability to tell them apart, not 336 newly-bad rows.
  `live-model` is unchanged at 3264 (3312 - 48, matching the pre-fix count exactly, since
  none of the reclassified 48 were ever `live-model`).
- Per `ACCEPTANCE_PLAN_V2.md` Sec.4, the 48 legitimate-no-model rows are excluded from
  the API-call-cost table (`per_condition_family.csv` -- they made zero API calls, so
  pooling them there would understate per-attempt cost) but INCLUDED in the new
  end-to-end task view (`end_to_end_per_condition_family.csv`, from the new
  `aggregate_end_to_end_per_condition_family`), since the task itself did genuinely
  reach a deterministic (if unsuccessful) end state.
- **OpenAI C5 duplicate-committed-effect count, 14 -> 12, reconciled:** the 14-row
  finding in `analysis_openai_c5_duplicates_v2.md` includes lines 3461/3462 (fault F4,
  seeds 42/43, `condition=C5`, `model_id=gpt-4o-mini`) -- exactly 2 of the 48
  legitimately-zero-cost F4 rows above. Before this fix, those 2 rows were classified
  `invalid`, so a query that filters `duplicate_committed_effects > 0` over
  `scored_rows.jsonl` WITHOUT also filtering on `row_class` still returned all 14
  (`row_class` and the duplicate-effect flag are independent columns). The "12" figure
  a later read of the same data reported came from also requiring `row_class ==
  "live-model"` (the natural filter for "duplicates among real API executions"), which
  excludes those same 2 F4 rows -- 12, not a different or shrinking dataset. Post-fix,
  those 2 rows are `legitimate-no-model` rather than `invalid`, but a `row_class ==
  "live-model"` filter still excludes them (correctly -- they made no API call), so the
  12-row count is unchanged by this fix. The 14-row total (all duplicate-committed-effect
  rows regardless of class) is also unchanged. See `analysis_openai_c5_duplicates_v2.md`
  for the same reconciliation written into that document directly.

Regenerates and reconciles the three superseded per-topic analyses using
benchmarks/safe-deopt/canonical_scoring.py's real output over the original ~3600-row
dataset (worktree: /Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf,
branch research/safe-deopt-v2-integration, verified via git status/branch before running
and before committing). Companion docs: analysis_c4g_vs_c6_v2.md,
analysis_openai_c5_duplicates_v2.md, analysis_percondition_costs_v2.md.

## Command

```
cd benchmarks/safe-deopt
python3 canonical_scoring.py --input results/runs.jsonl --output results/scored_v2
```

canonical_scoring.py's real CLI is `--input INPUT --output OUTPUT` (repeatable --input),
not any of the flag names speculated in the task brief (reconciliation_errors,
matched_cases_c4g_vs_c6 etc. are real output *fields*, not CLI flags -- confirmed by
reading canonical_scoring.py directly and by --help).

**SUPERSEDED by the update above.** The raw summary and table immediately below reflect the
pre-F4-fix, pre-classifier-fix state of the pipeline and are kept only as the original audit
trail. Current, authoritative counts are `{"invalid": 288, "legitimate-no-model": 48,
"live-model": 3264}` per the update block at the top of this document.

Raw summary the script printed (SUPERSEDED, pre-fix):
```
class_counts: {"invalid": 288, "live-model": 3312}
quarantined_count: 288
reconciliation_failures_count: 0
total_rows: 3600
```

## 1. Row classification breakdown

**SUPERSEDED by the update above -- see current counts (3264 live-model / 48
legitimate-no-model / 288 invalid) at the top of this document.**

| class | count |
|---|---|
| live-model | 3312 |
| legitimate-no-model | 0 |
| mock | 0 |
| invalid (quarantined) | 288 |
| **total** | **3600** |

No legitimate-no-model rows exist in runs.jsonl because C2/C3 (the only conditions the
script treats as zero-LLM-by-design) never appear in this file -- see item 9. (This
paragraph too predates the F4 rerun and classifier fix that introduced the 48
legitimate-no-model rows; see the update block at the top.)

## 2. Zero-token row handling

All 288 quarantined rows share one reason (verbatim from
results/scored_v2/quarantined_rows.jsonl): "llm-condition row with zero tokens/cost
claiming real accounting; transcript_path is null". Model breakdown: gpt-4o-mini = 48,
gemini-3.5-flash-lite = 240. This confirms T3's finding exactly: it is not just the 48
OpenAI rows, a further 240 Gemini rows share the identical shape and are quarantined
identically -- none are pooled with real API rows in any of the tables below or in the
companion docs.

## 3. Token reconciliation

reconciliation_failures = [] (count 0) across all 3600 rows: cached_tokens <= input_tokens
holds on every row. reasoning_tokens is a distinct column in the schema and is 0 on every
row in this dataset (no reasoning-token-billing model was used); it is never folded into
input/output tokens.

## 4. Distinct attempt/effect columns (per_condition_family.csv, live-model rows only)

**SUPERSEDED by the update above for the live-model row-count context** (this table's
`live-model`-only framing predates the 3312 -> 3264 correction); the per-cell
attempt/effect figures themselves (e.g. C5/gpt-4o-mini duplicate_committed_effects_total
= 14, unfiltered by the F4 legitimate-no-model split) are unaffected by that correction --
see `CLAIM_TO_EVIDENCE_TABLE.md` sec 4 for the "14 vs 12" reconciliation of this same
figure.

| condition | model | unsafe_attempts_total | blocked_attempts_total | dispatched_unsafe_retries_total | duplicate_committed_effects_total |
|---|---|---|---|---|---|
| C1 | gemini | 13 | 0 | 13 | 0 |
| C1 | gpt-4o-mini | 0 | 0 | 0 | 0 |
| C4 | gemini | 163 | 0 | 163 | 0 |
| C4 | gpt-4o-mini | 8 | 0 | 8 | 0 |
| C4+G | gemini | 0 | 196 | 0 | 0 |
| C4+G | gpt-4o-mini | 0 | 19 | 0 | 0 |
| C5 | gemini | 78 | 0 | 78 | 1 |
| C5 | gpt-4o-mini | 59 | 0 | 59 | 14 |
| C6 | gemini | 0 | 164 | 0 | 0 |
| C6 | gpt-4o-mini | 0 | 60 | 0 | 0 |

Both guarded conditions (C4+G, C6) show duplicate_committed_effects_total = 0 and route
unsafe attempts to blocked_attempts instead of dispatched_unsafe_retries -- the guard
mechanism working as designed. The unguarded conditions (C4, C5) show the opposite
pattern.

## 5. useful_completion vs escalation

Both are distinct columns in scored_rows.jsonl (useful_completion, escalated) plus a
useful_and_escalated flag. The script's own note on the overlap (verbatim):
"useful_and_escalated=True means the run reached a useful/correct end state ... AND ALSO
escalated to a human in the same run ... This is a GOOD outcome, not a contradiction."
per_condition_family.csv's useful_and_escalated_total column ranges from 17 (C1
gpt-4o-mini) to 211 (C4 gemini), confirming this is a common, legitimate combination in
the dataset, not scored as either a pure completion or a pure escalation.

## 6. OpenAI C5 duplicate reassessment (full detail in analysis_openai_c5_duplicates_v2.md)

**Note on "14" below:** this section's headline "14 duplicate-committed-effect rows" is the
unfiltered count and remains correct and current (see `CLAIM_TO_EVIDENCE_TABLE.md` sec 4);
it is **not** superseded. What is superseded is only the row-classification framing in
sec 0/1 above (3312/0 vs. the current 3264/48) -- 2 of these same 14 rows are exactly the
F4 rows that moved from `invalid` to `legitimate-no-model`, which is why a `row_class ==
"live-model"` filter over this same population reads 12, not 14 (see "OpenAI C5
duplicate-committed-effect count, 14 -> 12, reconciled" in the update block at the top).

**Corrected 2026-09-23 per FINAL_ADVERSARIAL_REVIEW_V2.md C2: the prior "0 of 14 survive"
verdict below this line was wrong for 4 rows and is withdrawn.**

14 duplicate-committed-effect rows found (C5, gpt-4o-mini). Of these:
- 2 (fault F4, seeds 42/43) fall under T2's confirmed F4 robustness_only exclusion
  (commit-then-fabricate gap in faults.py's synthesized-fallback path) and must be
  excluded from valid-guarantee conclusions per ACCEPTANCE_PLAN_V2.md Sec.2.
- 8 (status_resolvable x4, none x4, across F2/F6) do not fall under that exclusion, and
  reassessed against C5's design (the no-replay-guard condition, per README.md's H2) they
  ARE the expected outcome of running without a guard against a guarantee that promises
  nothing about idempotent retries -- not a violation.
- **4 (tool_guarantee=server_idempotent, F2 seeds 42/43 and F6 seeds 42/43) ARE genuine,
  unresolved guarantee-contract violations.** T2 contract #1 proved F2 commits exactly
  once; these 4 rows show `submit_allocation_unsafe` -- a tool declaring
  `server_idempotent` -- committing a real second `Allocation` on a model retry
  (verified directly against the transcript for seed 42,
  `results/transcripts/real_openai/C5/W2-nonidempotent/F2/server_idempotent/42.json`).
  `unsafe_attempts`/`dispatched_unsafe_retries` read 0 for these 4 rows, which is a
  documented scorer limitation (see canonical_scoring.py's `safety_columns` docstring and
  analysis_openai_c5_duplicates_v2.md), not evidence the retry was safe --
  `duplicate_committed_effects=1` correctly flags all 4.
- **Verdict: at most 8 of 14 explained as expected no-guard behavior; 4 of 14 are
  unexplained, genuine declared-guarantee violations; 2 of 14 are F4-confounded.**

## 7. Which cells are affected by (a) F4 exclusion and (b) the S2/F1/F3 mapping bug

**(a) F4 exclusion in the main 3600-row dataset.** faults.py defines FAULT_IDS =
("F0".."F7") and run_experiment.py imports fault injection directly from faults.py's own
_inject_f1/_inject_f2/... functions -- the same functions T2's contract tests exercised.
Any row in runs.jsonl with fault == "F4" is subject to the confirmed commit-then-fabricate
gap. Count: rows with fault=="F4" across the whole dataset (all conditions, both models) = 180
(30 per condition x 5 conditions for gemini-3.5-flash-lite = 150, plus 6 per condition x 5
conditions for gpt-4o-mini-2024-07-18 = 30). All 180 F4 rows, across every condition, are
excluded from valid-guarantee conclusions per Sec.2 -- not from correctness/cost
aggregates generally, only from claims about whether a guarantee mechanism holds, since
F4's gap is specific to the fault injector's own fabrication logic and not to any
guarantee condition's behavior.

**(b) S2/F1/F3 mapping bug.** This bug was local to
benchmarks/safe-deopt/llm_real_procedure_integration.py's own scenario-to-fault-id
comment/dispatch table used by T4's small 5-scenario integration harness (its own
docstring records the self-correction: "S2 did-not-commit/ambiguous-timeout -> F3, not F1
as the prior round's '2_non_commit_F1' scenario used"). run_experiment.py -- the script
that generated the 3600-row runs.jsonl -- does not use that scenario-naming layer at all;
it calls faults.py's fault-id functions directly. **This mapping bug never existed in the
main dataset's fault-injection code.** No cell in runs.jsonl needs a rerun on account of
it; the confusion was confined to T4's separate, much smaller
results/llm_recovery_integration*.jsonl files (8 and 10 rows respectively), which were
already corrected and re-run as REPORT_LLM_RECOVERY_INTEGRATION_V2.md documents.

**Cells needing rerun:** none identified beyond what the F4 exclusion already flags as
out-of-scope for guarantee conclusions (not requiring a rerun -- excluding is the
correct treatment per Sec.2, since F4's gap is in the fault injector's synthesized
fallback path, not something a different LLM run would resolve). No paid LLM reruns were
performed or are required for this reconciliation task.

## 8. C4+G vs C6 matched-case verdict (full detail in analysis_c4g_vs_c6_v2.md)

**Corrected 2026-09-23 per FINAL_ADVERSARIAL_REVIEW_V2.md C3/H1: the useful_completion
"tied at 0.5 vs 0.5" claim below is withdrawn as a correctness-equivalence finding.**

The 648-cell matched set includes 72 F4 rows; F4 is now excluded from this comparison (see
analysis_c4g_vs_c6_v2.md "F4 inclusion") -- the F4-excluded set is 1224 rows/1224 matched
cells worth of live-model rows (612 per condition). Re-derived broken down by fault type,
useful_completion is a **pure function of fault** (F2/F4/F6 = 100%, F1/F3/F7 = 0%) in BOTH
conditions, identically, for every fault -- including F2 and F3, which T2 proved are
caller-indistinguishable at retry time yet split 100%/0%. The "0.5 vs 0.5" match is fault-
mix bookkeeping (both conditions ran the same fault mix), not a measurement of C4+G's or
C6's recovery correctness, and carries no signal to support or refute H1
("structured handoff achieves correctness within 5-10% of C6"): **useful_completion is
Unsupported as evidence for H1, in either direction.**

What the matched-cell data DOES support, unchanged with or without F4: token/cost/time all
show a real (CI excludes zero) reduction for C4+G (F4-excluded: -887.3 tokens/attempt,
-$0.00025/attempt, -0.80s/attempt -- all within noise of the F4-included figures of -878.5
tokens, -$0.000248, -0.80s). escalated differs by roughly +1pp either way but its CI crosses
zero (not distinguishable from noise). C4+G is measurably cheaper and faster than C6 on
this dataset; whether it matches C6 on correctness is untested by useful_completion and
remains an open question.

## 9. C2/C3 data availability

Confirmed: **0 real rows for C2 or C3 anywhere in runs.jsonl** (3600 rows are C1/C4/C4+G/
C5/C6 only, 720 each). C2 and C3 exist only in results/runs.mock.jsonl (60 rows each of a
420-row all-mock file). T4's and T6's newer real-model result files
(llm_recovery_integration_v2.jsonl, procedure_vs_naive_runs.jsonl) use a different schema
without the C1-C6 condition taxonomy and likewise contain no C2/C3-equivalent real runs.
**No C3 (or C2) comparison is possible with current data; none is presented here or in the
companion docs.**

## Files produced

- analysis_c4g_vs_c6_v2.md
- analysis_openai_c5_duplicates_v2.md
- analysis_percondition_costs_v2.md
- RECOVERY_RESULTS_RECONCILED.md (this file)
- Scored data (committed in the worktree, not this git-ignored track dir):
  benchmarks/safe-deopt/results/scored_v2/{scored_rows.jsonl, quarantined_rows.jsonl,
  per_condition_family.csv, matched_c4g_vs_c6.json}
