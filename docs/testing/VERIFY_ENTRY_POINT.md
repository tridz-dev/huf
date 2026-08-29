# Single Verification Entry Point

Per `GOAL.md` §21: humans and coding agents must use the same test system, and
agents must not invent their own ad-hoc test commands. That entry point is:

```bash
./scripts/huf-verify.sh <target> [--base <ref>]
```

## Targets

| Target | What it runs | Needs a bench? |
|---|---|---|
| `quick` | frontend typecheck + Vitest unit tests + design parity | no |
| `frontend` | `quick` + production build | no |
| `backend` | `bench --site <site> run-tests --app huf` (optionally scoped via `HUF_BACKEND_MODULE`) | yes |
| `e2e` | mocked/offline Playwright, fast subset (excludes `visual-regression.spec.ts` / `accessibility.spec.ts`) | no |
| `security` | Semgrep (`--config .semgrep.yml huf/`) | no (skips gracefully if semgrep isn't installed) |
| `full` | `frontend` + full mocked Playwright (incl. visual/a11y) + `security`, plus `backend` and deployed Playwright IF a bench is reachable | degrades gracefully if not |
| `changed` | diffs against a base ref (default `develop`) and runs only the subset above relevant to what changed | depends on what changed |

Every run prints a `[PASS]/[FAIL]/[SKIP]` line per sub-check at the end, so a
human or agent can see exactly what happened without re-reading the whole log,
and the script's own exit code is non-zero if **any** check in the target
failed.

## Bench-backed checks (`backend`, `full`, `changed` when backend files changed)

The script auto-detects a live bench via `docker exec` into
`HUF_BENCH_CONTAINER` (default `frappe_docker_devcontainer-frappe-1`),
scanning `/workspace/benches/*/sites/*` for a site with a `site_config.json`.
Override with:

- `HUF_BENCH_CONTAINER` — the docker container name
- `HUF_BENCH_SITE` — the site name inside that bench
- `HUF_BENCH_PATH` — the bench directory inside the container

If no bench is reachable, `backend` fails with a clear message pointing at the
`frappe-multihand` skill (`mh-tools/provision.sh`) to provision one; `full`
skips the bench-backed checks instead of hard-failing, and says so explicitly
in its summary.

**Known gotcha this script works around:** `bench run-tests` can exit `0` even
when unittest reported failures/errors. The script does not trust the exit
code alone for `backend` — it parses the unittest summary line
(`OK` vs `FAILED (...)`) out of the output.

The deployed Playwright suite (`playwright.deployed.config.ts`) additionally
needs the site reachable over plain HTTP from wherever the script runs (not
just via `docker exec`) — set `BASE_URL`/`E2E_BASE_URL` if the bench's
host-mapped address differs from the config's default. `full` probes this and
skips with a clear message rather than failing on a doomed connection.

## `changed` file → target mapping

Kept deliberately simple, not clever (see the script's own header comment for
the authoritative version):

- `frontend/e2e/**` changed → `e2e` (mocked, fast subset)
- `frontend/**` changed → `frontend` (typecheck + unit + build + design parity)
- `huf/**/*.py` changed → `backend`, scoped to
  `huf/ai/tests/test_<basename>.py` as a `--module` if that 1:1 test file
  exists, else the full `--app huf` suite
- Nothing recognized → falls back to `quick`

Override the base ref with `--base <ref>` or `HUF_VERIFY_BASE`.

## Not yet wired

`playwright.nightly.config.ts` (cross-browser matrix) is intentionally not
run by `full` — it's meant for a separate scheduled job, not an on-demand
verify pass. `full` prints a note pointing at how to run it directly.
