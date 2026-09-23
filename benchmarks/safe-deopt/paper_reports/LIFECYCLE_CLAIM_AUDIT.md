# Lifecycle Claim Audit -- T7 (ACCEPTANCE_PLAN_V2.md Sec.6)

Task: "Keep lifecycle claims within the measurements" -- the discarded model-generated plan
is plan-generation cost, not compilation cost. Either measure the real trace-to-proposal and
verification path, or leave lifecycle break-even unmeasured and omit numerical break-even
claims entirely. Report human review effort separately if available. Never substitute direct
Frappe execution time for discovery/compilation/verification cost.

## 1. What "compilation cost" actually measures

Code evidence, `benchmarks/safe-deopt/procedure_vs_naive.py` (worktree
`/Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf`,
branch `research/safe-deopt-v2-integration`):

```
641: """One real model call with no tools -- used for the Procedure arm's compile /
665: def compile_procedure(model_id: str, ceiling: RunningCostCeiling) -> tuple[dict, ModelCallRecord]:
666:     """One-time compilation-cost measurement: shown the task + the six tool schemas, asked
670:     own output -- I8) -- this call's tokens are what is charged as the one-time compile cost,
683:     text, record = _one_shot_model_call(model_id, system, user, "compile", ceiling)
961: # compile_procedure() model output (that call, when it runs at all, is logged
962: # separately as one-time "compilation"/plan-generation cost -- see run_experiment).
```

`compile_procedure()` is a single discarded, no-tools model call ("shown the task + the six
tool schemas, asked [to plan]"). Its output is never fed to `execute_procedure` -- the
executed graph is hand-authored (`extra.graph_provenance == "hand-authored"`, confirmed in
`REPORT_PROCEDURE_VS_NAIVE_V2.md` Sec.2 row 5d). The module's own docstring at line 37 states
this plainly:

```
37: Procedure version (this is a stand-in for ``propose_procedure_from_run`` mining an
```

and `REPORT_PROCEDURE_VS_NAIVE.md` line 95-100 (original v1) says it explicitly:

> "a stand-in for `propose_procedure_from_run`'s mining cost (that function needs a
> *completed* Agent Run to mine from, which is circular for a 'first-ever compilation'
> measurement; the real mining path is exercised structurally, not re-measured...)"

**Conclusion: "compilation cost" in both `REPORT_PROCEDURE_VS_NAIVE.md` and
`REPORT_PROCEDURE_VS_NAIVE_V2.md` is the cost of one discarded plan-generation model call, not
the cost of the real trace-to-Procedure-proposal-and-verification path.** `propose_procedure_
from_run` (or an equivalent verification pass) is never invoked in this dataset. This matches
the plan's own expected finding verbatim.

## 2. Can `propose_procedure_from_run` be cheaply invoked against a real completed Agent Run?

Not cheaply. `huf/ai/procedure_proposal.py` (the real mining/proposal module) imports
`frappe` at module scope. `REPORT.md` line 262 and `benchmarks/safe-deopt/README.md`
("(e) `n.py` timing could not be measured") both record that this import fails in the
sandbox that produced this dataset -- no frappe/bench was available -- and
`results/breakeven.json`'s `n_timing_seconds` field is `null` for exactly this reason. Running
it for real requires a live Frappe bench with a completed Agent Run to mine from (mining is
inherently post-hoc: it needs an already-executed run as its input, which is circular for a
"first compilation" measurement) plus the verification pass on top. This is real, non-trivial
infra, not a quick fix.

Per the plan's own framing ("not a blocker for a paper reporting steady-state execution +
recovery behavior"), this audit does **not** build that infra and does **not** invoke
`propose_procedure_from_run` against a live bench. The task per Sec.6 is instead to reframe
every numerical break-even/lifecycle-savings claim into a steady-state-only claim with an
explicit "lifecycle break-even not measured" caveat.

## 3. Human review effort

