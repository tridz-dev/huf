# C4+G vs C6, matched cases -- v2 (regenerated from canonical_scoring.py)

Supersedes analysis_c4g_vs_c6.md, which compared C4+G and C6 aggregates without matching
on seed/fault/guarantee/model cell and inferred equivalence from overlapping confidence
intervals. That reasoning is invalid per ACCEPTANCE_PLAN_V2.md Sec.4/Sec.7 and is not
repeated here. This document reports only the matched-cell comparison the canonical script
actually computes.

## Commands run

```
cd benchmarks/safe-deopt
python3 canonical_scoring.py --input results/runs.jsonl --output results/scored_v2
```

Input: results/runs.jsonl (3600 rows, the original Gemini + OpenAI dataset). Output used
here: results/scored_v2/matched_c4g_vs_c6.json.

class_counts: {"invalid": 288, "live-model": 3312} -- see RECOVERY_RESULTS_RECONCILED.md
for the full row-classification breakdown. No legitimate-no-model or mock rows exist in
runs.jsonl.

## Matched-cell result (raw script output)

n_matched_cells = 648 (cells present in both C4+G and C6 for the same
seed/fault/tool_guarantee/workload/model). **This includes 72 F4 rows (36 per condition) --
see "F4 inclusion" below for why that is a problem and the corrected, F4-excluded numbers.**

| metric | C4+G mean | C6 mean | observed diff (C4+G - C6) | bootstrap 95% CI |
|---|---|---|---|---|
| useful_completion | 0.5 | 0.5 | 0.0 | [-0.0540, +0.0556] |
| escalated | 0.8765 | 0.8673 | +0.00926 | [-0.0278, +0.0463] |
| total_tokens | 1223.72 | 2102.27 | -878.55 | [-952.87, -802.95] |
| cost_usd | 0.0005417 | 0.0007902 | -0.0002485 | [-0.0002828, -0.0002145] |
| wall_time_seconds | 4.5225 | 5.3233 | -0.8008 | [-1.0755, -0.5418] |

## Reading these, honestly -- corrected per FINAL_ADVERSARIAL_REVIEW_V2.md C3

