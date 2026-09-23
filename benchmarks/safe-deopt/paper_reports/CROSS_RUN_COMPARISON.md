# Cross-Run Token / Cost / Time Comparison

> Descriptive internal QA/sanity-checking only. This is not a fifth experiment and does not add a paper claim. Sources remain separate because they differ in scope, task complexity, turn budgets, and fault mix.

## 1. Main dataset — per condition × model family

Source: `results/scored_v2/per_condition_family.csv`.

| condition | model | n | mean cost/attempt ($) | mean total tok | mean latency (s) |
|---|---|---:|---:|---:|---:|
| C1 | gemini-3.5-flash-lite | 600 | 0.001015 | 2244.5 | 6.194 |
| C1 | gpt-4o-mini-2024-07-18 | 120 | 0.000275 | 1440.5 | 4.152 |
| C4 | gemini-3.5-flash-lite | 530 | 0.000653 | 1443.2 | 5.087 |
| C4 | gpt-4o-mini-2024-07-18 | 106 | 0.000099 | 509.5 | 1.778 |
| C4+G | gemini-3.5-flash-lite | 530 | 0.000636 | 1387.2 | 5.104 |
| C4+G | gpt-4o-mini-2024-07-18 | 106 | 0.000090 | 454.2 | 1.659 |
| C5 | gemini-3.5-flash-lite | 530 | 0.000875 | 2092.1 | 4.915 |
| C5 | gpt-4o-mini-2024-07-18 | 106 | 0.000391 | 2244.6 | 4.191 |
| C6 | gemini-3.5-flash-lite | 530 | 0.000879 | 2121.0 | 5.603 |
| C6 | gpt-4o-mini-2024-07-18 | 106 | 0.000348 | 2009.6 | 3.809 |

The main scored CSV persists total tokens rather than input/output/reasoning components, so it is not reverse-engineered here.

## 2. T4 real HUF recovery integration — scenario × model family

Source: `results/llm_recovery_integration_v2.jsonl` (10 rows). Cost and latency are not persisted in this artifact.

| scenario | model | n | mean cost/attempt ($) | mean input tok | mean output tok | mean reasoning/handoff tok | mean latency (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| S1_committed_response_lost_F2 | gemini-3.5-flash-lite | 1 | n/a | 3268.0 | 139.0 | n/a | n/a |
| S1_committed_response_lost_F2 | gpt-4o-mini | 1 | n/a | 3673.0 | 106.0 | n/a | n/a |
| S2_not_committed_ambiguous_timeout_F3 | gemini-3.5-flash-lite | 1 | n/a | 2997.0 | 92.0 | n/a | n/a |
| S2_not_committed_ambiguous_timeout_F3 | gpt-4o-mini | 1 | n/a | 2428.0 | 131.0 | n/a | n/a |
| S3_late_commit_F7 | gemini-3.5-flash-lite | 1 | n/a | 3079.0 | 125.0 | n/a | n/a |
| S3_late_commit_F7 | gpt-4o-mini | 1 | n/a | 2493.0 | 73.0 | n/a | n/a |
| S4_reject_then_permitted_retry_F1 | gemini-3.5-flash-lite | 1 | n/a | 4162.0 | 121.0 | n/a | n/a |
| S4_reject_then_permitted_retry_F1 | gpt-4o-mini | 1 | n/a | 2407.0 | 117.0 | n/a | n/a |
| S5_permission_denial_same_identity | gemini-3.5-flash-lite | 1 | n/a | 1851.0 | 126.0 | n/a | n/a |
| S5_permission_denial_same_identity | gpt-4o-mini | 1 | n/a | 2314.0 | 60.0 | n/a | n/a |

## 3. T6 Procedure-vs-naive — arm/kind × model family

Source: `results/procedure_vs_naive_runs.jsonl` (2 compilation and 20 instance rows).

| kind/arm | model | n | mean cost/attempt ($) | mean input tok | mean output tok | mean cached tok | mean latency (s) |
|---|---|---:|---:|---:|---:|---:|---:|
| compilation | gemini-3.5-flash-lite | 1 | 0.000913 | 850.0 | 263.0 | 0.0 | 2.434 |
| compilation | gpt-4o-mini | 1 | 0.000311 | 710.0 | 340.0 | 0.0 | 4.280 |
| naive | gemini-3.5-flash-lite | 5 | 0.003640 | 7260.6 | 584.8 | 0.0 | 7.648 |
| naive | gpt-4o-mini | 5 | 0.001763 | 15488.0 | 422.4 | 10854.4 | 13.143 |
| procedure | gemini-3.5-flash-lite | 5 | 0.000309 | 229.4 | 96.0 | 0.0 | 2.106 |
| procedure | gpt-4o-mini | 5 | 0.000086 | 281.2 | 72.2 | 0.0 | 1.941 |

## 4. F4 rerun — before vs corrected after

Source: corrected `results/runs_f4_rerun.jsonl`, compared with matching F4 rows in `results/runs.jsonl.pre-f4-fix.bak`.

| phase | n | mean cost/attempt ($) | mean input tok | mean output tok | mean handoff tok | mean latency (s) |
|---|---:|---:|---:|---:|---:|---:|
| before (buggy) | 180 | 0.000529 | 1166.6 | 90.1 | 338.4 | 3.928 |
| after (corrected) | 180 | 0.000358 | 751.5 | 63.6 | 255.2 | 2.106 |

## Synthesis

Where spend is persisted, sources #1 and #3 show internally plausible model-family accounting; the observed per-call range is driven mainly by prompt/turn scope, not an obvious pricing drift. Source #2 has token totals but no persisted spend or elapsed-time field, so it supports a token comparison only. Source #4 is a correction audit, not a new treatment comparison: before/after differences reflect the fixed F4 injector and changed valid accounting. Direct cross-source comparisons remain limited by task complexity, turn budgets, scenario counts, and fault mixes.


