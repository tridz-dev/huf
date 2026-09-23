# Test agent settings for the ACCEPTANCE_PLAN_V2 reruns

Status: **CONFIG DESIGN. Not executed, not yet wired.** This sheet sets every model-call
setting for the reruns in [`ACCEPTANCE_PLAN_V2.md`](ACCEPTANCE_PLAN_V2.md) (§3, §4, §5). The
settings are grounded in what the harness in
`worktrees/safe-deopt-experiment/huf/benchmarks/safe-deopt/` sends today
(`recovery_harness.py`, `run_experiment.py`, `procedure_vs_naive.py`,
`llm_real_procedure_integration.py`). Section 0 lists every harness gap that must be closed
before a setting below can take effect.

## Quick reference

```yaml
models:                                  # both families, every role
  gemini: gemini-3.5-flash-lite          # AGENTS.md primary; pricing already in harness table
  openai: gpt-4o-mini                    # only OpenAI model the harness has pricing for
  roles:
    naive_agent_loop_s5:          {gemini: gemini-3.5-flash-lite, openai: gpt-4o-mini}
    procedure_interpretation_s5:  {gemini: gemini-3.5-flash-lite, openai: gpt-4o-mini}
    procedure_compilation_s5:     NOT RUN (graph is hand-authored; label it so) - see 1(c)
    final_report_s5_both_arms:    {gemini: gemini-3.5-flash-lite, openai: gpt-4o-mini}
    recovery_decision_s3:         {gemini: gemini-3.5-flash-lite, openai: gpt-4o-mini}
    affected_cell_reruns_s4:      original models + ORIGINAL (unset) sampling params, unchanged
  escalation_model_not_default:   gemini-3.5-flash  # only via the pre-registered gate in 1(e)

sampling:            # values sent explicitly and recorded; "unset" means the provider default, recorded as unset
  naive_agent_loop_s5:         {gemini: {temperature: 1.0, top_p: unset}, openai: {temperature: 1.0, top_p: 1.0}}
  final_report_s5:             same as naive_agent_loop_s5 (both arms identical)
  procedure_interpretation_s5: {gemini: {temperature: 1.0, top_p: unset, responseMimeType: application/json, responseSchema: binding},
                                openai: {temperature: 0.0, top_p: 1.0, response_format: json_schema(strict)}}
  recovery_decision_s3:        {gemini: {temperature: 1.0, top_p: unset}, openai: {temperature: 0.2, top_p: 1.0}}
  s4_reruns:                   {temperature: unset, top_p: unset}   # must match the original runs
  gemini_thinking:             unset (provider default); record thoughtsTokenCount per call
  max_output_tokens:           {gemini: 8192, openai: 2048}    # finish_reason=length/MAX_TOKENS -> harness failure
  seed:                        {openai: 20260923 (best-effort), gemini: 20260923 in generationConfig.seed (best-effort)}
  parallel_tool_calls:         {openai: true (default, sent explicitly), gemini: native (multiple functionCall parts)}
  tool_choice:                 auto on every tool-loop call (never "required", never a forced name)

budgets:
  s5_naive_max_tool_calls:     40     # per instance; worst instance needs ~16-20
  s5_naive_max_model_calls:    25
  s5_procedure_repair_calls:   1      # one logged, cost-included re-ask on a malformed binding
  s3_max_model_turns: {S1_committed_lost: 6, S2_not_committed: 8, S3_late_commit: 10, S4_reject_then_retry: 8, S5_permission_denied: 6}
  s3_max_tool_calls_per_scenario: 12
  hard_spend_ceiling_usd:      5.00   # RunningCostCeiling, shared across s3+s5 (+ s4 reruns if they share a process)
  projected_spend_usd:         ~0.9 typical, ~2.1 worst case (see section 6)

context:
  history:            full transcript, no summarization, no truncation
  caching:            implicit provider caching only (can't be turned off on OpenAI); no explicit cachedContents
  cost_formula:       (input - cached)*in + cached*cached_in + (output + reasoning)*out   # cached is a SUBSET of input
transport:
  timeout_s: 60
  retry: {on: [429, 500, 502, 503, 504, URLError], max: 3, backoff_s: [2, 8, 30], counted_as: harness_retry, cost_included: true}
```

## 0. Harness gaps these settings depend on (check before any paid run)

