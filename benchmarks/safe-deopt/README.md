# Safe Deoptimization Experiment

## What this benchmark tests

This benchmark investigates whether a structured recovery handoff lets an agent safely take
over after a deterministic Procedure fails mid-run at a write, keeping most of the
Procedure's cost advantage while approaching the correctness of a full agent working from
scratch. Concretely, it asks: after a write's outcome is genuinely ambiguous (a timeout, an
inconclusive read, a late commit), does giving the recovering agent (a) an explicit
UNKNOWN/committed classification of that write and (b) a runtime replay guard that only
permits a retry when a declared tool guarantee (`server_idempotent`, `status_resolvable`,
`fenceable`) has actually been used, prevent duplicate and unsafe writes that a generic
"just retry" fallback allows? See `PREREGISTRATION.md` for the full design; in short, the
experiment tests four hypotheses:

- **H1**: structured handoff (C5/C6) achieves correctness within 5-10% of a full-agent
  ceiling (C1) at 30-50% of C1's token cost.
- **H2**: the C6 replay guard eliminates unsafe duplicate writes that C4/C5 (no guard)
  allow.
- **H3**: deterministic recovery alone (C3) suffices wherever idempotency or
  read-before-write already covers the fault, with the agent's marginal value concentrated
  in concurrent-actor drift (F4) and non-idempotent write variants.
- **H4**: no recovery path, including the agent, can escalate privilege beyond the original
  Procedure's authorization envelope.

The matrix crosses two workloads (W1: CRM follow-up; W2: payment allocation, plus a
non-idempotent W2 variant), eight fault types (F0-F7 from `faults.py`), four tool-guarantee
levels, and seven recovery conditions (C1-C6, `PREREGISTRATION.md` section 5) — evaluated
against ground-truth invariants in `invariants_safedeopt.py`, never against what a faulty
wrapper merely reports back to the caller.

## How to run it

```bash
# Deterministic pieces + mocked LLM-condition matrix (no API key needed):
bash run_all.sh

# Attempt a real LLM run once recovery_harness.LiveAPIModel is implemented:
MODEL=<model-id> ANTHROPIC_API_KEY=<key> bash run_all.sh

# Re-score/re-aggregate already-saved results without calling any model:
bash run_all.sh --replay
```

`run_all.sh` runs, in order: the deterministic authority sub-experiment
(`authority_experiment.py`, no model or API key involved at all), the full experiment matrix
(`run_experiment.py`, which itself always runs C2/C3 deterministically and only touches a
model for C1/C4/C4+G/C5/C6), and finally the test suite
(`python -m pytest benchmarks/safe-deopt/tests/ -v`), reporting pass/fail clearly at each
step.

If `MODEL` and either `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` are set, the script attempts a
real call through `recovery_harness.LiveAPIModel` before falling back to the mocked matrix.
As of this writing that call is expected to fail loudly with a clear `NotImplementedError`
pointing at `recovery_harness.py` — `LiveAPIModel` is a documented stub, not a real client
(see "Known limitations" below). The script does not swallow that failure: it prints the
error and marks the run as failed.

Without a model/key, every LLM condition runs against `recovery_harness.MockedModel`, a
deterministic scripted stand-in, and the script prints a banner making that explicit before
and during the run.

`--replay` skips both fault injection and any model call. It loads whatever rows already
exist in `results/runs.mock.jsonl` and/or `results/runs.jsonl`, and re-runs only the
aggregation step (`results/summary.csv`, `results/plots/`, `results/breakeven.json`) against
those rows — it never regenerates or re-scores individual runs from scratch. This is
implemented via a `--replay` flag on `run_experiment.py` itself
(`python run_experiment.py --replay`), added specifically to support this without disturbing
`run_experiment.py`'s existing `main()` behavior when the flag is absent.

## Expected runtime and cost

The deterministic/mocked path (`bash run_all.sh`, no `MODEL`/API key) is **near-instant**:
the full run — authority experiment, the 420-cell experiment matrix, and 84 pytest tests —
completes in well under one second of wall-clock time on this machine (observed total
around 0.4s end to end, dominated by Python interpreter startup rather than any actual
computation). `bash run_all.sh --replay` is comparably fast, since it does no fault
injection at all.

