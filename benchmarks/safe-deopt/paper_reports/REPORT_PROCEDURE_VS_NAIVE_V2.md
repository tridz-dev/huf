# Report: Procedure vs Naive Agent (v2, ACCEPTANCE_PLAN_V2.md Sec.5 / T6)

**Status: EXECUTED.** Supersedes REPORT_PROCEDURE_VS_NAIVE.md per ACCEPTANCE_PLAN_V2.md's
"Superseded artifacts" table. This is the 5 fixed task instances x 2 model families x 2 arms
= 20-execution dataset the plan requires, run on the pinned integration checkout
(PINNED_CHECKOUT.md, HEAD 89918b20295ec062416648361748eaa7805cc72c, branch
research/safe-deopt-v2-integration).

## 0. What ran, where

| Field | Value |
|---|---|
| Worktree | /Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf |
| Branch | research/safe-deopt-v2-integration |
| HEAD before this task | 89918b20295ec062416648361748eaa7805cc72c |
| Script | benchmarks/safe-deopt/procedure_vs_naive.py |
| Results file | benchmarks/safe-deopt/results/procedure_vs_naive_runs.jsonl (22 lines: 2 compilation + 20 instance rows) |
| Models | gemini-3.5-flash-lite, gpt-4o-mini (per TEST_AGENT_SETTINGS.md Sec.1a/1b) |
| Total real spend, full dataset | $0.0302 |
| Total real spend, including one pre-registered smoke check (not part of dataset) | $0.0347 |
| Hard ceiling | $5.00 (RunningCostCeiling in-process); never approached |

## 1. Minimal harness fixes made (disclosed)

Two small, additive fixes were required before the dataset could run; neither changes the
experimental design in ACCEPTANCE_PLAN_V2.md Sec.5:

1. **procedure_vs_naive.py, run_naive_instance**: was calling run_recovery(...) without
   max_tool_calls, silently using the harness default MAX_TOOL_CALLS=20, not the 40
   tool-call budget TEST_AGENT_SETTINGS.md Sec.4(a) specifies. Fixed by passing
   max_tool_calls=40 explicitly. Confirmed necessary: one naive gpt-4o-mini instance
   (CUST-0001+CUST-0004) used exactly 40 model calls / 40 tool calls and hit
   tool_call_cap_reached.
2. **recovery_harness.py, ROLE_SAMPLING["procedure_interpretation_s5"]["openai"]**:
   response_format={"type": "json_schema"} alone is rejected by OpenAI's Chat Completions
   API with 400 "Missing required parameter: 'response_format.json_schema'". Fixed by
   supplying the full json_schema object (name, strict: true, and the
   selected_customers/company/allocated_to schema _validate_binding already checks). Does
   not change what is validated or what counts as a binding failure.

Both fixes verified against the pre-existing frappe-free test suite before any paid run:
`python3 -m pytest benchmarks/safe-deopt/tests/ -q` -> 233 passed, 1 skipped, 4 subtests
passed, unchanged from the pre-fix baseline recorded in PINNED_CHECKOUT.md.

A third, additive-only change captures per-turn tool-call dispatch counts into each naive
instance's extra.per_turn_dispatch / extra.max_tool_calls_in_one_turn (used as the T3
multi-call evidence below); changes no runtime behavior, only what is logged.

## 2. Mandatory conditions -- confirm/deny with evidence

