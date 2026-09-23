# Safe-Deopt Experiment -- Full Report Package

This directory mirrors the key planning/results/audit documents for the safe-deoptimization
research project, committed here so they are reachable by anyone with access to this repo
and branch (`research/safe-deopt-v2-integration`), not only on the author's local machine.
Source of truth for ongoing work remains
`/Users/safwan/Code/Huf/workspace/Tracks/SafeDeoptExperiment/` (host-local, not committed);
this is a point-in-time copy taken as of commit `0986fc438` plus the classification fix
described below.

All paths below are relative to this directory (`benchmarks/safe-deopt/paper_reports/`).

## Read first

- [`ACCEPTANCE_PLAN_V2.md`](ACCEPTANCE_PLAN_V2.md) -- the plan and acceptance criteria this
  project was executed against.
- [`RECOVERY_RESULTS_RECONCILED.md`](RECOVERY_RESULTS_RECONCILED.md) -- the canonical
  reconciled results, including the F4 rerun (2026-09-23) and the classifier fix that
  followed it (288 -> 336 -> 288 quarantined + 48 legitimate-no-model).
- [`EXCLUSIONS_AND_FAILURES.md`](EXCLUSIONS_AND_FAILURES.md) -- everything excluded,
  quarantined, or that failed, with citations.
- [`CLAIM_TO_EVIDENCE_TABLE.md`](CLAIM_TO_EVIDENCE_TABLE.md) -- every claim in the write-up
  mapped to its supporting evidence.
- [`FINAL_ADVERSARIAL_REVIEW_V2.md`](FINAL_ADVERSARIAL_REVIEW_V2.md) -- the adversarial
  review pass and findings (H1-H3, C1-C3) that drove the F4 fix/rerun and this
  classification fix.

## Analyses

- [`analysis_c4g_vs_c6_v2.md`](analysis_c4g_vs_c6_v2.md) -- matched C4+G vs C6 comparison,
  including the F4-inclusion re-derivation.
- [`analysis_openai_c5_duplicates_v2.md`](analysis_openai_c5_duplicates_v2.md) -- the OpenAI
  C5 duplicate-committed-effect findings, including the 14-vs-12 count reconciliation.
- [`analysis_percondition_costs_v2.md`](analysis_percondition_costs_v2.md) -- per-condition
  cost/completion tables from `canonical_scoring.py`.

## Integration reports

- [`REPORT_LLM_RECOVERY_INTEGRATION_V2.md`](REPORT_LLM_RECOVERY_INTEGRATION_V2.md)
- [`REPORT_PROCEDURE_VS_NAIVE_V2.md`](REPORT_PROCEDURE_VS_NAIVE_V2.md)
- [`CONTRACT_TEST_RESULTS.md`](CONTRACT_TEST_RESULTS.md) -- guarantee-contract test results
  (T2), including the F4 commit-then-fabricate finding that motivated the fix in
  `../faults.py`.

## Audit trail / environment

- [`LIFECYCLE_CLAIM_AUDIT.md`](LIFECYCLE_CLAIM_AUDIT.md)
- [`TEST_AGENT_SETTINGS.md`](TEST_AGENT_SETTINGS.md)
- [`PINNED_CHECKOUT.md`](PINNED_CHECKOUT.md)

## Regenerating the scored tables

```
cd benchmarks/safe-deopt
python3 canonical_scoring.py --input results/runs.jsonl --output results/scored_v2
```

`results/scored_v2/*` (not committed -- generated output) is the single source of truth for
every number quoted in these documents; regenerate it from `results/runs.jsonl` with the
command above to reproduce them.
