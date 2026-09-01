# CI Tier Map

This document maps the CI system that actually exists in this repo today onto the
4-tier model from `GOAL.md` §19 (CI architecture). It is a map, not a spec — every
row cites a real file. Where GOAL.md asks for something that has no workflow or
script backing it yet, that is called out explicitly as a **GAP** rather than
implied to be covered.

Sources read in full for this document: `.github/workflows/server-tests.yml`,
`frontend-tests.yml`, `e2e-tests.yml`, `failure-analysis.yml`, `deploy-huf.yml`,
`fasterdocker-publish.yml`, `.pre-commit-config.yaml`, `.semgrep.yml`,
`frontend/playwright.config.ts`, `frontend/playwright.deployed.config.ts`,
`frontend/package.json`, `frontend/scripts/check-design-parity.mjs`.

(As of this writing there is no `.github/workflows/nightly-e2e.yml` in the repo.
Cross-browser/nightly E2E is a separate, in-flight work-stream — not documented
here as existing, and not something this document invents.)

---

## Tier 0 — local/pre-commit / coding-agent loop

**GOAL.md asks for:** changed-file lint, TypeScript where relevant, affected
Vitest, affected Python/unit tests, design parity on changed files. Target: fast
feedback (seconds).

**What actually exists:** `.pre-commit-config.yaml`, wired to run on
`pre-commit` (i.e. only against staged/changed files, via the pre-commit
framework's own diff mechanism):

| Hook | Tool | Scope |
|---|---|---|
| `trailing-whitespace`, `check-merge-conflict`, `check-ast`, `check-json`, `check-toml`, `check-yaml`, `debug-statements` | pre-commit-hooks v5.0.0 | changed files |
| `ruff` (import sort `--select=I --fix`), `ruff` (lint), `ruff-format` | astral-sh/ruff-pre-commit v0.8.1 | changed Python files |
| `prettier` | mirrors-prettier v2.7.1 | changed `.js/.vue/.scss` |
| `eslint --quiet` | mirrors-eslint v8.44.0 | changed `.js` |
| `check-explicit-frappe-commits` | local script (`scripts/check_explicit_commits.py`) | changed `huf/**/*.py` |

This genuinely covers **changed-file lint** for both Python and JS (ruff +
ESLint + Prettier), and is fast.

**GAP — not covered by anything runnable today:**
- **TypeScript**: no hook runs `tsc`. `pre-commit`'s eslint mirror hook only
  lints `.js`, not `.ts`/`.tsx` (see the `types_or: [javascript]` restriction
  in both the prettier and eslint hook blocks) — TypeScript files are not
  type-checked, or even linted, at the pre-commit stage.
- **Affected Vitest**: no hook, script, or `pre-commit` entry runs `vitest`
  against changed files. `frontend/package.json`'s `"test"` script
  (`vitest run --config vitest.config.ts`) runs the whole suite and is invoked
  only by `frontend-tests.yml` (Tier 1), not locally/pre-commit.
- **Affected Python/unit tests**: `bench --site test_site run-tests --app huf`
  (the only backend test runner that exists — see Tier 1 below) runs the
  entire app's test suite; there is no local mechanism to run just the tests
  affected by a changed file, and it requires a full bench (MariaDB, Redis,
  a built site) that does not exist as a lightweight local check.
- **Design parity on changed files**: `frontend/scripts/check-design-parity.mjs`
  exists and supports `--strict`/`--all` flags (checked its source directly),
  but has no "only scan files changed vs. a base ref" mode — it walks
  `frontend/src` wholesale every run — and no CI workflow invokes it at all
  (see the Tier 1 gap below). It is not wired into pre-commit either.

**Verdict: Tier 0 is real but partial.** Lint (Python + a subset of JS) is a
genuine fast local loop via `pre-commit run --all-files` / on `git commit`.
TypeScript, affected-Vitest, affected-Python-tests, and changed-file design
parity do not exist as fast local checks — see "Tier-0 gap decision" below for
what this task did about it.

---

## Tier 1 — every PR

**GOAL.md asks for:** frontend lint, frontend typecheck, frontend unit tests,
frontend build, design parity, backend tests, API contracts for P0/P1, security
static checks, mocked Playwright, critical full-stack Playwright, critical
accessibility, selected visual regression.

| Requirement | Real file / job | Trigger | Status |
|---|---|---|---|
| Frontend lint | *(none in CI)* | — | **GAP** — `npm run lint` (`eslint .`, `frontend/package.json:9`) is never invoked by any workflow. Only `pre-commit`'s eslint mirror (JS-only) touches lint, and only locally. |
| Frontend typecheck | `frontend-tests.yml` job `frontend`, step "Typecheck" (`.github/workflows/frontend-tests.yml:40-41`, `npm run typecheck` → `tsc --noEmit -p tsconfig.app.json`) | PR/push to `develop`, paths `frontend/**` | Covered |
| Frontend unit tests | same job, step "Unit tests" (`frontend-tests.yml:43-44`, `npm run test` → `vitest run`) | same | Covered |
| Frontend build | same job, step "Build" (`frontend-tests.yml:46-47`, `npm run build`) | same | Covered |
| Design parity | *(none in CI)* | — | **GAP** — `npm run check:design` / `check:design:strict` (`frontend/package.json:10-11`) is defined but not called from `frontend-tests.yml` or any other workflow. |
| Backend tests | `server-tests.yml` job `backend` (`.github/workflows/server-tests.yml`, full `bench init` → `bench new-site` → `bench --site test_site run-tests --app huf`, lines 71-106) | PR/push to `develop` | Covered |
| API contracts P0/P1 | Same backend job — contract suites live as ordinary Python tests under `huf/ai/tests/test_http_contract_agent_p0.py` and `huf/ai/tests/test_http_contract_automation_tool_p0.py`, executed by the same `run-tests --app huf` call, so they run inside `server-tests.yml` | same | Covered, but only implicitly — there is no separate named job/step that isolates or reports P0/P1 contract status; a P0 contract failure looks identical to any other backend test failure in the workflow UI. |
| Security static checks | *(none in CI)* | — | **GAP, and the most significant one found.** `.semgrep.yml` exists at repo root with real rules (e.g. `huf-no-explicit-frappe-commit`), but no workflow file anywhere under `.github/workflows/` invokes `semgrep`. There is also no CodeQL workflow, no `dependency-review` action, and no `pip-audit`/frontend audit step in any workflow. Every "security static checks" item GOAL.md lists for Tier 1 is unimplemented as CI. |
| Mocked Playwright | `e2e-tests.yml` job `e2e` (`.github/workflows/e2e-tests.yml`, `npm run test:e2e` → `playwright test` using `frontend/playwright.config.ts`, `testDir: './e2e'`) | PR/push to `develop`, paths `frontend/**` | Covered |
| Critical full-stack Playwright (against a real backend, not mocked) | *(none in CI)* | — | **GAP, intentionally.** `e2e-tests.yml`'s own title is "E2E Tests (offline)" and its only suite is the mocked/offline one. `frontend/playwright.deployed.config.ts` (`testDir: './e2e/deployed'`, with an `auth.setup.ts` project) + `test:e2e:deployed` run against a real instance and DO now have a workflow (`live-llm-e2e.yml`), but it is manual-only by design — see Tier 3 below — since the one live spec in that suite makes a real, billed LLM call. |
| Critical accessibility | Bundled into `e2e-tests.yml`'s `npm run test:e2e` run — `frontend/e2e/accessibility.spec.ts` uses `@axe-core/playwright`'s `AxeBuilder` and lives in the same `testDir` (`./e2e`) that `playwright.config.ts` matches via `testMatch: /\.spec\.ts$/`, so it executes as part of the same Playwright invocation, just with no dedicated job name calling it out | same as mocked Playwright | Covered, implicitly (same caveat as API contracts: a failure here surfaces generically as an `e2e-tests.yml` failure, not as an "accessibility" failure). |
| Selected visual regression | Same mechanism — `frontend/e2e/visual-regression.spec.ts` (+ its `visual-regression.spec.ts-snapshots/` baseline directory) is picked up by the same `playwright test` run in `e2e-tests.yml` | same | Covered, implicitly, same caveat. |

**Verdict:** Tier 1 is real for typecheck/unit/build/backend/mocked-Playwright,
but has three concrete holes: frontend lint is never run in CI at all, design
parity is never run in CI at all, and security static checks (Semgrep despite
a ready-to-use `.semgrep.yml`, CodeQL, dependency review, secret scanning) do
not exist as CI jobs anywhere in this repo.

---

## Tier 2 — `develop` / nightly

**GOAL.md asks for:** all backend, all full-stack E2E, all golden Agent traces,
expanded automation/time cases, cross-browser, larger security/property/fuzz
testing, dependency audits, migration/install, provider compatibility, optional
mutation testing.

**What actually exists:** Nothing dedicated. `server-tests.yml` and
`frontend-tests.yml` both trigger on `push: branches: [develop]` as well as PR
(`server-tests.yml:4-7`, `frontend-tests.yml:3-13`) — so "backend" and
"frontend" tests do re-run on every merge to `develop`, but that is the *same*
job as Tier 1, not an expanded nightly variant (no separate cross-browser
matrix, no larger security/fuzz pass, no scheduled/`cron` trigger anywhere in
`.github/workflows/`).

**Update (post prompt-cache-auto-mode merge):** `.github/workflows/nightly-e2e.yml`
now exists — scheduled (`cron: "0 2 * * *"`) plus manual `workflow_dispatch`,
running the mocked/offline suite across Chromium+Firefox+WebKit (`npm run
test:e2e:nightly` → `playwright.nightly.config.ts`). This covers the
cross-browser bullet only; it is still the same mocked/offline suite as
Tier 1, not an expanded nightly pass.

**GAP (remaining).** No migration/install pipeline (GOAL.md §18's `new bench
→ new site → install → migrate → seed → smoke` sequence), scheduled
dependency audit, or mutation testing exists in this repo's CI today.

---

## Tier 3 — release/deployment

**GOAL.md asks for:** clean install, migrate, build, production-like smoke,
critical browser flows, security gates.

**What actually exists, read closely, with line citations:**

- **`deploy-huf.yml`** (37 lines total): triggers on `push: branches: [pre-develop, develop]`
  (lines 3-10). Its only job, `deploy` (lines 13-37), does two things: configure
  SSH (lines 17-27), then SSH into a fixed host and run
  `/home/ubuntu/deploy-huf.sh '${GITHUB_REF_NAME}' '${GITHUB_SHA}'` (lines
  29-37). **There is no `needs:`, no `workflow_run` trigger on another
  workflow's success, and no test/build step in this file at all.** It deploys
  unconditionally on every push to `develop`/`pre-develop`, independent of
  whether `server-tests.yml` or `frontend-tests.yml` passed or even finished.
  Everything downstream (clean install, migrate, smoke) is delegated to
  `deploy-huf.sh` on the remote host, which is outside this repo and was not
  read as part of this task (it lives on the deploy target, not in
  `.github/workflows/`).
- **`fasterdocker-publish.yml`** (163 lines): triggers on `push: branches:
  [develop]` and `push: tags: ['v*']`, or manual `workflow_dispatch` (lines
  3-14). Same shape: it builds a native runtime image, bakes a site, builds and
  pushes a per-arch demo image (`build` job, lines 24-116), then assembles and
  pushes a multi-arch manifest (`manifest` job, lines 118-163). **No `needs:`
  referencing `server-tests.yml`/`frontend-tests.yml`, no `workflow_run` gate,
  no test step of any kind** — it builds Docker images and pushes them to
  `ghcr.io` purely off the same `push: develop` trigger frontend/server tests
  also use, as a fully independent, ungated workflow.

**Finding, stated precisely:** neither of the two workflows that touch
release/deployment gates on tests passing first. Both trigger off the same
raw `push` to `develop` that `server-tests.yml`/`frontend-tests.yml` use, as
separate, uncoordinated workflows with no dependency edge between them. GitHub
Actions gives all three workflows the same trigger and runs them in parallel —
a red `server-tests.yml`/`frontend-tests.yml` run does not block
`deploy-huf.yml` or `fasterdocker-publish.yml` from deploying/publishing on
that same commit. This is a real gap against GOAL.md §19 Tier 3's implicit
requirement that release/deployment gates on the earlier tiers, and against
§18's requirement that migration/install and critical-smoke be *proven* before
release — as far as this repo's CI is concerned, nothing proves it; that proof
(if it happens) happens only inside the untracked `deploy-huf.sh` on the
remote host.

Separately: `frontend/playwright.deployed.config.ts` + `frontend/e2e/deployed/`
+ the `test:e2e:deployed` npm script look purpose-built for exactly the
"production-like smoke, critical browser flows" GOAL.md asks Tier 3 to cover.
**Update:** `.github/workflows/live-llm-e2e.yml` now invokes
`test:e2e:deployed` — but deliberately only via manual `workflow_dispatch`
against a `base_url` input, never on `push`/`pull_request`. This is
intentional, not a partial fix: `deployed/chat.spec.ts`'s
`new-chat-gets-a-real-reply` test makes a real, billed call to a live
external LLM and is inherently rate-limit/latency-flaky by nature of that
(GOAL.md §29's "avoid live external LLM dependencies in authoritative PR
CI" / §4's "real-provider compatibility should exist as a separate
optional/nightly suite"), so it is opt-in-on-demand rather than gated into
any automatic trigger. It still is not wired into `deploy-huf.yml` as an
actual release gate — that remains the gap this section describes.

**No security gates** (the GOAL.md Tier 3 bullet) exist in either workflow —
consistent with the Tier 1 finding that no Semgrep/CodeQL/dependency-review
workflow exists in this repo at all yet.

---

## Tier-0 gap decision: documented, not built

This task considered adding a `scripts/verify-changed.sh` fast-loop script
(diff against a base ref, run affected Vitest/typecheck/design-parity/ruff on
changed files only) as instructed. Decision: **document the gap, do not build
the script**, for a concrete reason found during this audit rather than a
generic caution:

- `check-design-parity.mjs` has no changed-file mode to shell out to — it
  walks all of `frontend/src` every run (confirmed by reading the script:
  it derives its file list from `readdirSync`/`statSync` over `SRC`, not from
  a git diff). Building `verify-changed.sh` to call it "per changed file"
  would need either patching that script (out of scope: this task's brief was
  explicit not to touch existing enforced tooling's behavior) or reimplementing
  its per-file logic from outside, which risks drifting from the real checker
  and reporting false confidence.
- `tsc --noEmit -p tsconfig.app.json` and Vitest do not have a lightweight
  officially-supported "only these files" mode wired up in this repo either
  (no `vitest related`/`--changed` config, no incremental tsconfig split by
  path) — a naive `tsc`/`vitest` invocation scoped to a file list can silently
  miss type errors that only show up through import graphs, which is worse
  than an honest "this isn't fast yet" for a task whose only job is mapping
  reality, not shipping something fragile that looks like coverage.
- Backend "affected Python tests" requires a live bench (MariaDB + Redis + a
  built site) per `server-tests.yml` — there is no meaningfully fast local
  subset of that available without first solving a separate, larger problem
  (a persistent local bench for coding-agent loops), which is out of scope
  here.

Given the explicit instruction that half-building something fragile is worse
than naming the gap, this document is the deliverable for Tier 0's uncovered
items (TypeScript, affected Vitest, affected Python tests, changed-file design
parity). What already works locally and fast today, and should be used as-is:
`pre-commit run --all-files` (or its default staged-file behavior on
`git commit`) for changed-file lint/format across Python and JS.

---

## Summary table

| Tier | GOAL.md ask | Real backing today |
|---|---|---|
| 0 | changed-file lint, TS, affected Vitest, affected Python tests, changed-file design parity | Partial — `.pre-commit-config.yaml` covers lint/format only |
| 1 | lint, typecheck, unit, build, design parity, backend, API contracts, security static checks, mocked Playwright, full-stack Playwright, accessibility, visual regression | Partial — typecheck/unit/build/backend/mocked-Playwright/accessibility/visual-regression covered; lint, design parity, security static checks, and full-stack (non-mocked) Playwright are gaps |
| 2 | all backend, all E2E, golden traces, cross-browser, larger security, dependency audits, migration/install, provider compat, mutation testing | Partial — `nightly-e2e.yml` covers cross-browser (mocked/offline only); golden traces, larger security, dependency audits, migration/install, mutation testing remain gaps |
| 3 | clean install, migrate, build, production-like smoke, critical browser flows, security gates | Not gated as a release gate — `deploy-huf.yml`/`fasterdocker-publish.yml` still deploy/publish unconditionally on `push: develop`. `test:e2e:deployed` is now invoked, by `live-llm-e2e.yml`, but only via manual `workflow_dispatch` (opt-in, real-LLM smoke, never a release gate) |
