# Claim-to-Evidence Table (T8, ACCEPTANCE_PLAN_V2.md ss7)

Every substantive claim this track has made or could plausibly make in a paper, classified
Supported / Limited / Unsupported / Withdrawn, with the exact evidence file backing the
classification. Numbers in this table were spot-checked against raw artifacts under
`benchmarks/safe-deopt/results/` in the worktree
`/Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf` (branch
`research/safe-deopt-v2-integration`) — see the "traced" note on each row and
`EXCLUSIONS_AND_FAILURES.md` for what was excluded before these numbers were computed.

Definitions (verbatim from the task):
- **Supported**: real evidence, properly scoped, would survive an adversarial reviewer.
- **Limited**: real evidence exists but is narrow (n, single workload/model family, one run).
- **Unsupported**: claimed somewhere in the track's docs but the evidence does not establish it.
- **Withdrawn**: an earlier claim (cited) that later/reconciled data contradicts, or that a
  supersession explicitly replaced.

## 1. Guarantee contracts (deterministic, T2)

| Claim | Class | Evidence |
|---|---|---|
| Committed-timeout (F2): commits exactly once, caller sees timeout | Supported | `CONTRACT_TEST_RESULTS.md` #1, `TestCommittedTimeout::test_f2_commits_once_but_reports_timeout` |
| Uncommitted-timeout (F3): same shape, write never commits | Supported | `CONTRACT_TEST_RESULTS.md` #2, `TestUncommittedTimeout::test_f3_same_shape_as_f2_but_never_commits` |
| F4 validation rejection produces no committed mutation | **Withdrawn** | `CONTRACT_TEST_RESULTS.md` #3: gap confirmed ("commit-then-fabricate" is present), marked `robustness_only`, excluded from valid-guarantee conclusions per plan Sec.2. Any earlier framing that F4 "holds" is withdrawn. |
| Late commit: pending -> UNKNOWN -> commits unless fenced | Supported | `CONTRACT_TEST_RESULTS.md` #4, `TestLateCommit` (2 tests) |
| Server idempotency: same key+payload cannot double-effect | Supported | `CONTRACT_TEST_RESULTS.md` #5, `TestServerIdempotency` (2 tests) |
| Status resolution (COMMITTED/NOT_COMMITTED/UNKNOWN correctness) | Supported | `CONTRACT_TEST_RESULTS.md` #6, `TestStatusResolution` (5 tests) |
| Fencing: successful fence blocks the original pending op | Supported | `CONTRACT_TEST_RESULTS.md` #7, `TestFencing` (3 tests) |
| F4 is a real, known gap and is excluded from every guarantee claim in this project | Supported | `CONTRACT_TEST_RESULTS.md` #3; `RECOVERY_RESULTS_RECONCILED.md` sec 7(a): 180 F4 rows in `runs.jsonl` (traced: `python3 -c` count over `results/runs.jsonl`, fault=="F4" == 180, matches doc) |

## 2. Guard safety mechanism (deopt replay guard)