Neither provider class currently sends any sampling parameters. `GeminiHTTPProvider.generate`
sends only `contents`, `system_instruction` and `tools`. `OpenAIHTTPProvider.generate` sends
only `model`, `messages` and `tools`. So every past live run used provider defaults, and a
"temperature" recorded anywhere for those runs is the provider default, not a chosen value.
The small, additive changes below are needed. None of them changes the runtime path under test.

| # | Gap (file:line, approx.) | Required change | Protects |
|---|---|---|---|
| G1 | No `generationConfig` / sampling params in either `generate()` (`recovery_harness.py` ~532, ~688) | Add an optional `sampling: dict` constructor arg on both providers and on `LiveAPIModel`. When it is `None`, send nothing, which matches past behavior for §4 reruns. Store the exact request params in every `model_step` log entry. | §1 "record exact ... settings", §4 original-condition reruns |
| G2 | `_parse_openai_response` reads only `tool_calls[0]` (~739). `_parse_gemini_response` keeps only the first `functionCall` part (~580). | Parse **all** tool calls. Dispatch them in the order returned. Return one result per call id: OpenAI rejects a turn with unanswered `tool_call_id`s, and Gemini needs one `functionResponse` per `functionCall`, with the `thoughtSignature` on the first part echoed. Log `tool_calls_returned` and `tool_calls_dispatched` for each step, and assert they are equal. | §5 "no silent dropping, no forced one-call-per-response" (hard requirement) |
| G3 | Gemini `usageMetadata.thoughtsTokenCount` is not read. Gemini 3.x bills thinking tokens as output. | Read `thoughtsTokenCount` into a new `reasoning_tokens` field. Also read OpenAI `usage.completion_tokens_details.reasoning_tokens` (0 for 4o-mini, but recorded). Cost formula: `output_billed = completion + reasoning`. Keep them separate in the tables. | §4 "handle provider reasoning-token fields explicitly" |
| G4 | `finishReason` / `finish_reason` not recorded | Record it per step. `MAX_TOKENS`/`length` goes in the harness/budget failure bucket, not the model-correctness bucket. | §5 "record whether failures are model/tool/harness/budget-caused" |
| G5 | `llm_real_procedure_integration.py` has a flat `max_turns=4` | Use the per-scenario budgets from section 4. | §3 "model may avoid/escalate rather than being forced" |
| G6 | `procedure_vs_naive.py` ~796 falls back to ground-truth customers on a parse failure | Remove the fallback. Parse failure means one logged repair call (section 4), then a failure row. | §5 "never substitute ground truth on a parse failure" |
| G7 | Pricing table has no `gemini-3.5-flash` | Only needed if gate 1(e) fires. Fetch the price live on the day, date it, and add it before any flash call. | §4/§7 "every number traces to an artifact" |
| G8 | No `seed` sent, no `system_fingerprint` / `modelVersion` recorded for OpenAI | Send the seed (section 5). Record `system_fingerprint` (OpenAI). `modelVersion` (Gemini) is already recorded. | §1 model-version pinning |

## 1. Model selection per role

**(a) Naive agent-loop arm (§5): `gemini-3.5-flash-lite` / `gpt-4o-mini`.**
This follows the AGENTS.md primary. These are also the only two models the harness prices, and
the models the earlier `procedure_vs_naive` run used, so the rerun changes only what §5 says to
change. I have not moved the naive arm to `gemini-3.5-flash` by default, for two reasons.
First, §5's comparison is between arms on the *same* model. A stronger model helps both arms
and does not make the comparison fairer. Second, the multi-tool-call failure that §5 names was
a *harness* defect: the harness parsed only `tool_calls[0]` and the first `functionCall`. That
is gap G2. It is not a model-capability defect, and switching to a stronger model would hide
it rather than fix it. Both families emit parallel calls natively.

**(b) Procedure interpretation (§5): same model as that family's naive arm.**
§5 requires "equivalent ... real model-driven initial interpretation" on both arms. Using a
different or stronger model here would give the Procedure arm an advantage the naive arm
doesn't get.

**(c) Procedure compilation (§5/§6): do not run a compile call in the §5 dataset.**
The pinned graph comes from `build_followup_procedure_graph` and is **hand-authored**. §5
requires the dataset to say so (`graph_provenance: hand-authored`). The existing
`compile_procedure()` output is discarded, so it is plan-generation cost, not compilation
cost (§6). Running it inside the 20-execution dataset would invite exactly the mislabeling
§6 forbids. If you want it for §6 anyway, run it once per family in a separate file labelled
`plan_generation_cost`. It uses the same model and the interpretation sampling settings, and
it never feeds the Procedure arm.