| # | Condition | Verdict | Evidence |
|---|---|---|---|
| 1 | Equivalent starting state/task info/permissions/tool behavior/scoring across arms | Confirmed | Both arms build a fresh FollowupStore per instance, use the same six tool functions, the same task_text(customers) payload, scored by the same score_correctness(store_before, store, customers) against real post-run store state. |
| 2 | Both arms include real model-driven initial interpretation AND final reporting, usage counted | Confirmed | Procedure: interpret_request() + final_response(), both real model calls, both costed. Naive: entire run_recovery loop is model-driven; its terminal final_text turn is that arm's report. |
| 3 | Same execution budget both arms | Confirmed (fix above) | Naive capped at 40 tool calls; Procedure always uses 2 model calls (interpret+final) plus at most 1 repair call -- cap never binds it. |
| 4 | T3 multi-tool-call fix exercised, all calls dispatched, none dropped | Confirmed, direct evidence | Two Gemini naive instances (CUST-0006; CUST-0001+CUST-0004) returned 2 tool calls in a single turn, 4 times each; tool_calls_returned == tool_calls_dispatched in every one of those turns. See Sec.5. |
| 5 | Procedure arm: real execute_procedure, zero LLM calls in that path | Confirmed | Every procedure-arm row has exactly 2 model_calls (interpret, final_response) regardless of customer-set size -- graph execution between those two calls contributes zero additional model calls. |
| 5b | Parse failure -> NOT_EXECUTED_INVALID_BINDING, never ground-truth substitution | Confirmed by code reading; not empirically observed this run | interpret_request() never falls back to the known customer list on failure; on a still-invalid repair, run_procedure_instance short-circuits to extra.procedure_status = "NOT_EXECUTED_INVALID_BINDING" without calling run_real_procedure. G6 (old ground-truth fallback) absent from current code. No instance in this run hit this path (all 10 bindings validated on first attempt) -- verified by code trace, disclosed honestly rather than staged. |
| 5c | interpret_request validates company/allocated_to, not just IDs | Confirmed | _validate_binding() checks selected_customers, company (non-empty + equals COMPANY), and allocated_to (non-empty + equals ALLOCATED_TO) -- all three required in both the Gemini prompt schema and the OpenAI json_schema's "required" list. |
| 5d | Graph labeled hand-authored | Confirmed | Every procedure-arm row's extra.graph_provenance == "hand-authored". compile_procedure()'s discarded model output is logged separately as kind:"compilation" and never feeds the executed graph. |
| 6 | Agent arm: no artificial tool-call forcing; failures classified | Confirmed | No one-call-per-turn forcing (fixed harness dispatches every returned call); tool_choice is auto, never "required". See Sec.6 for classification. |
| 7 | Per-execution measurement completeness | Partially confirmed | latency, model call count, tool call count, input/output/cached tokens, $ cost recorded for every row. Gap disclosed: reasoning_tokens/finish_reason exist per-step in RunLog.entries but ModelCallRecord (the summary object rows are built from) does not carry them forward into the committed JSONL. Both models used report 0 reasoning tokens in practice (neither is a thinking variant), but the field is honestly absent rather than backfilled with an assumed 0. |
| 8 | Arm-order alternation actually used | Confirmed, shown in log order | Instance 1 (odd) -> procedure,naive; instance 2 (even) -> naive,procedure; instance 3 (odd) -> procedure,naive; instance 4 (even) -> naive,procedure; instance 5 (odd) -> procedure,naive -- identical pattern in both families, matching idx%2==1 exactly. |
| 9 | Conclusion scoped to n=5/family/arm | Confirmed | See Sec.7. |

## 3. Model selection / smoke gate

Per TEST_AGENT_SETTINGS.md Sec.1(e), a free-of-outcome smoke check ran before the paid
dataset: one naive-loop call on instance 5 (CUST-0001+CUST-0004) on gemini-3.5-flash-lite.
Result: 10 tool calls, 7 model calls, outcome final_text, correctness True, no malformed
tool-call arguments or out-of-schema function names observed. The gate did not fire -- both
arms of the Gemini family stayed on gemini-3.5-flash-lite for the full dataset. Smoke-check
cost ($0.0045) excluded from dataset totals, reported separately above.

## 4. Results

### 4.1 Compilation cost (one-time per family, NOT part of the 20-execution dataset)

| Model | Prompt tok | Completion tok | Cost | Wall time |
|---|---:|---:|---:|---:|
| gemini-3.5-flash-lite | 850 | 263 | $0.000913 | 2.43s |
| gpt-4o-mini | 710 | 340 | $0.000311 | 4.28s |

This one-time cost is one discarded, no-tools plan-generation model call
(`compile_procedure()` in `procedure_vs_naive.py`), a stand-in for `propose_procedure_from_run`'s
mining cost — not a measurement of the real trace-to-proposal-and-verification path, which was
not invoked in this dataset. No lifecycle break-even/amortization claim is made from this
table anywhere in this report; see `LIFECYCLE_CLAIM_AUDIT.md` (ACCEPTANCE_PLAN_V2.md Sec.6/T7).

### 4.2 Per-family, per-arm summary (n=5 instances each cell)

| Family | Arm | Correct/5 | Total cost | Total model calls | Total wall time | Prompt tok | Completion tok | Cached tok |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| gemini-3.5-flash-lite | Procedure | 5/5 | $0.001544 | 10 | 10.53s | 1,147 | 480 | 0 |
| gemini-3.5-flash-lite | Naive | 3/5 | $0.018201 | 35 | 38.24s | 36,303 | 2,924 | 0 |
| gpt-4o-mini | Procedure | 5/5 | $0.000428 | 10 | 9.71s | 1,406 | 361 | 0 |
| gpt-4o-mini | Naive | 1/5 | $0.008813 | 60 | 65.71s | 77,440 | 2,112 | 54,272 |

Every Procedure-arm row used exactly 2 model calls (interpret + final_response); no repair
call fired (all 10 bindings validated on first attempt).

### 4.3 Per-instance detail

| Family | Instance | Arm order | Procedure correct | Naive correct | Naive model calls | Naive outcome |
|---|---|---|---|---|---:|---|
| gemini | CUST-0001 | Procedure,Naive | True | True | 7 | final_text |
| gemini | CUST-0002 | Naive,Procedure | True | False | 7 | final_text |
| gemini | CUST-0004 | Procedure,Naive | True | True | 7 | final_text |
| gemini | CUST-0006 | Naive,Procedure | True | False | 7 | final_text |
| gemini | CUST-0001+0004 | Procedure,Naive | True | True | 7 | final_text |
| openai | CUST-0001 | Procedure,Naive | True | False | 5 | escalated |
| openai | CUST-0002 | Naive,Procedure | True | True | 5 | escalated |
| openai | CUST-0004 | Procedure,Naive | True | False | 5 | escalated |
| openai | CUST-0006 | Naive,Procedure | True | False | 5 | escalated |
| openai | CUST-0001+0004 | Procedure,Naive | True | False | 40 | tool_call_cap_reached |

