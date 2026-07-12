# Huf Test Coverage Plan

This plan closes the gap between Huf's current test state and the conventions used by
`frappe`/`erpnext`/`hrms`, in priority order. Each phase is a separate PR (small, reviewable,
no drift smuggled into feature work). Full survey backing these numbers lives in the
`TestCoverage` track of the `workspace` planning repo (not part of this app repo).

> Note: `CLAUDE.md` in this repo currently references a `ci.yml` that runs backend tests on
> push to `develop` — as of this plan, no such workflow exists in `.github/workflows/` on any
> branch checked. That reference is stale; Phase 0 below adds the real thing.

## Current state (one line each)

- Backend: 23/47 doctypes have a test file; only 1 has real assertions. Deprecated `FrappeTestCase`. No fixtures, no bootstrap data, no `huf/tests/` package, no pytest config.
- Frontend: 3 unit test files, node-env only, no DOM/component testing possible.
- E2E: 3 Playwright specs (agents, chat, dashboard) — ahead of all three reference apps on e2e, but narrow.
- CI: zero workflows run tests.

## Phase 0 — Foundations (prerequisite for everything else)

**Backend**
- Add `huf/tests/__init__.py` package with a `HufTestSuite` base class (mirrors `ERPNextTestSuite` /
  `HRMSTestSuite` pattern: `unittest.TestCase` subclass, rollback teardown, `set_user`,
  `change_settings` context managers).
- Add a `BootStrapTestData`-equivalent that creates minimal `_Test`-prefixed master data huf
  doctypes commonly depend on (e.g. a default `AI Provider`/`AI Model`, a test `Agent`).
- Migrate the 21 empty stubs' base class from `FrappeTestCase` → `IntegrationTestCase` (v16
  convention) as part of giving them real bodies, not as a separate mechanical rename PR.
- No `pyproject.toml` pytest section needed — confirm `bench run-tests` / `bench
  run-parallel-tests` remain the execution path (matches all 3 reference apps); document this in
  `docs/TESTING_PLAN.md` so nobody adds a conflicting pytest config later.

**Frontend**
- Land the prior frontend-testing-plan 's Phase 1
  as-is: add `jsdom` + `@testing-library/{react,dom,jest-dom,user-event}` as devDeps, extend
  `vitest.config.ts` to include `*.test.tsx` with per-file `@vitest-environment jsdom`, fix the
  `NODE_ENV=production` footgun, land one exemplar (`video.test.tsx`, already written once).

**CI**
- Add `.github/workflows/server-tests.yml`: single mariadb service container (start small — no
  postgres/multi-shard matrix until backend test volume justifies it), `bench run-tests --app
  huf` (or `run-parallel-tests` once >20 min).
- Add `.github/workflows/frontend-tests.yml`: `npm run test` (vitest) + `npm run typecheck` +
  `vite build`.
- Do **not** add Playwright to CI yet (Phase 3) — it needs a live site, out of scope for Phase 0.

## Phase 1 — Backend doctype test backfill

Priority order (highest business risk / most-used first, per `huf/huf/doctype/`):
1. `agent`, `agent_chat`, `agent_conversation`, `agent_message`, `agent_run` — core chat/agent
   execution path.
2. `agent_tool_call`, `agent_tool_function`, `agent_trigger` — tool-calling correctness.
3. `mcp_server`, `mcp_server_tool`, `mcp_server_header` — MCP integration (currently 0 tests on
   the latter two).
4. `ai_provider`, `ai_model`, `openai_settings`, `groq_settings`, `elevenlabs_settings` —
   provider config validation.
5. Remaining 24 doctypes with **no test file at all** (full list:
   `flow_definition`, `flow_run`, `agent_tool`, `agent_role`, `knowledge_source`,
   `integration_*`, `huf_data_table`, etc.) — add at minimum a creation/validation test each.

For each: real assertions on required-field validation, at least one link-field relationship,
and any custom `validate`/`before_save` controller logic (read the controller `.py` first — do
not write blind CRUD tests).

## Phase 2 — Module-level backend tests

Extend the 4 existing substantive test files' pattern to sibling untested logic:
- `huf/ai/` — orchestration, context policy edge cases beyond `test_context_policy.py`.
- `huf/ai/knowledge/` — retrieval correctness beyond `test_tool.py`/`test_chroma_backend.py`.
- Any `flow_*` execution engine logic (currently untested — `flow_definition`/`flow_run` have no
  test files per Phase 1 item 5).

## Phase 3 — Frontend component backfill

Follow the prior frontend-testing-plan notes' Phase 2:
`Video`, `Image`, audio player, `ToolOutput` dispatch, `ChatMessage` render branches. ~303 `.tsx`
files exist with zero component coverage today — prioritize components with real
branching/conditional logic, not pure presentation.

## Phase 4 — E2E breadth

Current 3 specs cover agents-list→form, new-chat+history, dashboard+nav. Add:
- Agent tool-calling flow (create agent with MCP tool → run → verify tool call in transcript).
- Knowledge/RAG flow (upload knowledge source → query → verify retrieval in response).
- Settings flows (AI provider/model configuration).
- Error-path coverage (failed tool call, provider auth failure) — currently all specs are
  happy-path only.
- Once stable, wire into CI (`frontend-tests.yml` or a dedicated `e2e-tests.yml`) against a
  disposable bench — needs `DOCKER_BENCH.md` env, so this is the phase most likely to need
  environment work before it can run unattended.

## Explicitly out of scope

- Postgres test matrix (reference apps have it; Huf has no evidence of postgres usage — skip
  until there's a reason).
- Cypress (Frappe core uses it for `frappe/` itself, not relevant to an installed app like Huf,
  ERPNext/HRMS don't use it either).
- Rewriting the 4 already-substantive backend test files — they're fine as-is.

## Sequencing / PR boundaries

Each phase ships as its own PR against `feature/huf-design-system`, in order, each gated on the
previous merging (Phase 1+ needs Phase 0's base class; Phase 3 needs the jsdom infra). This
track's draft PR (`chore/test-coverage-plan`) carries only the plan doc + Phase 0 CI skeleton —
it is intentionally the *first*, smallest PR, not a container for all the work.