**(d) Recovery-decision LLM, HUF integration (§3): `gemini-3.5-flash-lite` / `gpt-4o-mini`.**
These are the same models §4's recovery cells were run on. So §3's integration evidence and
§4's corrected tables describe the same models, and the claim-to-evidence table (§7) doesn't
have to explain a model change.

**(e) Pre-registered deviation gate: the only place `gemini-3.5-flash` may enter.**
Before any paid §3/§5 run, do a **free-of-outcome smoke check**. It is one naive-loop call on
instance 5 (two customers, the one most likely to draw parallel calls) with G2 wired. Check
only the harness, not task success. If `gemini-3.5-flash-lite` returns *malformed* tool calls
(bad JSON args, a missing required field in >1 of the calls, or a function name outside the
schema), switch **both arms** of the Gemini family to `gemini-3.5-flash` for §5. Record the
switch and the smoke transcript as an exclusion with its reason. Do this once, before the
dataset starts. Never switch mid-dataset or after seeing results, because that would be the
"rerun selectively until it passes" that §3 and the ground rules forbid. §3 and §4 stay on
flash-lite either way. My prior is that the gate won't fire. **Do not** use
`gemini-3.1-flash-lite` for anything (per AGENTS.md).

**OpenAI family.** `gpt-4o-mini` stays for every role. Newer OpenAI small models exist, but
the harness has neither pricing nor a verified request shape for them. §4 also requires
reruns "at original models", so a different OpenAI model in §3/§5 would break the link to
§4's 14-duplicate reassessment.

## 2. Temperature and top_p

**Gemini: temperature 1.0 everywhere (sent explicitly), top_p unset.** Google's guidance for
the Gemini 3.x family is to keep the default temperature of 1.0. Lowering it is documented to
cause looping or degraded reasoning in thinking models. So for Gemini, "low temperature for
consistency" would *add* a failure mode instead of reducing noise. Sending 1.0 explicitly
changes nothing about what the model does compared with the provider default. What it adds is
a recorded value instead of "default", which protects §1. I'm leaving top_p unset because
there is no documented reason to change it. It is recorded as `unset/provider-default`.

**OpenAI naive loop and final report: temperature 1.0, top_p 1.0.** These are OpenAI's
defaults, sent explicitly. This keeps §5's "normal model-chosen tool sequencing": a naive arm
held at temperature 0 would be less realistic, because deployed agent loops don't run
greedy, and it would make the naive arm look more consistent than it really is. Both arms'
final-report calls use the same values, so reporting quality isn't an extra variable
(§5 "equivalent ... final reporting").

**OpenAI Procedure interpretation: temperature 0.0, top_p 1.0, plus strict `response_format`
JSON schema.** This step is a narrow NL-to-JSON binding (`selected_customers`, plus every
other task-relevant input §5 says to validate). Randomness adds nothing to what is being
measured, and parse or binding errors must be *model* errors, not sampling noise. Strict
structured output doesn't substitute for model judgement: the model still chooses the values,
and wrong values still count as failures under §5. **Gemini equivalent:** temperature 1.0
(see above), with `responseMimeType: application/json` and a `responseSchema`. Is this unfair
to the naive arm? No. The naive arm gets the same kind of support through tool schemas, which
are strict JSON schemas too, so neither arm receives unstructured-parsing help the other lacks.

**OpenAI recovery decision (§3): temperature 0.2, top_p 1.0.** Each scenario runs once (§3:
"1 run"), so the reader will treat one transcript as representative of that model. Slightly
lower variance makes that single sample less of an outlier draw. It does not *force* a
choice: at 0.2 the model still picks between check_status, retry, escalate and avoid by
itself, as §3 requires. I've stayed above 0.0 so as not to overfit a single greedy path.
Gemini stays at 1.0 for the reason above. So the two families use different nominal
temperatures, each set to the provider's recommended behavior. Both values are recorded and
disclosed.