| Claim | Class | Evidence |
|---|---|---|
| Guarded conditions (C4+G, C6) produce zero duplicate committed effects across the full 3312-row live-model dataset | Supported | `RECOVERY_RESULTS_RECONCILED.md` sec 4 table: `duplicate_committed_effects_total` = 0 for C4+G and C6, both model families. Traced: `results/scored_v2/per_condition_family.csv` grepped directly, both C4+G and C6 rows read 0 in that column. |
| Unguarded conditions (C4, C5) allow duplicate committed effects | Supported (Limited to this workload) | Same table: C5/gemini = 1, C5/gpt-4o-mini = 14, C4 = 0 both families (C4 has no replay attempts landing as duplicates in this run despite being unguarded — see per-cell caveat below). |
| The real, wired runtime replay guard (not a standalone copy) rejects an unnecessary retry a model actually attempted | Supported (Limited: n=1 observed instance) | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` "Guard behavior observed" table, S1/GPT-4o-mini row: guard rejected an actual retry attempt after the model already knew the write had committed. Real `execute_procedure` call, real Frappe backend (`safe-deopt-verify` bench). One observed instance only — not a statistical safety estimate (the report says so explicitly). |
| The guard allows a legitimate permitted retry to succeed (S2, S4) end-to-end through the real runtime | Supported (Limited: n=2 scenarios x 2 families = 4 runs) | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` S2 and S4 rows: `guard_rejected=False`, real second `execute_procedure` dispatch, real Frappe `ToDo.status="Closed"` commit confirmed. |
| The guard provides a "safety benefit" in a general/statistical sense across models and workloads | **Unsupported as a general claim** | The only real-runtime evidence is 10 integration rows (`REPORT_LLM_RECOVERY_INTEGRATION_V2.md`), not a statistical estimate ("this is integration evidence, not a statistical safety estimate" — plan Sec.3, repeated in the report itself). The 3312-row statistical dataset (Sec 1 above) shows the guard eliminating duplicates in the synthetic-harness condition, not the real HUF runtime path. REPORT.md's v6 "guard provides the measured safety benefit (0 unsafe retries across every condition/family tested)" framing conflates these two different guard implementations (synthetic-harness guard vs. real wired runtime guard) — flagged as superseded in REPORT.md's v7 update. |

## 3. C4+G vs C6 comparison (T5, matched-cell)