**A real 10-seed-per-cell LLM run's cost and runtime are UNKNOWN and are not estimated
here.** The mocked run's `tool_calls` and `wall_time_seconds` columns in
`results/summary.csv` are real counts of a real (but scripted, near-instantaneous) tool-call
loop — they are not proxies for real LLM latency or token cost, because `MockedModel` never
tokenizes anything and never calls a network endpoint. Extrapolating a dollar figure or
wall-clock estimate for a real model from these numbers would materially misrepresent real
LLM cost and is deliberately not done anywhere in this benchmark's outputs (`summary.csv`'s
`tokens_estimated` column is explicitly always `0` for every mocked row, and
`tokens_are_real_accounting` is `false` for all of them — see `run_experiment.py` and
`recovery_harness.py`'s module docstrings). A real estimate would require actually running
the real conditions against a real model and provider pricing, which is exactly the gap
`LiveAPIModel` currently blocks on.

## Known limitations

- **(a) Simulated in-memory stores, not a real ERPNext bench.** `workloads.py`'s `CrmStore`
  and `PaymentAllocationStore` are deliberately Frappe-free, in-memory Python objects with
  their own `commit_log` as ground truth — they do not exercise a real Frappe bench,
  MariaDB, or `huf.ai.graph.procedure_runtime`. A separate bench-level verification effort
  exists to check this benchmark's claims against a real bench; see
  `Tracks/SafeDeoptExperiment/BENCH_VERIFICATION.md` if that file exists in your checkout —
  this benchmark does not depend on it and does not block on its existence.
- **(b) All current results are from a `MockedModel`, not a real LLM.** Every row in
  `results/runs.mock.jsonl` and every number in `results/summary.csv` comes from a
  deterministic, scripted/rule-based stand-in for a language model (see
  `recovery_harness.MockedModel` and `run_experiment.py`'s module docstring), run at n=1
  seed per cell. This is a pilot pass per `PREREGISTRATION.md`'s "pilot run transparency"
  commitment: `summary.csv`'s confidence-interval columns are literally the string `"NA"`,
  not an estimate, and no result here should be read as a validated hypothesis.
  **Critically: `run_experiment.py`'s mocked policy for each condition (see `_naive_rule`
  vs. `_smart_rule`, and `trust_resolved_none` keyed on the condition name) is authored
  per-condition to reflect what H1/H2 predict a real model would do** — e.g. C4/C5's
  mocked policy is scripted to attempt an unsafe retry, and C6's is scripted to resolve a
  guarantee before retrying. Every C4-vs-C6 contrast visible in `summary.csv` and the plots
  is therefore **true by construction, not measured**: it demonstrates that the harness,
  the fault injection, and the C6 guard correctly produce the outcomes the hypotheses
  predict when a model behaves the scripted way — it is proof the machinery works, not
  evidence about how a real model actually behaves under these conditions. Only a real
  `LiveAPIModel` run can supply that evidence.
- **(c) `LiveAPIModel` is a stub, not implemented.** `recovery_harness.LiveAPIModel` reads
  `MODEL` from the environment but its `next_step()` deliberately raises
  `NotImplementedError` rather than fabricating a response or silently no-op-ing. Real LLM
  runs (C1/C4/C4+G/C5/C6 against an actual model) are not possible today without
  implementing a real API client and tool-use parsing there first.
- **(d) AppWorld tasks and multi-run mining are out of scope for v1**, per the original
  brief. This benchmark covers only the W1/W2 workloads and the fault/condition matrix
  defined in `PREREGISTRATION.md`.
- **(e) `procedure_proposal.py` timing could not be measured.** The break-even analysis in
  `results/breakeven.json` and `results/plots/breakeven.png` needed a timing figure for
  `huf/ai/procedure_proposal.py`, but that module imports `frappe` at module scope and this
  sandbox has no Frappe/bench installed, so it cannot run standalone here (see
  `run_experiment.py::compute_breakeven`, which records this honestly as
  `procedure_proposal_timing_seconds: null` rather than fabricating a number). The
  break-even numbers that are produced are a **methodology demonstration only** — they
  illustrate how a break-even repeat-count would be computed from measured costs, using the
  mocked run's own (near-instantaneous, non-representative) wall-clock times — not a real
  cost claim about Procedures versus full agents in production.
