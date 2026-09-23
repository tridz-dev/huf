# Per-condition costs -- v2 (regenerated from canonical_scoring.py)

Supersedes analysis_percondition_costs.md, whose token accounting mixed the 48 zero-token
gpt-4o-mini rows into real-row aggregates without reconciling them, and whose C2/C3 claim
is reconfirmed (not merely re-cited) below with a fresh count.

## Commands run

```
cd benchmarks/safe-deopt
python3 canonical_scoring.py --input results/runs.jsonl --output results/scored_v2
```

**Update 2026-09-23 (classifier fix, post F4-rerun):** the counts and tables below predate
both the F4 rerun (`RECOVERY_RESULTS_RECONCILED.md` "Update 2026-09-23") and the
classifier fix that followed it. After both: `class_counts` is
`{"invalid": 288, "legitimate-no-model": 48, "live-model": 3264}` over the same 3600-row
`runs.jsonl`. The 288 quarantined rows below are unchanged (still F0/F5, no fault fired,
no legitimate reason for zero tokens). The F4 rerun additionally produced 48 new
zero-token rows (fault F4, workload W2-nonidempotent, a genuine fault-detected competing
write) that are correctly classified `legitimate-no-model`, not pooled into the
API-cost table (`per_condition_family.csv`, still live-model-only) but included in the
new end-to-end task view (`end_to_end_per_condition_family.csv`). Full reconciliation:
`RECOVERY_RESULTS_RECONCILED.md` "Update 2026-09-23 (part 2)".

## Row-class counts (runs.jsonl, 3600 rows)

class_counts (script's own summary): {"invalid": 288, "live-model": 3312}. No
legitimate-no-model, no mock rows. 288 = 48 gpt-4o-mini + 240 gemini-3.5-flash-lite rows,
all sharing the shape: LLM condition (never C2/C3), zero tokens/cost, null
transcript_path, claiming tokens_are_real_accounting=true. All 288 are quarantined --
excluded from every table below.

## Per-condition-family costs (live-model rows only)

Source: results/scored_v2/per_condition_family.csv (verbatim columns, n = row count after
quarantine):

| condition | model_id | n | success_rate | mean_cost_per_attempt_usd | mean_tokens_per_attempt | cost_per_success_usd |
|---|---|---|---|---|---|---|
| C1 | gemini-3.5-flash-lite | 600 | 0.275 | 0.0010203 | 2257.75 | 0.0037100 |
| C1 | gpt-4o-mini-2024-07-18 | 120 | 0.3083 | 0.0002780 | 1456.73 | 0.0009015 |
| C4 | gemini-3.5-flash-lite | 540 | 0.7130 | 0.0006494 | 1435.86 | 0.0009108 |
| C4 | gpt-4o-mini-2024-07-18 | 108 | 0.5185 | 0.0000982 | 504.70 | 0.0001893 |
| C4+G | gemini-3.5-flash-lite | 540 | 0.5 | 0.0006322 | 1378.42 | 0.0012644 |
| C4+G | gpt-4o-mini-2024-07-18 | 108 | 0.5 | 0.0000892 | 450.21 | 0.0001783 |
| C5 | gemini-3.5-flash-lite | 540 | 0.6704 | 0.0008733 | 2086.61 | 0.0013027 |
| C5 | gpt-4o-mini-2024-07-18 | 108 | 0.6667 | 0.0003936 | 2257.79 | 0.0005904 |
| C6 | gemini-3.5-flash-lite | 540 | 0.5 | 0.0008781 | 2117.38 | 0.0017563 |
| C6 | gpt-4o-mini-2024-07-18 | 108 | 0.5 | 0.0003505 | 2026.69 | 0.0007010 |

(C4 and C4+G rows include the quarantined 48 gpt-4o-mini "gpt-4o-mini" (no version
suffix) and 240 gemini zero-token rows as *separate* rows already excluded from n above --
per-condition n's here are 540/108, i.e. 600/120 minus quarantined count for that cell,
confirming the quarantine was applied per-cell, not just in aggregate.)

**No C2 or C3 row exists anywhere in runs.jsonl** -- confirmed by direct condition-count
over all 3600 scored rows (C1/C4/C4+G/C5/C6 only, 720 each). C2 and C3 rows exist only in
results/runs.mock.jsonl (60 rows each, part of a 420-row all-conditions mock/pilot file),
never in the real dataset.

## Token reconciliation

results/scored_v2/summary JSON: reconciliation_failures = [] (count 0) over all 3600 rows.
cached_tokens <= input_tokens holds on every row; no reasoning_tokens are present in this
dataset (all zero) and are, per the script, kept as a separate column rather than folded
into input/output regardless.

## What changed vs the superseded analysis

- The superseded doc's "48 zero-token rows" framing undercounted the issue: the same
  zero-token/null-transcript shape recurs in 240 Gemini rows, not just OpenAI's 48. Both
  populations are quarantined identically here (288 total), not pooled with real rows.
- Per-condition costs above are computed strictly over the 3312 live-model rows, so C4 and
  C4+G's per-attempt cost/token figures are not diluted by free/zero-cost rows the way an
  un-quarantined aggregate would be.
- The C2/C3 "no real data" finding is reconfirmed exactly, with an explicit row count (0
  real rows, 60 mock rows each) rather than restated from the prior doc.

## Lifecycle / break-even (not reconciled by this rerun)

This regeneration covers per-condition token/cost/latency only; it does not touch the
break-even question. Status, per `analysis_percondition_costs.md`'s "Break-even:
PROVISIONAL" section and `LIFECYCLE_CLAIM_AUDIT.md` (ACCEPTANCE_PLAN_V2.md Sec.6/T7):
`results/breakeven.json` remains self-labeled illustrative/mocked, real compile+verification
timing (`propose_procedure_from_run` / `huf/ai/procedure_proposal.py`) has still never been
run against a live bench, and no numerical lifecycle break-even is claimed here or anywhere
in the reconciled dataset.

## Bottom line on C2/C3

**No C2 (or C3) comparison is possible with current data.** Any per-condition cost or
success-rate comparison involving C2 or C3 in prior reports is necessarily built from
runs.mock.jsonl's mocked pilot rows, not real model executions, and should not be
presented as an empirical result. H3 ("deterministic recovery alone (C3) suffices...")
remains untested by real data; T4/T6's real-model work did not add C2/C3 executions
either (results/llm_recovery_integration_v2.jsonl and results/procedure_vs_naive_runs.jsonl
were checked and contain no C2/C3 rows).