## 5. Multi-tool-call (T3 fix) evidence

Two naive Gemini instances show genuine multi-call turns, returned == dispatched every time:

```
CUST-0006 (gemini-3.5-flash-lite):
  turn 1: returned=1 dispatched=1
  turn 2: returned=2 dispatched=2
  turn 3: returned=2 dispatched=2
  turn 4: returned=2 dispatched=2
  turn 5: returned=2 dispatched=2
  turn 6: returned=1 dispatched=1

CUST-0001+CUST-0004 (gemini-3.5-flash-lite):
  turn 1: returned=1 dispatched=1
  turn 2: returned=2 dispatched=2
  turn 3: returned=2 dispatched=2
  turn 4: returned=2 dispatched=2
  turn 5: returned=2 dispatched=2
  turn 6: returned=1 dispatched=1
```

No gpt-4o-mini naive turn returned more than 1 tool call in this dataset -- an observed
model behavior on this task, not a harness limitation: the fixed harness parses
tool_calls[*] (plural, all entries), so a batched OpenAI response would have been dispatched
in full had one occurred; none did.

## 6. Failure classification (naive arm)

| Instance | Family | Classification | Basis |
|---|---|---|---|
| CUST-0002 | gemini | Model-caused | outcome final_text (model chose to stop, no cap hit), resulting state didn't match ground truth. |
| CUST-0006 | gemini | Model-caused | Same: final_text, no cap hit, incorrect final state despite 2-call batching working correctly. |
| CUST-0001 | openai | Model-caused (escalation) | outcome escalated -- model called escalate rather than completing; legitimate model choice, scored incorrect since it did not produce the correct final state. Not harness/budget-caused (5 of 40 calls used). |
| CUST-0004 | openai | Model-caused (escalation) | Same pattern. |
| CUST-0006 | openai | Model-caused (escalation) | Same pattern. |
| CUST-0001+0004 | openai | Budget-caused | outcome tool_call_cap_reached at exactly 40/40 -- model repeated single-tool-call turns without converging or escalating; hit the harness's execution budget, not a harness defect. Reported as budget-caused per Sec.5's explicit rule. |

No harness-caused (silently-dropped-call) failures occurred in this dataset -- the one
harness limitation found (the OpenAI response_format 400) was caught and fixed before any
paid run and did not appear as a failure mode in the final dataset.

## 7. Conclusion (scoped to n=5 per family per arm -- no generalized claim)

Within this specific 20-execution dataset (5 fixed task instances x 2 model families x 2
arms, one run per cell, no repetitions):

- The Procedure arm was correct on all 10 of its executions (5/5 in each family) and used a
  small, constant 2 model calls per execution regardless of customer-set size, at low cost
  ($0.0003-0.0016 total per family across 5 instances).
- The naive arm was correct on 3/5 (gemini) and 1/5 (gpt-4o-mini) executions in this sample,
  used substantially more model calls, tokens and wall time per execution, and one instance
  (gpt-4o-mini, two customers) exhausted its full 40-tool-call budget without reaching a
  final state.
- The multi-tool-call fix (T3) is empirically exercised and correct in this run: Gemini
  batched 2 calls per turn on 2 of 10 naive instances, and every batched call was
  dispatched, none dropped.
- Arm-order alternation was applied and is visible in the row order for every instance in
  both families.

This sample is far too small (n=5 per family per arm, one run each) to support any claim
about a general speedup, cost savings, or correctness advantage of Procedures over agents,
or about either model family's general capability. No such claim is made here. The naive
arm's lower correctness in this particular sample reflects this specific task, these two
specific models, this specific one-shot (non-repeated) draw, and the fixed 40-call/no-repair
budget it was given -- not a general property of naive agentic execution. Non-determinism
was not controlled for by repetition, consistent with the plan's "stop adding experiments"
rule; a different draw on the same models could show different per-instance outcomes.

## 8. Secrets protocol compliance

- OpenAI key: extracted from ~/.zshrc's OPENAI_KEY and exported as OPENAI_API_KEY in the
  same shell command as the execution command. Never echoed, never logged.
- Gemini key: /workspace/development/ury/sites/ury.localhost/site_config.json confirmed
  unreachable from this macOS host before falling back to ~/.zshrc's GEMINI_API_KEY,
  extracted and used the same way, in the same shell command.
- Every file this task wrote or touched (procedure_vs_naive.py, recovery_harness.py,
  results/procedure_vs_naive_runs.jsonl, this report) was grepped for
  AIza[A-Za-z0-9_-]{20,} and sk-[A-Za-z0-9_-]{20,} before commit: zero matches in all four.
- Real (non-mocked) execution verified via real_accounting: true on every one of the 20
  instance rows and both compilation rows.