**§4 affected-cell reruns: send no sampling params** (G1's `None` path). §4 says rerun "at
original models/repetition counts", and the original rows used provider defaults. Changing
temperature there would make the rerun cells incomparable to the preserved cells they sit
next to. This is the one place where "record exact settings" means recording
`provider-default (unset)` truthfully.

## 3. Context and prompt settings

**System prompt structure (all roles).**
1. The fixed role line. For §3/§4 that is the existing `SYSTEM_PROMPT` ("Complete the task
   safely; escalate if you cannot establish a safe continuation."), unchanged. The ground
   rules say "no per-condition prompt tuning", and the §4 reruns must match the originals.
2. Real tool schemas, passed through the provider's native `tools`/`functionDeclarations`
   field and generated from `AtomicTool` by the existing converters. Don't paste them into
   prose. Hash each schema set (sha256 of the canonical JSON) into the run record (§1).
3. For §3, the user turn is the *real* `build_mid_run_fallback` payload (`{"task": ...,
   "procedure_failure": ...}`), and it must contain no status dict. Status can only be learned
   by calling `check_status`, which reads persisted Frappe state (§3 "no prefilled status
   dict").
4. §5 naive: `task_text(customers)` only. §5 Procedure interpretation: the same
   `task_text(customers)` plus the binding schema. Both arms see identical task information.
5. No hints about the expected outcome, no examples of "correct" recovery, and no wording
   that differs by condition, arm or family.
6. Every run record carries `graph_provenance: hand-authored` for the Procedure arm (§5),
   and `prompt_sha256` covering the system prompt and user payload (§1).

**History.** Carry the full provider-native transcript forward with no summarization and no
truncation. The largest scenario (§3 S3, at most 10 turns) stays around 20-30k tokens, far
inside both models' context windows. Summarizing would add a hidden model-authored step,
which is an extra uncounted call or a lossy harness rewrite. It could also drop an operation
id and violate §3's "operation identity/recovery constraints preserved across failure ->
recovery". Gemini `thoughtSignature`s must be echoed verbatim on every replayed
`functionCall` part, as the harness already does. OpenAI assistant messages must carry all
`tool_calls` ids, each followed by its `tool` message (G2).

**Caching.** Use implicit caching only. OpenAI applies automatic prefix caching to prompts
of 1024 tokens or more, and it cannot be disabled. Gemini implicit caching is on by default.
Do **not** add explicit `cachedContents` for Gemini: it adds storage fees and a TTL the cost
table doesn't model, and the savings are tiny at this scale. For accounting, both providers
report cached tokens as a **subset** of prompt/input tokens (`cachedContentTokenCount`,
`prompt_tokens_details.cached_tokens`). `compute_model_step_cost_usd` already bills
`(prompt - cached) * input + cached * cached_input`. Keep that formula, and keep
`input_tokens` in tables as the provider's total. **Never** report `input + cached` as the
input total, or add a separate "cached" column into a token sum. That is the exact
double-count §4 is repairing, and the canonical script (T3) should assert
`cached <= input` for every row. Because caching is implicit and can't be controlled, cached
counts will vary between otherwise identical runs. Report them, and don't use them as
evidence of arm efficiency.

## 4. Turn and call budgets

**(a) §5 naive arm: 40 tool calls, 25 model calls per instance.**
The task per invoice is: list overdue invoices, check for an existing ToDo, create one if
missing, and record the outcome. That is about 1 list call per customer plus about 3 calls
per invoice, plus a final status. Instance 5 has two customers. With the current seed data
that's a few invoices, so a careful serial agent needs about 16-20 tool calls. 40 gives
roughly 2x headroom for re-reads and verification calls a cautious model might add. §5 says
"large enough for valid completion" and "same execution budget". The Procedure arm is
capped by the same 40-tool-call / 25-model-call budget, though it uses far less, so the cap
never binds it. The current `MAX_TOOL_CALLS = 20` is too tight for instance 5 and would turn
a slow-but-correct model into a budget failure. Reaching the cap is recorded as
`budget-caused`, never as `model-incorrect`. Parallel calls returned in one response count
individually toward the tool-call cap and as one model call.

**Procedure arm repair: 1 extra interpretation call** on a missing or malformed binding.
It is logged as `repair`, its cost is included, and it gets the validation error text as
feedback. If the repair also fails, the instance is recorded as a failure (§5). This is
never a ground-truth fallback (G6).

**(b) §3 HUF integration: model-turn budgets tied to the minimum safe path.**
The minimum safe path is the number of model turns a correct, cautious model needs. Each
budget is roughly 2x that minimum, rounded up, so escalating or avoiding is always
affordable.

| Scenario | Minimum safe path (model turns) | Budget |
|---|---|---|
| S1 committed, response lost | check_status -> sees COMMITTED -> final/no-retry (2-3) | **6** |
| S2 did not commit, ambiguous timeout | check_status -> NOT_COMMITTED -> permitted retry -> confirm -> final (4) | **8** |
| S3 late commit after inconclusive read | check_status -> UNKNOWN -> wait/escalate or fence -> re-check after drain -> final (4-5) | **10** |
| S4 pre-dispatch rejection, then permitted retry | read rejection -> check_status -> retry -> confirm -> final (4) | **8** |
| S5 permission denied, including recovery write | attempt_action -> denied -> (optional recovery write, denied) -> escalate (3) | **6** |

There is a cap of 12 tool calls per scenario across all turns. §3 requires a drain/release
of pending ops before the final state check. That step belongs to the harness and does not
count against the model's budget. Reaching the budget is reported as a result
(`max_turns_exhausted`), never rerun (§3 "do not rerun selectively").

## 5. Determinism and reproducibility

- **OpenAI:** send `seed: 20260923`. OpenAI documents it as best-effort only. Record the
  returned `system_fingerprint` for each call. A fingerprint change between calls is a
  disclosed source of non-determinism.
- **Gemini:** send `generationConfig.seed: 20260923`. It is also best-effort; with thinking
  and temperature 1.0, outputs are not reproducible. Record `modelVersion` for each response
  (already captured as `last_model_version`).
- **Neither provider guarantees determinism.** State this in the paper. Non-determinism is
  handled by what §3/§5 already require: one fixed run per cell, every run reported, no
  selective reruns, and raw transcripts retained. It is **not** handled by adding
  repetitions, which §7 forbids ("stop adding experiments").
- **Record for each call:** requested model id, returned model version/fingerprint, the full
  request-params dict (G1), tool-schema hash, prompt hash, seed, `finish_reason`, all token
  fields (input, cached, output, reasoning), wall-clock time, retry count, UTC timestamp, and
  HUF commit SHA.
- **§5 ordering:** alternate which arm goes first per instance (odd instances Procedure
  first, even instances naive first), as §5 requires. The current driver always runs
  Procedure first (`procedure_vs_naive.py` ~861).
- **Transport retries** (429/5xx/URLError, at most 3 with backoff) are logged per call, and
  the cost of any partial response is included. A call that still fails after retries is a
  `harness` failure row, never silently resampled.

## 6. Cost and latency

Prices come from the harness table: flash-lite $0.30 in / $0.03 cached / $2.50 out;
4o-mini $0.15 / $0.075 / $0.60 per 1M tokens.

| Block | Calls | Est. tokens per run (in / out incl. thinking) | Gemini | OpenAI |
|---|---|---|---|---|
| §5 naive, 5 instances | about 10-25 model calls each, growing context | about 60-150k / 4-10k | $0.03-0.07 per instance, about $0.35 | about $0.015-0.03 per instance, about $0.12 |
| §5 Procedure, 5 instances | 2-3 calls each | about 3k / 1k | about $0.004 each, about $0.02 | about $0.01 total |
| §3 integration, 5 scenarios | up to 10 turns each | about 20-40k / 2-5k | about $0.02 each, about $0.10 | about $0.04 |
| §4 affected-cell reruns | original counts | as originals | historically below $1 | |
| **Typical total** | | | | **about $0.9** |
| **Worst case (every run hits its cap; Gemini flash gate fires at about 4x flash-lite price)** | | | | **about $2.1** |

Both totals fit under the $5 hard `RunningCostCeiling`, which aborts rather than overruns.
The flash-gate estimate uses an *assumed* price. Before using it, fetch the real price
(G7) and recompute. **Where I chose correctness over cost:** full-history context instead of
summarization, 40/25 naive budgets instead of 20, per-scenario §3 budgets instead of 4, one
repair call on the Procedure arm, and explicit seeds and recording on every call. Together
these add maybe $0.3 in the worst case. **Where cost matters:** flash-lite and 4o-mini
instead of larger models, no explicit Gemini cache objects, and no extra repetitions.
Latency isn't optimized, but it is measured (§5). The 60 s per-call timeout plus 3 retries
bounds a stuck call at about 4 minutes, and that case is logged as harness latency rather
than model latency.