**The superseded framing of this document ("useful_completion is genuinely tied at 0.5 vs
0.5 ... H1 holds") is withdrawn. That claim is vacuous, not merely tied, and is corrected
below.**

Broken down by fault type within each condition (re-derived directly from
`scored_v2/scored_rows.jsonl`, live-model rows only, C4+G and C6):

| fault | C4+G useful_completion | C6 useful_completion |
|---|---|---|
| F1 | 0/36 | 0/36 |
| F2 | 144/144 | 144/144 |
| F3 | 0/144 | 0/144 |
| F4 | 36/36 | 36/36 |
| F6 | 144/144 | 144/144 |
| F7 | 0/144 | 0/144 |

**useful_completion is a pure function of `fault`, identical in both conditions for every
fault type.** F2/F4/F6 always score 100% completion and F1/F3/F7 always score 0%,
regardless of which condition (C4+G or C6) ran the cell. Per T2's own finding (Contract #2),
F2 and F3 are caller-indistinguishable at the moment of retry, yet split 100%/0% -- proof
that this column reads ground-truth commit state baked in by the fault injector, not
anything the model or the guard did. The "0.5 vs 0.5" match is therefore not a finding about
C4+G matching C6 on correctness; it is the row count arithmetic of a 50/50 split between
always-completes faults (F2/F4/F6) and never-completes faults (F1/F3/F7), restated in both
conditions because both conditions ran the identical fault mix. **H1 ("structured handoff
achieves correctness within 5-10% of C6") is Unsupported by this metric, not Supported** --
useful_completion carries no C4+G-vs-C6 model-recovery signal to test H1 against.

What DOES differentiate the two conditions, from the same matched-cell table:

- **escalated**: +0.93pp observed (C4+G escalates slightly more), CI crosses zero
  ([-0.0278, +0.0463]) -- genuinely indistinguishable from noise at this sample size.
- **total_tokens, cost_usd, wall_time_seconds all show a real, CI-excludes-zero reduction
  for C4+G vs C6**: roughly 42% fewer tokens, 31% lower cost, 15% less wall time per matched
  cell, every CI bound on the same side of zero. This is the one place the matched
  comparison does carry real signal distinguishing the two conditions, and it survives
  removing F4 from the matched set (see below) with materially the same magnitude.

## F4 inclusion (FINAL_ADVERSARIAL_REVIEW_V2.md C3 / H1)

The 648-cell matched set above includes 72 F4 rows (36 per condition), despite F4 being
excluded elsewhere in this project from valid-guarantee conclusions as `robustness_only`
(EXCLUSIONS_AND_FAILURES.md ss1: F4's injector has a confirmed "commit-then-fabricate" gap
-- it commits the write for real, then always reports a fabricated validation failure to
the caller, regardless of whether the underlying store validated). Re-running the matched
comparison with F4 rows excluded (n = 612+612 = 1224 rows, 576 fewer matched cells):

| metric | C4+G mean (no F4) | C6 mean (no F4) | diff |
|---|---|---|---|
| useful_completion | 0.4706 | 0.4706 | 0.0 |
| escalated | 0.8693 | 0.8595 | +0.0098 |
| total_tokens | 1249.09 | 2136.37 | -887.28 |
| cost_usd | 0.0005518 | 0.0008019 | -0.0002501 |
| wall_time_seconds | 4.6056 | 5.4066 | -0.8010 |

Every finding above is unchanged in direction and magnitude with F4 excluded: the
useful_completion tie is still exact (still vacuous, for the same reason -- F4's removal
doesn't change that F2/F6 always complete and F1/F3/F7 never do), and the token/cost/latency
reduction for C4+G persists almost identically. **Decision: F4 is excluded from the matched
C4+G-vs-C6 comparison going forward** (this document's own headline table above is
retained for the audit trail, but the F4-excluded table is the one to cite). This matches
the treatment F4 already gets everywhere else in this project (robustness_only, excluded
from guarantee conclusions) and resolves the review's H1/C3 finding that F4 rows were
inconsistently included here while being excluded elsewhere. At the time this section was
written, no rerun of F4 had been performed. **That rerun has since been done -- see below.**

## F4 rerun 2026-09-23

`_inject_f4`'s commit-then-fabricate bug (fixed in commit `8c5466504`) is now fixed, and the
180 affected rows in `results/runs.jsonl` (72 of them in the C4+G/C6 matched set) were
regenerated against live models via `benchmarks/safe-deopt/rerun_f4_cells.py` (real cost:
$0.0645; see EXCLUSIONS_AND_FAILURES.md ss1 for the full accounting). `canonical_scoring.py`
was rerun on the corrected `results/runs.jsonl` to produce a fresh `results/scored_v2/*`.

Matched-cell result, F4 now correctly included (`results/scored_v2/matched_c4g_vs_c6.json`,
n_matched_cells = 636 -- 12 fewer than the old buggy 648, because 12-per-condition
`W2-nonidempotent` F4 cells are now honestly zero-cost/no-model-call and correctly
quarantined rather than fabricated-into-looking-like a live-model row):

| metric | C4+G mean | C6 mean | observed diff (C4+G - C6) | bootstrap 95% CI |
|---|---|---|---|---|
| useful_completion | 0.4906 | 0.4906 | 0.0 | [-0.0550, +0.0550] |
| escalated | 0.8742 | 0.8648 | +0.00943 | [-0.0283, +0.0472] |
| total_tokens | 1231.72 | 2102.40 | -870.69 | [-947.75, -794.22] |
| cost_usd | 0.0005450 | 0.0007904 | -0.0002454 | [-0.0002811, -0.0002106] |
| wall_time_seconds | 4.5302 | 5.3039 | -0.7737 | [-1.0594, -0.5057] |

Compared to the F4-excluded table below (n=612, unchanged by this rerun since it never
touched F4), every metric moves only slightly with F4 correctly included: useful_completion
0.4906 vs 0.4706 (both still an exact tie between conditions -- the fault-determined
bookkeeping conclusion below is unaffected), escalated +0.94pp vs +0.98pp (still
indistinguishable from noise), and the token/cost/latency reduction for C4+G persists at
materially the same magnitude (-41.4% tokens / -31.0% cost / -14.6% wall time here, vs
-41.5%/-31.2%/-14.8% F4-excluded). **No headline finding changes**: C4+G remains measurably
cheaper and faster than C6 with a CI that excludes zero, and useful_completion remains a
pure function of fault type carrying no C4+G-vs-C6 signal, in both the F4-included and
F4-excluded views. Per H1's own stated options, F4 is now included going forward since it
was fixed and honestly rerun rather than dropped.

## What changed vs the superseded analysis

analysis_c4g_vs_c6.md argued C4+G and C6 were "equivalent" on cost/token grounds using
unmatched aggregates and CI overlap. The matched-cell numbers here show C4+G is measurably
cheaper and faster than C6 (a real, CI-excludes-zero effect, not merely indistinguishable);
that part of the substantive conclusion survives. The useful_completion "match" this
document previously read as evidence of correctness equivalence is corrected here to
Unsupported: it is fault-determined bookkeeping, not a comparison of model or guard
behavior, and does not support H1 in either direction.

## Scope caveat

This reflects runs.jsonl only (Gemini gemini-3.5-flash-lite and OpenAI
gpt-4o-mini-2024-07-18 families, 720 rows per condition, 288 rows quarantined
project-wide as zero-token/no-transcript -- see RECOVERY_RESULTS_RECONCILED.md). It does
not incorporate T4's small 5-scenario integration harness results
(results/llm_recovery_integration_v2.jsonl), which are a separate, much smaller dataset
against a real HUF/Frappe backend and are not matched-cell comparable with this table.
