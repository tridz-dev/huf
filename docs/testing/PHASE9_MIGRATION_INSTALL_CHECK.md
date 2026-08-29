# Phase 9 — Migration/Install Regression Check

Validates GOAL.md §18 ("Migration/install regressions") end-to-end against a
**brand-new, throwaway bench**, separate from the `regression-safety-e2e`
bench this track normally uses: new bench → new site → install HUF → migrate
→ seed expected defaults → start server → critical smoke.

This was a one-shot verification run. The bench (`regression-migration-check`)
was provisioned, checked, and torn down in the same session; it no longer
exists.

## Setup

- Host: `frappe_docker_devcontainer-frappe-1` container, via the
  `frappe-multihand` skill's `provision.sh` / `teardown.sh`
  (`/workspace/.mh-scripts/`).
- Bench name: `regression-migration-check`
- Site: `regression-migration-check.local`
- Ports: web 8091, socketio 9011, watcher 6798
- `--blank` data mode (empty site, no reference-bench restore)
- `BENCH_ROOT=/workspace/benches`, `DB_ROOT_PASSWORD` read from
  `frappe_docker_devcontainer-mariadb-1`'s `MYSQL_ROOT_PASSWORD` env var,
  `SIGNED_BY=claude`, `TASK_DESCRIPTION="Phase 9 migration/install regression
  check"`.
- App source: `/workspace/.sources-local/huf.git` (the same local bare
  mirror `regression-safety-e2e` uses).

### Branch caveat — read before trusting "same branch" framing

The task asked to test against `explore/regression-safety-e2e` directly, but
`git worktree add` refuses to check out a branch that's already checked out
elsewhere, and that branch is already checked out by the `regression-safety-e2e`
bench's own worktree. To avoid touching that bench, a local branch
`phase9-migcheck-verify` was force-created in the bare mirror pointing at the
exact same commit as `explore/regression-safety-e2e` at the time
(`efe4683f5009a42ed2df7f30aee269cfe7545b24`), used only for this run, and
deleted afterward.

**That commit is stale relative to the actual live branch work.** The
sibling `regression-safety-e2e` bench's own `apps/huf` checkout is at
`b6bf2063` — roughly 20 commits ahead of what the shared bare mirror
`/workspace/.sources-local/huf.git` has (`git log
origin/explore/regression-safety-e2e..HEAD` in that bench lists ~20 unpushed
commits, e.g. `2ca61a50 fix(frontend): add @testing-library/dom as an
explicit devDependency`, several e2e test fixes, a security audit commit,
etc.). This track's `worktrees/huf` (this doc's own location) is further
ahead still, at `4be65a77`. **The bare mirror this skill's provisioning
depends on has not been kept in sync with the live branch checkouts** — that
is itself worth flagging to whoever owns this track's tooling, independent of
anything found below.

Net effect: this run validated install/migrate/seed behavior against an
~20-commits-stale snapshot of the branch, not the tip. Commands below are
exact; findings are scoped accordingly.

## Commands run (exact)

```bash
# Provision
docker exec -e BENCH_ROOT=/workspace/benches -e DB_ROOT_PASSWORD=123 \
  -e SIGNED_BY=claude -e TASK_DESCRIPTION="Phase 9 migration/install regression check" \
  frappe_docker_devcontainer-frappe-1 bash -lc '
    /workspace/.mh-scripts/provision.sh \
      --name regression-migration-check \
      --branch phase9-migcheck-verify \
      --track-dir /workspace/benches/.tracks/regression-migration-check \
      --app huf \
      --source-repo /workspace/.sources-local/huf.git \
      --blank'

# Explicit migrate (idempotency check, second pass over what install already ran)
bench --site regression-migration-check.local migrate

# Frontend build + start + smoke
cd apps/huf/frontend && yarn install --ignore-engines && yarn build   # (see finding below)
bench build --app huf
nohup bench start > logs/bench-start.log 2>&1 &
curl http://127.0.0.1:8091/api/method/ping
curl http://127.0.0.1:8091/huf/                       # app shell, expect 200
curl http://127.0.0.1:8091<bundle-path-from-shell>     # JS bundle, expect 200

# Teardown
docker exec -e BENCH_ROOT=/workspace/benches -e DB_ROOT_PASSWORD=123 \
  frappe_docker_devcontainer-frappe-1 bash -lc \
  '/workspace/.mh-scripts/teardown.sh --name regression-migration-check'
```

