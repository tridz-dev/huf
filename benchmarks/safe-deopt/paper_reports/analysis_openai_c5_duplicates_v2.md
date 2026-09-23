# OpenAI C5 duplicate-committed-effect cases -- v2, reassessed against T2's F4 exclusion

Supersedes analysis_openai_c5_duplicates.md. Regenerated from
results/scored_v2/scored_rows.jsonl (canonical_scoring.py output over runs.jsonl).

## Extraction

```
rows = scored_rows.jsonl rows where condition == "C5" and model_id.startswith("gpt-4o-mini")
       and duplicate_committed_effects > 0
```

14 rows found (matches the prior count). Full per-case listing (source_line, seed, fault,
tool_guarantee, duplicate_committed_effects):

| source_line | seed | fault | tool_guarantee | dup_count | unsafe_attempts | dispatched_unsafe_retries |
|---|---|---|---|---|---|---|
| 3445 | 42 | F2 | server_idempotent | 1 | 0 | 0 |
| 3446 | 43 | F2 | server_idempotent | 1 | 0 | 0 |
| 3447 | 42 | F2 | status_resolvable | 1 | 1 | 1 |
| 3448 | 43 | F2 | status_resolvable | 1 | 1 | 1 |
| 3451 | 42 | F2 | none | 1 | 1 | 1 |
| 3452 | 43 | F2 | none | 1 | 1 | 1 |
| 3461 | 42 | F4 | NA | 1 | 1 | 1 |
| 3462 | 43 | F4 | NA | 1 | 1 | 1 |
| 3465 | 42 | F6 | server_idempotent | 1 | 0 | 0 |
| 3466 | 43 | F6 | server_idempotent | 1 | 0 | 0 |
| 3467 | 42 | F6 | status_resolvable | 1 | 1 | 1 |
| 3468 | 43 | F6 | status_resolvable | 1 | 1 | 1 |
| 3471 | 42 | F6 | none | 1 | 1 | 1 |
| 3472 | 43 | F6 | none | 1 | 1 | 1 |

Aggregate check against results/scored_v2/per_condition_family.csv: C5/gpt-4o-mini row
reports duplicate_committed_effects_total = 14, consistent with this listing.

## Per-case reassessment against CONTRACT_TEST_RESULTS.md (T2)

T2's finding: only fault F4 (`FaultInjector._inject_f4`, "concurrent actor drift") has the
confirmed commit-then-fabricate gap, marked `robustness_only` and excluded from valid-
guarantee conclusions (ACCEPTANCE_PLAN_V2.md Sec.2). F2, F3, F6, F7's own mechanisms
("server idempotency", "status resolution", "fencing") were confirmed to HOLD by T2's
contract tests. Separately, C5 is *by design* the "no replay guard" condition (README.md:
"C6 replay guard eliminates unsafe duplicate writes that C4/C5 (no guard) allow" -- H2).
`tool_guarantee` on a C5 row records which guarantee class the cell is testing, not that
the guard is active in C5 -- C5 never invokes replay protection regardless of that field.

Per-case verdicts:

- **Rows 3461/3462 (fault F4, seed 42/43): fall under the F4 robustness_only exclusion.**
  These two are literally F4 rows -- the fault whose injector T2 confirmed commits for
  real and then fabricates a validation error on top, independent of any guarantee
  mechanism. Any duplicate-effect signal here is confounded by that known-broken injector
  path and must not be counted as a guarantee-contract finding. Per ACCEPTANCE_PLAN_V2
  Sec.2/Sec.7, exclude these 2 from valid-guarantee conclusions.
