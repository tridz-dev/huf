# Cross-Run Token / Cost / Time Comparison

> Descriptive internal QA/sanity-checking only. This is not a fifth experiment and does not add a paper claim. Sources remain separate because they differ in scope, task complexity, turn budgets, and fault mix.

## What this document is about

[HUF](https://github.com/tridz-dev/huf) is open-source, self-hosted AI infrastructure for any application: a multi-agent and multi-modal platform with provider routing, local-model support, knowledge grounding, tool/code execution, skills and apps, multi-channel gateways, MCP integrations, visual flows, human-in-the-loop controls, and observability. It can connect cloud providers such as OpenAI, Anthropic, and Google Gemini alongside local or OpenAI-compatible endpoints, so teams can keep their data and deployment under their control rather than depending on a single hosted assistant platform.

An **Agent Procedure** is one HUF capability for turning a known, repeatable agent workflow into a validated executable graph. In this evaluation, the model interprets the request and reports the result, while the Procedure graph carries out the known intermediate tool steps without asking the model to rediscover each step interactively.

The comparison therefore tests a feature/implementation inside HUF, not a separate model or a new standalone agent framework. The “naive” arm is the same task performed through an ordinary model-driven loop that repeatedly reasons, selects tools, observes results, and continues. The Procedure idea is most useful when a business operation has a repeatable sequence of roughly 3-8 tool calls, especially when that sequence is executed many times and must be recoverable after a partial failure.

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

## T6 task-level comparison: what was done

The five fixed tasks were: create `CUST-0001` / `SINV-2001`; handle already-existing `CUST-0002` / `SINV-2002`; create `CUST-0004` / `SINV-2004`; create both `SINV-2006A` and `SINV-2006B` for `CUST-0006`; and process the two-customer task `CUST-0001 + CUST-0004`. Each task was run once with each arm under each model family, for 20 executions total.

With the procedure, the model interpreted and validated the request, the precompiled graph executed the required database/tool steps, and the model produced the final response: two model calls per task. Without the procedure, the model repeatedly reasoned through the workflow and issued the individual tool calls step by step; the two-customer GPT task reached the 40-call execution cap.

### Observed average gain/loss per task

Percentages are calculated as `(without procedure − with procedure) / without procedure`; positive values therefore mean reduction with the procedure. These are descriptive averages over five tasks, excluding the one-time compilation rows.

| model | with procedure: tokens / time / cost | without procedure: tokens / time / cost | token reduction | time reduction | cost reduction | correctness |
|---|---|---|---:|---:|---:|---|
| Gemini | 325 / 2.11 s / 0.031¢ | 7,845 / 7.65 s / 0.364¢ | 95.9% | 72.5% | 91.5% | 5/5 vs 3/5 |
| GPT-4o-mini | 353 / 1.94 s / 0.009¢ | 15,910 / 13.14 s / 0.176¢ | 97.8% | 85.2% | 95.1% | 5/5 vs 1/5 |

The procedure arm also reduced model calls from 7.0 to 2.0 on average for Gemini and from 10.8 to 2.0 for GPT-4o-mini. This remains a small, fixed-task comparison—not evidence of a universal percentage improvement. The compilation calls are reported separately above because lifecycle break-even was not measured in this run.

## Illustrative scale example: 10,000 invoices per month

The following is a planning illustration, not an additional experiment. Its basis is the
T6 Procedure-vs-naive dataset (n=5 tasks per arm per model family, no confidence
intervals) — the per-invoice cost/time/token figures below are those five-task averages
applied unchanged to a hypothetical volume, not a new or larger measurement. It applies the
measured five-task averages from T6 unchanged to 10,000 repeated invoice workflows. It assumes each invoice follows a repeatable 3-8 tool-call sequence such as: read the customer and invoice context, validate line items and tax rules, create or update the invoice, record the payment/status transition, and send or schedule a confirmation. Actual production totals would depend on model choice, prompt size, batching, caching, retries, concurrency, and the exact HUF graph.

| Model | Arm | Cost / invoice | Monthly cost | Annual cost | Aggregate model time / month* | Monthly tokens |
|---|---|---:|---:|---:|---:|---:|
| Gemini | Procedure | $0.000309 | $3.09 | $37.08 | 5.85 h | 3.25M |
| Gemini | Naive | $0.003640 | $36.40 | $436.80 | 21.24 h | 78.45M |
| GPT-4o-mini | Procedure | $0.000086 | $0.86 | $10.32 | 5.39 h | 3.53M |
| GPT-4o-mini | Naive | $0.001763 | $17.63 | $211.56 | 36.51 h | 159.10M |

Under this illustrative scaling, the Procedure arm reduces direct model spend by about **$33.31/month ($399.72/year)** for Gemini or **$16.77/month ($201.24/year)** for GPT-4o-mini, relative to the measured naive-arm averages. Aggregate model execution time falls by about **15.39 hours/month** for Gemini or **31.12 hours/month** for GPT-4o-mini. These are summed model-seconds, not a promise that a production queue would take that long on the calendar: parallel workers could reduce elapsed wall-clock duration, while rate limits or serialized dependencies could increase it.

The projection also illustrates why repeated, structured work is the natural use case: a small per-invoice reduction compounds across 10,000 invoices. It does **not** establish production correctness, capacity, lifecycle break-even, or universal savings; those require workload-specific operational measurements.