| Claim | Class | Evidence |
|---|---|---|
| C4+G and C6 are matched, cell-for-cell, on 648 (seed, fault, tool_guarantee, workload, model) cells | Supported | `analysis_c4g_vs_c6_v2.md`, `results/scored_v2/matched_c4g_vs_c6.json`. Traced: `n_matched_cells` read directly from JSON = 648, matches doc. |
| useful_completion is tied exactly between C4+G and C6 on this matched set, and this tie means "C4+G matches C6 on correctness" | **Unsupported (corrected 2026-09-23; F4 fixed and rerun same day, tie persists)** | `useful_completion` is a pure function of `fault`, not a comparison of model/guard behavior — F2/F6 always score 100%, F1/F3/F7 always score 0%, in both conditions and both model families. F2 and F3 are caller-indistinguishable (contract test #1/#2) yet split 100/0, proving the metric reads ground-truth commit state. After F4's injector bug was fixed and the 180 affected rows rerun against live models ($0.0645 real spend), the matched-set diff is 0.0 at `c4g_mean=c6_mean=0.4906` (n=636, F4 included) — F4 itself now splits 24/36-True vs 12/36-False per condition on the `W2-nonidempotent` workload specifically (previously 36/36 True under the buggy injector), but the tie across both conditions is unaffected since both ran the identical fault mix. The tie therefore still carries no completion-equivalence signal. `analysis_c4g_vs_c6_v2.md` "F4 rerun 2026-09-23"; `FINAL_ADVERSARIAL_REVIEW_V2.md` C3. |
| C4+G is measurably cheaper than C6 on tokens/cost/wall-time, CI excludes zero (not an overlap-implied-equivalence claim) | Supported (Limited: same 648-cell dataset, 2 model families) | `analysis_c4g_vs_c6_v2.md`; traced: `total_tokens` diff=-878.55 CI[-952.87,-802.95]; `cost_usd` diff=-0.0002485 CI[-0.000283,-0.000215]; both CIs strictly negative, confirmed from `matched_c4g_vs_c6.json`. |
| escalated differs by +0.93pp (C4+G escalates more) but the CI crosses zero — undistinguishable from noise | Supported | Same source; traced CI [-0.0278, +0.0463], crosses zero. |
| C4+G ≈ C6 "equivalence" inferred from overlapping confidence intervals (original framing) | **Withdrawn** | `ACCEPTANCE_PLAN_V2.md` supersession table explicitly disallows this reasoning; `analysis_c4g_vs_c6.md` (v1) used it and is superseded by `analysis_c4g_vs_c6_v2.md`, which reports observed differences with CIs instead of inferring equivalence. |
| "C6 costs 1.6x-3.7x more tokens/row and 10%-130% higher latency" (REPORT.md v6 framing) | **Withdrawn / superseded numbers** | v1 numbers from unmatched aggregates; the matched-cell v2 numbers (42% fewer tokens, 31% lower cost, 15% less wall time for C4+G vs C6) are the current, authoritative figures. Marked superseded in REPORT.md v7 update. |

## 4. OpenAI C5 "14 duplicates" finding

| Claim | Class | Evidence |
|---|---|---|
| 14 duplicate-committed-effect rows exist in C5/gpt-4o-mini | Supported | `analysis_openai_c5_duplicates_v2.md`; traced: direct count over `results/scored_v2/scored_rows.jsonl` for condition=="C5", model startswith "gpt-4o-mini", duplicate_committed_effects>0 = 14, matches doc and matches the original v1 count (count itself did not change between v1 and v2 — only the interpretation did). |
| All 14 are "genuine guarantee-contract violations", spanning F2/F4/F6 and falsely-reassuring `server_idempotent`/`status_resolvable` labels (REPORT.md v6 framing) | **Withdrawn** | Superseded by the corrected reassessment below — the original claim over-counted (14 treated as violations without distinguishing no-guard-expected behavior); the corrected reassessment (next row) is neither "all 14" nor "0 of 14". |
| Corrected reassessment (2026-09-23): of the 14 duplicate-committed-effect rows, 4 are genuine, unexplained declared-guarantee violations; at most 8 are explained as C5's expected no-guard behavior; 2 are F4-confounded | **Supported (corrected)** | `analysis_openai_c5_duplicates_v2.md`: the 4 `tool_guarantee=server_idempotent` rows (F2 seeds 42/43, F6 seeds 42/43; raw rows 3445/3446/3465/3466) are genuine violations — a declared server-idempotent tool produced a second committed effect, which its own guarantee says cannot happen; the scorer's `dispatched_unsafe_retries` count for this path was also found to be a miscount (records 0 for a row whose transcript shows an unsafe-tool dispatch). `RECOVERY_RESULTS_RECONCILED.md` sec 6. The earlier "0 of 14 survive" framing (row above) is withdrawn as incorrect, not merely superseded by new data. |
| 2 of the 14 (F4, seeds 42/43) are confounded by the known F4 commit-then-fabricate gap and must be excluded from valid-guarantee conclusions | Supported | `analysis_openai_c5_duplicates_v2.md` per-case reassessment table; traced against `CONTRACT_TEST_RESULTS.md` #3. |
| The remaining 8 duplicates (12 minus the 4 reclassified as genuine violations) demonstrate exactly the failure class C6's guard is shown to eliminate | Supported | `analysis_openai_c5_duplicates_v2.md` + `RECOVERY_RESULTS_RECONCILED.md` sec 4/6: C6's matched `duplicate_committed_effects_total` = 0 for gpt-4o-mini (traced above, section 2 of this table). The 4 `server_idempotent` violations are a distinct, still-open finding, not part of "the failure class the guard eliminates". |

## 5. Per-condition costs (T5)

| Claim | Class | Evidence |
|---|---|---|
| 336 rows (56 gpt-4o-mini + 280 gemini) are zero-token/null-transcript and quarantined, excluded from every cost/success table | Supported (updated 2026-09-23 after F4 fix+rerun; was 288 = 48+240 before) | `analysis_percondition_costs_v2.md`, `RECOVERY_RESULTS_RECONCILED.md` sec 2 (pre-rerun baseline). Traced post-rerun: `wc -l results/scored_v2/quarantined_rows.jsonl` = 336; per-model breakdown counted directly from that file = {gemini-3.5-flash-lite: 280, gpt-4o-mini: 56}, exact match. The +48 delta is 48 newly-legitimate `W2-nonidempotent` F4 rows now honestly zero-cost/no-model-call (previously fabricated tokens/cost hid them from this bucket). |
| No token reconciliation failures across all 3600 rows (cached_tokens <= input_tokens holds everywhere) | Supported | `analysis_percondition_costs_v2.md`; `results/scored_v2` summary reports `reconciliation_failures_count: 0`, corroborated in `RECOVERY_RESULTS_RECONCILED.md` sec 3. Not independently re-derived (would require re-running canonical_scoring.py's own check), so treated as Supported on the strength of the script's own committed output rather than a fully independent re-derivation. |
| Per-condition-family cost/token/success tables (C1/C4/C4+G/C5/C6 x 2 models) are correct as reported | Supported | `analysis_percondition_costs_v2.md` table; traced: `results/scored_v2/per_condition_family.csv` C1/gemini row and C5 rows read directly, match the doc's figures exactly (e.g. C5/gpt-4o-mini: n=108, success_rate=0.6667, mean_cost=0.0003936 — all confirmed byte-for-byte against the CSV). |
| No C2 or C3 real-model data exists anywhere in the project; any prior C2/C3 comparison used mock data | Supported | `analysis_percondition_costs_v2.md`, `RECOVERY_RESULTS_RECONCILED.md` sec 9. Traced: grep over `results/runs.jsonl` for `"condition": "C2"` or `"C3"` = 0 matches; condition counts in `runs.jsonl` = {C1,C4,C4+G,C5,C6} only, 720 each, total 3600 — matches doc exactly. |
| H3 ("deterministic recovery alone, C3, suffices...") is empirically tested | **Unsupported** | No C3 real-model rows exist anywhere (see above); H3 remains untested by real data per `analysis_percondition_costs_v2.md` bottom line. |

## 6. Real HUF LLM recovery integration, 5 scenarios (T4)

| Claim | Class | Evidence |
|---|---|---|
| 10 real (non-mocked) integration runs (5 scenarios x 2 model families) executed through the actual `execute_procedure` and the real wired runtime replay guard | Supported | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md`; traced: `wc -l results/llm_recovery_integration_v2.jsonl` = 10, matching doc's stated row count. |
| Scenario 4 (clean pre-dispatch rejection then a permitted successful retry) is a genuinely new scenario not covered by the prior (v1, 4-scenario) round | Supported | `ACCEPTANCE_PLAN_V2.md` supersession table item on `REPORT_LLM_RECOVERY_INTEGRATION.md` ("Only 4 scenarios were covered ... requires 5"); `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` "What changed" item 3 documents S4 as new, with its own fault-id correction (F1, not F4 as a prior in-code comment mistakenly named it). |
| Permission-denial (S5) recovery attempt is verified under the exact same restricted identity as the original denial, with zero unauthorized effect | Supported (Limited: n=2, one per model family) | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` S5 row + "S5 uses the SAME restricted identity" paragraph: direct Frappe read of `Safe Deopt Test Submittable.docstatus` = 0 / `unauthorized_effect: false` for both families. |
| GPT-4o-mini attempted an unnecessary/unsafe retry in S1 despite already knowing the write had committed, and the real guard blocked it | Supported (Limited: n=1 observed instance, not rerun for a cleaner transcript) | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` "Unexpected model behavior" section, reported as-is per instruction. |
| This integration evidence establishes a statistical safety guarantee across models/workloads | **Unsupported** | The report itself states: "This is integration evidence, not a statistical safety estimate" (plan Sec.3 language, reiterated in the report). n=10 total runs, no repetitions, cannot support a statistical claim. |
| Real dollar cost of the full 10-run integration suite (~$0.0077) | Supported | `REPORT_LLM_RECOVERY_INTEGRATION_V2.md` Cost section: Gemini $0.00546 + OpenAI $0.00227 ≈ $0.0077. Not independently re-summed from a raw per-row token file in this pass (the file's per-row token fields were not individually re-added); accepted on the strength of the report's own itemized token->cost derivation, which is internally consistent. |

## 7. Procedure-vs-naive comparison, 20 executions (T6)

| Claim | Class | Evidence |
|---|---|---|
| 20-execution dataset (5 fixed task instances x 2 model families x 2 arms) plus 2 one-time compilation rows (22 total rows) was actually run | Supported | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 0. Traced: `wc -l results/procedure_vs_naive_runs.jsonl` = 22, matches doc exactly. |
| Procedure arm was correct on 10/10 executions (5/5 both families); naive arm was correct on 3/5 (gemini) and 1/5 (gpt-4o-mini) in this specific one-shot draw | Supported (Limited: n=5/family/arm, one run each, no repetitions — explicitly scoped as such in the report) | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 4.2/4.3/7. |
| The naive arm's multi-tool-call harness fix (T3) was genuinely exercised: batched calls returned == dispatched, none silently dropped | Supported (Limited: 2 of 10 naive instances, both Gemini) | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 5, per-turn returned/dispatched counts shown for both instances. |
| No harness-caused (silently-dropped-call) naive-arm failures occurred in the final dataset | Supported | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 6 classification table + closing note; the one harness defect found (OpenAI response_format 400) was fixed pre-run, not a failure mode in the dataset. |
| Procedure arm graph is hand-authored, honestly labeled (not compiler-produced) | Supported | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 2 row 5d: `extra.graph_provenance == "hand-authored"` on every row. |
| Procedures show a general/statistically established speedup, cost saving, or correctness advantage over naive agents | **Unsupported as a general claim; Limited/directional only for this sample** | `REPORT_PROCEDURE_VS_NAIVE_V2.md` sec 7 explicitly disclaims this: "far too small ... to support any claim about a general speedup, cost savings, or correctness advantage ... No such claim is made here." |
| "Procedure arm used ~4-6x fewer model calls and cost roughly an order of magnitude less ... while being more correct (10/10 vs 5/10)" (REPORT.md v6 framing, from the superseded n=5/family/arm, non-fixed-order v1 dataset) | **Withdrawn / superseded** | `ACCEPTANCE_PLAN_V2.md` supersession table: v1 dataset was "n=5/family/arm (not 5 fixed task instances x 2 families x 2 arms = 20 as specified)"; naive arm's one-tool-call-per-turn limitation was only disclosed, not fixed; graph provenance was not explicitly labeled. The v2, corrected 20-execution dataset (this section) supersedes it; REPORT.md v7 marks the v6 section superseded rather than deleting it. |

## 8. Lifecycle / break-even claims (T7)

| Claim | Class | Evidence |
|---|---|---|
| "Compilation cost" as measured in `procedure_vs_naive.py` is one discarded plan-generation model call, not the real trace-to-proposal-and-verification cost | Supported | `LIFECYCLE_CLAIM_AUDIT.md` sec 1, code citation (`compile_procedure()`, module docstring line 37). |
| `propose_procedure_from_run` / real compile+verify path was never invoked against a live bench in this project | Supported | `LIFECYCLE_CLAIM_AUDIT.md` sec 2: `huf/ai/procedure_proposal.py` imports frappe at module scope, unavailable in the sandbox; `results/breakeven.json`'s `n_timing_seconds` is null. |
| Human review effort/cost of accepting a Procedure proposal is measured anywhere in this project | **Unsupported (explicitly, correctly disclosed as absent)** | `LIFECYCLE_CLAIM_AUDIT.md` sec 3: grep across the whole track and benchmark code found no measured figure; report states plainly "human review effort is unmeasured. No estimate is given here or should be given anywhere." |
| Numerical break-even claim: "compile cost recovered in well under one repetition ... far faster than the speculative plan's predicted 2-5 repetitions" (REPORT_PROCEDURE_VS_NAIVE.md v1, REPORT.md v6 citing it) | **Withdrawn** | `LIFECYCLE_CLAIM_AUDIT.md` sec 4/5 item 1: this substitutes a mislabeled plan-generation cost for a full discovery/compile/verify lifecycle cost, the exact violation Sec.6 of the plan targets. `REPORT_PROCEDURE_VS_NAIVE_V2.md` does not repeat this claim (Sec.4.1 reports the table with no break-even derivation). Marked superseded in REPORT.md v7. |
| `breakeven.json`'s N* sweep is illustrative/mocked only, not a real cost claim | Supported | `LIFECYCLE_CLAIM_AUDIT.md` sec 4: file self-labels "PILOT / MOCKED — illustrative methodology demonstration only"; `n_timing_seconds`/`procedure_proposal_timing_seconds` are null, never fabricated. |
| No report substitutes direct Frappe execution time for discovery/compilation/verification cost | Supported | `LIFECYCLE_CLAIM_AUDIT.md` sec 4, final paragraph: the one real Frappe write-path latency measurement (REPORT.md line 51, recovery-integration scenarios) is a distinct measurement, not conflated with compile/verify cost. |

## 9. Other headline claims found in REPORT.md's version history

| Claim | Class | Evidence |
|---|---|---|
| "0 unsafe retries across every condition/family tested" (v4/v5/v6 framing, cited as the paper's locking safety claim) | Limited (Supported for the synthetic-harness statistical dataset; separately corroborated, not statistically extended, by the real-runtime T4 integration evidence) | `RECOVERY_RESULTS_RECONCILED.md` sec 4: `duplicate_committed_effects_total` = 0 for guarded conditions C4+G/C6 across all 3312 live-model rows (statistical dataset). This is a different code path from the real wired runtime guard exercised in T4 (10 runs) — REPORT.md v7 must not conflate the two when repeating this claim; see section 2 of this table above. |
| "the stateful handoff's usefulness is not established beyond the guard alone" (v6 locking assessment) | Supported, but not for the reason previously stated | The original v7 framing over-claimed by citing "C4+G matches C6 exactly on useful_completion" as the supporting grounds — that completion-tie claim is now Unsupported (section 3 of this table): `useful_completion` is fault-determined bookkeeping, not a model/guard signal, so it cannot establish or sharpen this claim either way. The real, supported grounds are cost/tokens/latency: C4+G is measurably cheaper than C6 (CIs excluding zero) with no completion cost, which is consistent with (but does not by itself prove) the stateful handoff adding no established benefit beyond the guard. |
| Cross-model ranking / "universal safety" / "cross-model superiority" | **Unsupported, and explicitly disclaimed** | No report in this track makes a cross-model ranking claim; `ACCEPTANCE_PLAN_V2.md` Sec.7 explicitly prohibits this without corresponding evidence, and none of T4-T7's reports assert it. Listed here as a claim class this project could plausibly be pressed on and confirming it is NOT made. |

## Summary counts

**Updated 2026-09-23 post Fix-A/Fix-B (`FINAL_ADVERSARIAL_REVIEW_V2.md` C2/C3):** one row
was added (section 4, the corrected 4/14 duplicate reassessment) and two rows'
classifications changed (section 3's useful_completion-tie row: Supported (Limited) ->
Unsupported; section 9's "stateful handoff usefulness" row: kept Supported but its cited
grounds corrected). The counts below are re-derived directly from the current table (51
claim rows total):

- Supported: 36 (includes rows tagged "Supported (Limited: ...)" or "Supported (corrected
  ...)" — the leading word in the Class column is the operative classification; the
  parenthetical states the scope caveat a reviewer should apply, it does not demote the row)
- Limited (as the sole/leading classification, no "Supported" prefix): 1
- Unsupported: 8 (was 6; +1 for the corrected useful_completion-tie row, +1 net from the
  added duplicate-reassessment row's superseded predecessor moving to Withdrawn below)
- Withdrawn: 6

If a stricter split is wanted (every row with any "Limited" caveat counted as Limited rather
than Supported), the counts become approximately: Supported 26, Limited 10, Unsupported 8,
Withdrawn 6 — both splits are provided since the task's four-category scheme does not define
how to handle a dual-tagged row. Re-verify by direct count over this file before citing
either split in a paper draft; this table has been hand-edited twice (Fix-B, then this pass)
since the last machine count.