- **Remaining 12 rows (F2: 6 rows, F6: 6 rows): do NOT fall under the F4 exclusion** --
  F2 and F6 are not the fault T2 found broken; T2 confirmed F2's own mechanism ("commits
  for real and reports failure to the caller") and, by extension, F6/F7-class fencing and
  idempotency behavior hold. These 12 are genuine C5-condition duplicate effects, but they
  are the *expected* outcome of C5's design (no replay guard), not a violation of any
  guarantee C5 claims to provide, **except for the 4 rows below, which the tool's own
  declared guarantee (not C5's guard, which C5 never has) was supposed to prevent.**
  - **4 rows -- lines 3445, 3446 (F2, seeds 42/43) and 3465, 3466 (F6, seeds 42/43) --
    carry `tool_guarantee=server_idempotent` and ARE genuine unresolved violations.**
    `unsafe_attempts`/`dispatched_unsafe_retries` read 0 for these 4, but that is a
    property of how `run_experiment.py`'s `score_unsafe_retries` /
    `_admission_would_permit` classify the *attempt* (see "Scorer miscount" below), not
    evidence the attempt was safe. Verified directly against the transcript for line 3445
    (`results/transcripts/real_openai/C5/W2-nonidempotent/F2/server_idempotent/42.json`,
    entries 11-13): the model calls `submit_allocation_unsafe` a second time, the tool
    dispatches it (`"dispatched": True`), and it commits a real second `Allocation`
    (`ALLOC-UNSAFE-0003`) -- a duplicate. T2 contract #1 proved F2 commits *exactly once*
    on the injector's own first attempt, so this second commit cannot be "the fault's own
    double-commit shape" (the superseded framing of this v2 doc, corrected here); it is
    the `submit_allocation_unsafe` tool failing to honor its own declared
    `server_idempotent` guarantee when actually retried. Same shape for F6
    (lines 3465/3466, transcript families under `.../F6/server_idempotent/`). This
    matches FINAL_ADVERSARIAL_REVIEW_V2.md C2 exactly: **4 of 14, not 0 of 14.**
  - The other 8 rows (status_resolvable x4, none x4) carry `dispatched_unsafe_retries=1`
    and ARE the expected C5 (no-guard) behavior for a guarantee that does not promise
    idempotency on retry -- consistent with H2, not a violation of anything C5/those
    guarantees claim.

### Scorer miscount: `unsafe_attempts`/`dispatched_unsafe_retries` read 0 on the 4 violation rows

Traced to `run_experiment.py`'s `_admission_would_permit` (not `canonical_scoring.py`,
whose `dispatched_unsafe_retries = max(0, unsafe_attempts - blocked_attempts)` arithmetic
at `canonical_scoring.py:263` is correct given its inputs). `_admission_would_permit`
implements: `if ground_truth_committed: return tool_guarantee == "server_idempotent"` --
i.e. for a `server_idempotent` cell, ANY retry after a known commit is classified
"informationally safe to attempt" purely from the guarantee's own declaration, regardless
of whether the tool actually behaved idempotently. That is a defensible definition of
"informationally safe *given the declaration*" (the two metrics are intentionally kept
separate from `duplicate_committed_effects`, which does correctly read 1 for all 4 rows),
but it means `unsafe_attempts`/`dispatched_unsafe_retries` can never flag a
`server_idempotent` tool's own broken idempotency, by construction -- it will always read
0 for this failure mode no matter how many real duplicates the tool commits. This is not a
cleanly one-line fix: changing `_admission_would_permit` to also require the *outcome* be
safe would collapse the "declaration says this is fine" signal into the "it actually was
fine" signal, which `duplicate_committed_effects` already captures as its own column
(Sec.4's explicit separate-columns design). Left as a **documented known limitation**
rather than hacked: `unsafe_attempts`/`dispatched_unsafe_retries` should not be read as
"could this have caused a duplicate" for `server_idempotent` cells -- only
`duplicate_committed_effects` answers that. No code change made to
`run_experiment.py`/`canonical_scoring.py` for this; see canonical_scoring.py's top-of-file
note added below.

## 14 vs 12: reconciling the two counts seen across reports (added 2026-09-23)

A later read of `results/scored_v2/scored_rows.jsonl` reported **12**, not 14, duplicate
rows for this same `condition == "C5" and model_id.startswith("gpt-4o-mini") and
duplicate_committed_effects > 0` population, prompting an external reviewer to ask which
number is right. Both are right, for two different (and now both explicit) queries:

- **14** = the query as written above, with no filter on `row_class`.
- **12** = the same query with an additional `row_class == "live-model"` filter, which is
  the natural restriction for "duplicates among rows that actually made a real API call".

The difference is exactly the 2 rows already identified in this document as fault F4
(lines 3461/3462, seeds 42/43): before `canonical_scoring.py`'s classifier fix (see
`RECOVERY_RESULTS_RECONCILED.md` "Update 2026-09-23 (part 2)"), these 2 rows were
classified `invalid` (quarantined, lumped in with the unrelated 288-row bad population);
after the fix they are classified `legitimate-no-model` (a genuine, fault-detected
competing write short-circuits the attempt before any model dispatch, per
`_is_legitimate_f4_short_circuit`). Either way, a `row_class == "live-model"` filter
excludes them -- correctly, since neither classification is `live-model` and no API call
was made -- so **the 12-row count is unaffected by the classifier fix**; only the label
on those 2 rows changed (`invalid` -> `legitimate-no-model`), not their inclusion in any
API-cost aggregate. The 14-row total (ignoring `row_class` entirely) is also unaffected.

This is NOT "2 of the 14 disappeared" -- both rows are still present in
`scored_rows.jsonl` with `duplicate_committed_effects: 1`, still excluded from
valid-guarantee conclusions per the F4 `robustness_only` exclusion above, and now also
correctly reflected in the end-to-end task view (`end_to_end_per_condition_family.csv`)
as legitimate no-model executions rather than silently quarantined data.

## Bottom line

Of the 14: **2 are excluded** (lines 3461/3462, fault F4, seeds 42/43) from valid-guarantee
conclusions under T2's confirmed F4 robustness_only gap. Of the remaining 12: **8 are C5's
expected no-guard behavior** (status_resolvable/none guarantees, which promise nothing about
idempotent retries) and are not violations. **4 are genuine, unexplained declared-guarantee
violations** (lines 3445, 3446, 3465, 3466 -- all `tool_guarantee=server_idempotent`, model
`gpt-4o-mini-2024-07-18`, workload `W2-nonidempotent`, seeds 42/43, faults F2/F6): a tool
that declares itself server-idempotent produced a real second commit on retry, which its own
declared guarantee says cannot happen. **Corrected count: at most 8/14 explained as expected
no-guard behavior; 4/14 unexplained declared-guarantee violations; 2/14 F4-confounded** --
matching FINAL_ADVERSARIAL_REVIEW_V2.md's C2 finding exactly. The superseded "0 of 14
survive" claim in this document's earlier revision was wrong for these 4 rows and is hereby
withdrawn.