## Results

| Check | Result | Notes |
|---|---|---|
| Clean install (`bench new-site` + `install-app huf`, via provision.sh) | **PASS** | Completed with no errors; `provision.sh` reported `Provision complete`. |
| `bench migrate` idempotency (explicit second pass) | **PASS** | Ran clean, no errors/tracebacks; `after_migrate` hooks executed and completed. |
| Seeded system Agent(s) present | **PASS** | `Agent` doctype table exists; `Hub Orchestrator` and `Demo Assistant` agent records present after install, as expected from `huf/install.py::create_hub_orchestrator_agent()`. |
| Seeded Huf Roles / Frappe Roles present | **PASS** | `Huf Role` docs for Admin/Manager/User/Viewer all present with `is_system_role=1`; backing `Role` records `Huf Manager`, `Huf User`, `Huf Viewer` exist; Administrator has a `Huf User Role` row with `huf_role="Huf Admin"`, exactly matching `create_huf_roles()`. |
| Tool discovery (`Agent Tool Function` records) | **PASS** | 134 `Agent Tool Function` records present after fresh install (image generation, OCR, audio, flow, memory, and Frappe Cloud (`fc_*`) tools all appear). |
| AI Provider / AI Model seed data | **PASS** (bonus, not explicitly requested) | 11 `AI Provider` records, 157 `AI Model` records, matching `create_demo_ai_providers()` / `create_demo_ai_models()`. |
| Frontend build (`yarn install --ignore-engines && yarn build`) | **FAIL, but not a live regression — see below** | `tsc -b` failed: `badge.test.tsx(8,18): error TS2305: Module '"@testing-library/react"' has no exported member 'screen'`. Root cause: `@testing-library/dom` (a peer dependency of `@testing-library/react`, required for the `screen` re-export) is not declared in `frontend/package.json` and a clean `yarn install` does not pull it in. Confirmed by manually adding it (`yarn add -D @testing-library/dom@^10.4.1 --ignore-engines`), after which the build succeeded cleanly. **This exact fix already exists on the live branch** — commit `2ca61a50 fix(frontend): add @testing-library/dom as an explicit devDependency` — but that commit is one of the ~20 unpushed to the stale bare mirror this run had to use (see branch caveat above). So: not a regression on the current branch tip, just an artifact of testing an old snapshot. |
| Backend health (`/api/method/ping`) | **PASS** | `{"message":"pong"}` after `bench start`. |
| Critical smoke (`/huf/` shell + its JS bundle) | **PASS** (after applying the one-line devDependency fix locally to complete the build) | `/huf/` → 200; referenced bundle `/assets/huf/frontend/assets/index-*.js` → 200. |

## Discrepancies found

1. **Stale local bare source mirror** (process/tooling issue, not a HUF app
   bug): `/workspace/.sources-local/huf.git` on this host is ~20 commits
   behind the actual tip of `explore/regression-safety-e2e` as worked in the
   `regression-safety-e2e` bench and this track's own worktree. Anyone
   provisioning a fresh bench from this mirror right now gets an outdated
   snapshot of the branch, silently. Recommend: fetch/sync the mirror from
   wherever these branches are actually being pushed (or push commits from
   the live checkouts into the mirror) before next using it for provisioning.
2. **No genuine install/migrate/seed defect found** on the snapshot tested.
   The one build failure encountered (missing `@testing-library/dom`
   devDependency) is already fixed on the live branch; it only surfaced here
   because of finding #1.

## Teardown confirmation

- `teardown.sh` ran cleanly: bench process killed, DB/user dropped, Redis DBs
  flushed, dev worktree removed via `git worktree remove`, registry entry
  removed.
- `/workspace/benches/regression-migration-check` no longer exists.
- `regression-migration-check` no longer appears in
  `/workspace/benches/registry.json`.
- Temporary verification branch `phase9-migcheck-verify` deleted from the
  bare mirror.
- Confirmed **`regression-safety-e2e` bench was not touched**: still present,
  registry status `ready`.
