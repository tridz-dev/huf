# Pinned Integration Checkout — Safe Deoptimization Experiment (T1)

Status: **produced 2026-09-23**, per ACCEPTANCE_PLAN_V2.md §1 ("Freeze and identify the
implementation"). This document records the exact commits, environment, and verification
state of the single pinned local integration checkout that combines the benchmark code with
the real runtime changes from PR #751 and PR #753.

## Integration checkout

| Field | Value |
|---|---|
| Location | `/Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf` |
| Branch | `research/safe-deopt-v2-integration` |
| Final HEAD SHA | `89918b202` (was `3aadf7e9a` prior to 2026-09-23 harness sync) |
| Base | `research/safe-deopt-experiment` tip, unmodified up to that point |
| Pushed anywhere | No |
| Merged into develop/pre-develop/etc. | No |

## 2026-09-23 harness/scoring sync

Cherry-picked two additional commits from `research/safe-deopt-experiment` on top of the
prior integration HEAD `3aadf7e9a`, needed so upcoming T4/T6 reruns have both the pinned
guard/fallback runtime code and the fixed harness/scoring script:

| Order | SHA | Message |
|---|---|---|
| 1 | `8912921f3` (from `a2dfad615`) | Add deterministic guarantee-contract tests for safe-deopt (T2) |
| 2 | `89918b202` (from `14a55c675`) | safe-deopt: fix harness tool-call/token/sampling gaps, add canonical scoring |

`git log --oneline 5a5ad72a2..14a55c675` on `research/safe-deopt-experiment` showed only these
two commits as new since the integration branch's fork point — everything else in that range
was already incorporated. Both cherry-picks applied with **zero conflicts** (no overlap with
the PR #751/#753 runtime wiring). New integration HEAD: `89918b20295ec062416648361748eaa7805cc72c`.

Verification: `python3 -m pytest benchmarks/safe-deopt/tests/ -q` in the integration worktree
→ **233 passed, 1 skipped, 4 subtests passed**, no failures.

Not pushed, not merged into any key branch; committed locally to
`research/safe-deopt-v2-integration` only.

This branch exists only as a local worktree branch. The three source worktrees
(`safe-deopt-experiment`, `fallback-committed-writes-semantics`, `safe-deopt-guard-wiring`)
were not modified; the integration worktree was created fresh from
`research/safe-deopt-experiment`'s tip and PR commits were cherry-picked into it.

## Source SHAs

| Source | Branch | Tip SHA | Role |
|---|---|---|---|
| Benchmark base | `research/safe-deopt-experiment` | `5a5ad72a2` | Base of integration branch (verbatim, no cherry-pick) |
| PR #751 | `fix/fallback-committed-writes-semantics` | `8f27658a5` | `gh pr view 751` headRefOid; state OPEN; base `pre-develop` |
| PR #753 | `feat/procedure-replay-guard` | `77289ba73` | `gh pr view 753` headRefOid; state OPEN; base `pre-develop` |

Both PR branches share a common ancestor at `43b69a0c6` (merge of PR #747,
`fix/view-option`), confirmed by `git log --oneline 43b69a0c6..HEAD` on each source
worktree showing only that branch's own commits.

## Commits cherry-picked

Cherry-picked in order, PR #751 first, then PR #753 (per plan step 3). All four cherry-picks
applied **cleanly, with zero conflicts** — no manual resolution was needed at any step.

| Order | Source SHA | New SHA on integration branch | Message |
|---|---|---|---|
| 1 | `8f27658a5` (PR #751, sole commit) | `712d5130e` | fix(fallback): clarify that committed_writes lists attempted, not confirmed, writes |
| 2 | `a3358b9c6` (PR #753, commit 1/4) | `3665bd38d` | feat(procedure-runtime): add recovery_guarantee tool field and standalone replay guard module (stage 1-2, inert) |
| 3 | `bbe506845` (PR #753, commit 2/4) | `643af27aa` | feat(procedure-runtime): wire opt-in replay guard into the write-retry path |
| 4 | `a53df54cd` (PR #753, commit 3/4) | `7840f8732` | docs(procedure-runtime): clarify v1 scope of recovery_guarantee options |
| 5 | `77289ba73` (PR #753, commit 4/4) | `3aadf7e9a` | feat(procedure-runtime): wire status_resolvable/fenceable via optional status_check_fn/fence_fn hooks |

PR #753's four commits were applied as the contiguous range `a3358b9c6^..77289ba73` via a
single `git cherry-pick`, in their original order.

## Files touched (verified present in the integration checkout)

- `huf/ai/graph/fallback.py` — `committed_writes` docstring/semantics clarification (PR #751).
- `huf/ai/graph/replay_guard.py` — new standalone replay guard module (PR #753).
- `huf/ai/graph/procedure_runtime.py` — wiring of the replay guard into the write-retry path
  and `status_check_fn`/`fence_fn` hooks (PR #753).
- `huf/ai/graph/permissions.py` — supporting permission changes (PR #753).
- `huf/huf/doctype/agent_tool_function/agent_tool_function.json` — `recovery_guarantee`
  Select field (`server_idempotent` / `status_resolvable` / `fenceable` / `none`) confirmed
  present at lines 28 and 87-91 of the integrated file.
- `huf/ai/tests/test_replay_guard.py`, `huf/ai/tests/test_replay_guard_wiring.py` — new test
  files added by PR #753.

No conflicts arose between the benchmark branch's own history and the two PR diffs; the
benchmark branch (`research/safe-deopt-experiment`) does not appear to carry a benchmark-only
copy of `fallback.py`, `replay_guard.py`, or `procedure_runtime.py` that would collide with
the real runtime files, so step 4 of the plan (conflict escalation) was not triggered.

All three files (`fallback.py`, `replay_guard.py`, `procedure_runtime.py`) pass
`python3 -m py_compile` in the integrated checkout with no syntax errors.

## Model / settings metadata (from TEST_AGENT_SETTINGS.md, config design, not yet executed)

| Role | Model |
|---|---|
| Primary (fast/cheap) | `gemini-3.5-flash-lite` |
| Secondary OpenAI | `gpt-4o-mini` |
| Escalation (gated, pre-registered deviation only) | `gemini-3.5-flash` |

These are recorded here as the settings this checkout is intended to be exercised under for
§3/§4/§5 reruns; no paid model runs were executed as part of this T1 task.

## Dependency versions

| Item | Value |
|---|---|
| Host `python3 --version` | `Python 3.14.7` (Homebrew, `/opt/homebrew/bin/python3`) |
| `pytest` on host | `9.1.1` |
| `frappe` importable from host python3 | **No** — `ModuleNotFoundError: No module named 'frappe'`. The host Python is not a bench environment; huf/pyproject.toml notes frappe is "installed and managed by bench" only. |
| huf `pyproject.toml` pin, `litellm` | `>=1.74.7,!=1.82.7,!=1.82.8,<1.83.8` (upper-bounded below 1.83.8 because from that version litellm's PyPI metadata restricts installs to Python <3.14; ceiling documented in-repo as pending litellm's own Python 3.14 support) |
| `python_requires` (huf) | `>=3.10` |
| `benchmarks/safe-deopt/requirements.txt` or `pyproject.toml` | Not present as a separate file — benchmark code runs inside the huf app's own dependency set |

## Test suite run results

**Verification gap closed (2026-09-23).** Ran the real bench-dependent suites inside an actual
Frappe bench, plus the frappe-free benchmark suite directly on the host. Both real, not guessed.

### Bench used

| Field | Value |
|---|---|
| Bench name | `safe-deopt-verify` (pre-existing disposable bench, found healthy — not re-provisioned) |
| Host container | `frappe_docker_devcontainer-frappe-1` |
| Bench path (in container) | `/workspace/development/safe-deopt-verify` |
| Site | `safe-deopt-verify.local` |
| Webserver port | `8107` (internal to container; not published on host — verified via `bench run-tests` from inside the container, not curl) |
| Registry status | `ready`; processes (`frappe serve`, `watch`, `schedule`, `worker`) confirmed running via `ps aux` before use |

### Git sync into the bench's `apps/huf` checkout

The bench's `apps/huf` was a separate checkout (`origin` = `/workspace/development/.sources/huf.git`,
a bare mirror bind-mounted from the host at `/Users/safwan/Code/Docker/frappe_docker/development/.sources/huf.git`).
The container only mounts `/Users/safwan/Code/Docker/frappe_docker`, not `/Users/safwan/Code/Huf`,
so the integration worktree was not directly reachable from inside the container.

1. From the integration worktree (`.../worktrees/safe-deopt-v2-integration/huf`), pushed the branch
   to the bare mirror using its pre-existing `bench-sources` remote:
   `git push bench-sources research/safe-deopt-v2-integration` — succeeded, new branch created.
2. Inside the bench's `apps/huf` checkout: `git fetch origin research/safe-deopt-v2-integration`,
   then `git checkout -B research/safe-deopt-v2-integration FETCH_HEAD`.
3. The checkout initially had leftover **untracked** files from prior manual test runs on this bench
   (`benchmarks/safe-deopt/_replay_guard_standalone.py`, `bench_scripts/`, a results jsonl, and
   transcript JSON files) that collided with paths the target branch tracks. These were untracked,
   not uncommitted changes to tracked files, so no WIP commit was needed — they were moved (not
   deleted) to `tmp_checks/pre_sync_untracked_backup/` inside the bench directory, preserving them.
4. Result: `git status` clean, checkout succeeded.

| | SHA | Branch |
|---|---|---|
| From | `2caa25178` | `research/safe-deopt-experiment` (bench's previous state) |
| To | `3aadf7e9a3460e46468213e11f41f00423ec2f16` | `research/safe-deopt-v2-integration` (matches the pinned integration HEAD above) |

No `docker cp` was used at any point — sync was git fetch + checkout only, per project convention.

### Bench-dependent suites (`bench --site safe-deopt-verify.local run-tests --app huf --module <path>`)

Testing was disabled on the site by default; enabled once via
`bench --site safe-deopt-verify.local set-config allow_tests true`, then all four modules run:

| Module | Result |
|---|---|
| `huf.ai.tests.test_replay_guard` | **25 passed**, 0 failed |
| `huf.ai.tests.test_replay_guard_wiring` | **25 passed**, 0 failed |
| `huf.ai.tests.test_fallback` | **16 passed**, 0 failed |
| `huf.ai.tests.test_procedure_fallback_wiring` | **12 passed**, 0 failed |

No failures, no errors, no skips in any of the four modules.

### Frappe-free benchmark suite (plain pytest, host, no bench needed)

Run directly in the integration worktree: `python3 -m pytest benchmarks/safe-deopt/tests/ -v`
(same worktree, HEAD `3aadf7e9a`, host Python — this suite does not import `huf`/`frappe`):

**193 passed, 1 skipped, 4 subtests passed** (12 test files: `test_authority.py`,
`test_blocked_retries.py`, `test_conditions.py`, `test_faults.py`, `test_live_api_model_gemini.py`,
`test_live_api_model_openai.py`, `test_live_model_wiring.py`, `test_real_procedure_integration.py`,
`test_recovery_harness.py`, `test_run_experiment.py`, `test_run_experiment_cli_flags.py`,
`test_unsafe_retry_scoring.py`, `test_workload_w3.py`, `test_workloads.py`). No failures.

### Bench-specific notes carried over

- `BENCH_IDENTITY.md` was still not present at the bench root (same gotcha noted in
  `BENCH_VERIFICATION.md` from provisioning time) — not written by this task either, to avoid
  fabricating provenance the provisioning script itself should own.
- The bench was left running and was **not torn down** — it may still be useful for further
  poking at this integration branch. Per project convention, teardown requires explicit
  confirmation first.

## How to resume / re-verify

1. `cd /Users/safwan/Code/Huf/workspace/worktrees/safe-deopt-v2-integration/huf`
2. `git log --oneline -8` should show HEAD `3aadf7e9a` with the five commits listed above on
   top of `5a5ad72a2` (`research/safe-deopt-experiment` tip).
3. The `safe-deopt-verify` bench's `apps/huf` is already synced to this exact SHA (see above) —
   rerun with `bench --site safe-deopt-verify.local run-tests --app huf --module
   huf.ai.tests.test_replay_guard` (and the three sibling modules) from inside
   `frappe_docker_devcontainer-frappe-1`. `allow_tests` is already enabled on that site.
4. For the frappe-free benchmark suite, `python3 -m pytest benchmarks/safe-deopt/tests/` from the
   worktree needs no bench.
5. Do not push, merge, or delete the `research/safe-deopt-v2-integration` branch on `origin`
   (tridz-dev/huf) or any key branch; it is local-only per ACCEPTANCE_PLAN_V2.md §7's stopping
   rule. The push in step 1 above went only to the local bare mirror used for bench sync, not to
   `tridz-dev/huf` or `esafwan/huf`.