No human-review-effort data exists anywhere in the project. `REPORT_PROCEDURE_VS_NAIVE.md`
line 100 and line 183 both already say so explicitly ("This number does NOT include the human
review step's own cost/latency, which was explicitly out of scope"; "does not include the
human-review latency/cost of accepting a Procedure proposal, which is real and unmeasured
here"). `grep -rn` across the whole track directory and the benchmark code for
"human review"/"review effort"/"review cost" found no measured figure anywhere -- only these
disclosures that it is absent. **Stated plainly: human review effort is unmeasured. No
estimate is given here or should be given anywhere in these reports.**

## 4. Synthetic timing trace -- still synthetic, correctly labeled?

Two distinct "timing" artifacts exist and must not be conflated:

- **`compile_procedure()`'s one discarded model call** (Sec.1 above) -- this is a *real* API
  call (real tokens, real wall time, real dollar cost, `real_accounting: true`), but it
  measures plan-generation, not compilation/verification. It is honestly labeled as
  "compilation cost" only in the narrow code sense of "the cost of the call `compile_procedure`
  makes" -- but the reports built numerical break-even claims on it as if it were amortizing a
  full discovery/compile/verify lifecycle cost, which Sec.6 disallows.
- **`compute_breakeven()`'s N\* sweep in `run_experiment.py`** (~line 1806) -- this is fully
  synthetic: it runs only over `MockedModel` rows (`tokens_are_real_accounting == False`),
  explicitly excludes real rows from its wall-time means, and its own docstring says "these are
  illustrative only, since MockedModel executes near-instantly and does not reflect real LLM
  latency." `results/breakeven.json` self-labels its output "PILOT / MOCKED -- illustrative
  methodology demonstration only, not a real cost claim" and its `n_timing_seconds` /
  `procedure_proposal_timing_seconds` fields are `null` (never fabricated). This is already
  correctly labeled everywhere it is cited: `analysis_percondition_costs.md`'s "Break-even:
  PROVISIONAL" section, `REPORT.md` lines 434-438 and 262-263, and `benchmarks/safe-deopt/
  README.md` item (e).

**No report substitutes direct Frappe execution time for discovery/compilation/verification
cost.** The one place Frappe execution timing is measured (REPORT.md line 51's "compiled/
direct-write path (avg 3.90s...)" on the live `safe-deopt-verify` bench) is real Frappe
*write-path* latency for the recovery integration scenarios (Sec.3 of the plan), a different
measurement from compile/verify cost, and is not conflated with it in that report.

**The one problem found**: `REPORT_PROCEDURE_VS_NAIVE.md`'s Sec.5 ("Compilation amortization")
and `REPORT.md`'s summary of it treat the real-but-mislabeled plan-generation cost from item 1
as if it were a full lifecycle compile+verify cost, and compute a numerical break-even
("recovered in well under one repetition", "far faster than the speculative plan's ...
2 to 5 repetitions") from it. This is the violation Sec.6 targets. `REPORT_PROCEDURE_VS_NAIVE_
V2.md` (the current, non-superseded report) does **not** repeat this error -- it reports the
compilation-cost table (Sec.4.1) without deriving any break-even/amortization claim from it.

## 5. Itemized break-even / lifecycle-savings claims and reframes

| # | File | Current text (quoted) | Reframe |
|---|---|---|---|
| 1 | `REPORT_PROCEDURE_VS_NAIVE.md` (superseded original) | "**Compilation amortization**: at gemini-3.5-flash-lite's numbers, the naive arm's average per-instance cost premium over the Procedure arm is about $0.00398; the one-time compile cost ($0.00095) is recovered in well under one repetition. At gpt-4o-mini's numbers, the premium is about $0.00159 per instance against a $0.00032 compile cost — also recovered in under one repetition. **This break-even is far faster than the speculative plan's pre-registered prediction of "2 to 5 repetitions"** (section 7, prediction 5) — which the plan itself said would mean "the experiment confirmed nothing new" if it landed inside that band. It landed outside (below) that band instead, which is a genuine, not-pre-ordained finding this run surfaced." | Keep the historical numbers (per ACCEPTANCE_PLAN_V2.md's "kept, not deleted" rule for superseded artifacts) but immediately follow the claim with a correcting caveat. See exact edit applied below. |
| 2 | `REPORT_PROCEDURE_VS_NAIVE.md` (superseded original) | "The 'break-even landed below the pre-registered 2-5 repetition band' statement is a single-sample observation, not a statistically established result." | Add: this is additionally not a lifecycle break-even at all -- see caveat below; retain sentence otherwise since it is already a legitimate scoping caveat about sample size, just not about the mislabeling. |
| 3 | `REPORT.md` | "Compile cost recovered in under one repetition in this sample." | Reframe to a steady-state-only claim with an explicit lifecycle caveat. |
| 4 | `analysis_percondition_costs.md` (superseded original) | Already correctly framed ("Break-even: PROVISIONAL" section, explicit non-measurement). No numerical break-even claim is asserted as real. Adding only a forward pointer to this audit for traceability. | Add one-line pointer to `LIFECYCLE_CLAIM_AUDIT.md`. |
| 5 | `analysis_percondition_costs_v2.md` | Contains no break-even section at all (silently dropped vs v1). Not itself a violation, but leaves a reader unable to find why. | Add a short "Lifecycle / break-even" section pointing to this audit and stating the status explicitly, so the v2 doc doesn't read as having simply forgotten the topic. |
| 6 | `REPORT_PROCEDURE_VS_NAIVE_V2.md` | No numerical break-even/amortization claim present (Sec.4.1 reports compilation cost as a bare table, Sec.7's conclusion makes no amortization claim). No edit required for a violation; add one clarifying sentence next to the compilation-cost table so it cannot be read as lifecycle cost. | Add one sentence after the Sec.4.1 table. |

## 6. Files edited

- `REPORT_PROCEDURE_VS_NAIVE.md`
- `REPORT.md`
- `analysis_percondition_costs.md`
- `analysis_percondition_costs_v2.md`
- `REPORT_PROCEDURE_VS_NAIVE_V2.md`

No code files were touched. No bench commands were run. `propose_procedure_from_run` was not
invoked against a live bench.
