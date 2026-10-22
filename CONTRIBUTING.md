# Contributing

This page covers how to run tests, where new files belong, and how commits are written. Every command below is taken from a CI workflow, a package script, the verify script, or the pre-commit config. The source for each is listed at the end.

## 1. Running tests

### Backend (Frappe bench)

Backend tests run through Frappe's test runner against a bench with `huf` installed.

```bash
bench --site <site> run-tests --app huf                              # whole app
bench --site <site> run-tests --app huf --module <dotted.module>     # one module
```

Example: `bench --site test_site run-tests --app huf --module huf.ai.tests.test_flow_eval_security`.

`./scripts/huf-verify.sh backend` wraps the same command. It auto-detects a running bench through `docker exec` (see `HUF_BENCH_CONTAINER`, `HUF_BENCH_SITE`, `HUF_BENCH_PATH`) and parses the unittest summary, because `bench run-tests` can exit 0 on failures.

### Frontend (`frontend/`)

Install once with `npm ci` inside `frontend/`. Then:

```bash
npm run typecheck    # tsc --noEmit against tsconfig.app.json
npm run test         # Vitest, runs src/**/*.test.ts and src/**/*.test.tsx
npm run build        # tsc -b, vite build, copy HTML entry
```

`./scripts/huf-verify.sh quick` runs typecheck, unit tests and design parity. `./scripts/huf-verify.sh frontend` adds the production build.

### Playwright (`frontend/`)

```bash
npm run test:e2e                                  # mocked/offline suite (excludes e2e/deployed)
npm run test:e2e:nightly                          # nightly config (scheduled 02:00 UTC)
npm run test:e2e:deployed -- e2e/deployed/chat.spec.ts   # real site, needs BASE_URL or E2E_BASE_URL
```

- The mocked suite runs in `e2e-tests.yml` on PRs into `develop` that touch `frontend/**`. It mocks `/api/**` at the network layer.
- The deployed suite runs against a live site. Its one spec makes a real, billed LLM call, so it is manual-only (`workflow_dispatch`) and never a release gate. Set `BASE_URL` or `E2E_BASE_URL` to the site.
- `./scripts/huf-verify.sh e2e` runs the fast mocked subset.

### Pre-commit

```bash
pre-commit run --all-files
```

Hooks include ruff (import sort, lint, format), prettier, eslint, file checks, `check-explicit-frappe-commits`, and `check-repo-layout`. Run `python3 scripts/check_repo_layout.py` directly to check the layout guard on its own.

## 2. Where things go

| What | Where | Notes |
|---|---|---|
| Product code (backend) | `huf/` (e.g. `huf/ai/`, `huf/huf/doctype/<doctype>/`) | Keep product modules free of `test_` in the name. |
| Feature tests, library code under `huf/ai/` | `<package>/tests/test_<name>.py` (co-located, e.g. `huf/ai/decision/tests/`) | Test-only helpers do not go here. |
| Feature tests, DocType | `test_<doctype>.py` directly in the DocType folder (e.g. `huf/huf/doctype/flow_definition/test_flow_definition_schema.py`) | Same folder as the controller. |
| Test infrastructure (fakes, factories, helpers) | `huf/testing/` (planned, created in a later change) | Never name these files `test_*`. |
| Fixtures | Next to the tests that use them, in a `fixtures/` folder under that tests package | Do not put fixtures in `docs/`. |
| Docs | `docs/` | Repo-level entry points stay at the root (`AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`). |
| Scripts | `scripts/` | Includes `huf-verify.sh` and the layout guard. |
| Frontend unit tests | Co-located `*.test.ts` / `*.test.tsx` next to the source in `frontend/src/` | Picked up by `npm run test`. |
| End-to-end tests | `frontend/e2e/` (`e2e/deployed/` for live-site specs) | Run with the Playwright scripts above. |

## 3. Naming rule

Only real tests start with `test_`. Frappe's runner collects every `test_*.py` file, so a product module, helper or fixture with that prefix gets imported as a test. Name helpers for what they do (`fakes.py`, `factories.py`), not as tests.

## 4. Conftest files

`bench run-tests` ignores `conftest.py`. The conftests in this repo (for example `huf/ai/tests/conftest.py`, `huf/ai/decision/tests/conftest.py`, `huf/huf/doctype/flow_definition/conftest.py`) are plain pytest shims. They mock `frappe` in `sys.modules` so that the module can be imported without a bench. Do not move these files or merge them into one global `huf/conftest.py`, because a global file would fake `frappe` for every test in the app.

## 5. Workspace rule

Plans, findings, progress notes, logs, and spike or probe scripts never go in this repo. `scripts/check_repo_layout.py` blocks them in pre-commit and in the Repo layout CI check. Keep them in the workspace track (`workspace/Tracks/<Track>/`).

## 6. Commits

Use conventional commit style (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`). Attribution lines are not needed.

## Sources

- `.github/workflows/server-tests.yml`: `bench --site test_site run-tests --app huf`
- `.github/workflows/frontend-tests.yml`: `npm ci`, `npm run typecheck`, `npm run test`, `npm run build` (working directory `frontend`)
- `.github/workflows/e2e-tests.yml`: `npm run test:e2e` (mocked suite)
- `.github/workflows/nightly-e2e.yml`: `npm run test:e2e:nightly`, cron `0 2 * * *`
- `.github/workflows/live-llm-e2e.yml`: `npm run test:e2e:deployed -- e2e/deployed/chat.spec.ts`, `workflow_dispatch` only
- `.github/workflows/repo-layout.yml`: `python3 scripts/check_repo_layout.py`
- `frontend/package.json`: `typecheck`, `test`, `build`, `test:e2e`, `test:e2e:nightly`, `test:e2e:deployed` script definitions
- `frontend/vitest.config.ts`: `include: ['src/**/*.test.ts', 'src/**/*.test.tsx']`
- `frontend/playwright.deployed.config.ts`: `BASE_URL` / `E2E_BASE_URL` override
- `scripts/huf-verify.sh`: `run-tests --app huf --module '$module'`, `run-tests --app huf`, target names (`quick`, `frontend`, `backend`, `e2e`), `HUF_BENCH_*` variables
- `docs/testing/VERIFY_ENTRY_POINT.md`: `./scripts/huf-verify.sh <target>` targets and bench discovery
- `.pre-commit-config.yaml`: hook list, `check-repo-layout` entry (`python3 scripts/check_repo_layout.py`)
- `CLAUDE.md`: `pre-commit run --all-files`
- `docs/testing/CI_TIERS.md`: `pre-commit run --all-files`; deployed suite is manual-only
