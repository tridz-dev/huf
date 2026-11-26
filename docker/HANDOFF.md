# Docker overhaul: handoff for an environment with Docker

Branch: `fix/intelligent-newton-f7052n` (commits `14bc6876`, `ffb797c8`, plus the commit that added this file).
Everything below was written and reviewed without a Docker daemon. Nothing has been booted. Your job is to
run it, fix what breaks, and finish the open items. Docker here means OrbStack on an Apple Silicon Mac
(arm64 native); amd64 can only be checked in CI.

## What changed (already on the branch)

- `docker/docker-compose.yml`: now the real demo compose for `ghcr.io/tridz-dev/huf-demo` (mariadb + frappe,
  Redis inside the frappe container, healthchecks, parameterized ports). Old runtime-bootstrap file is kept as
  `docker/docker-compose.legacy.yml` (+ `docker/init.sh`, now pinned to Frappe `v16.25.0`).
- `docker/try.sh`: `--timeout` / `HUF_WAIT_SECONDS` (default 300s, elapsed-time based), `creds` no longer remaps ports,
  clearer help.
- `docker/fast/demo-entrypoint.sh`: finishes credential rotation if a first boot was interrupted (missing creds file).
- `docker/compose.{bench,fast,fast-physical}.yml`: default platform is native (was forced `linux/arm64`).
- Docs unified on `./docker/try.sh up` then `./docker/try.sh creds`, URL `/huf`, random password (README, CLAUDE.md,
  AGENTS.md Docker section, docker/README.md, docker/fast/README.md).
- `.github/workflows/fasterdocker-publish.yml`: concurrency, paths filter, tag logic (develop -> `<sha>` + `develop`;
  stable `vX.Y.Z` -> version + `latest`; pre-release tags never move `latest`), boot smoke job gates the manifest, OCI labels.
- New `.github/workflows/docker-checks.yml` (PR check) and `.github/workflows/ghcr-cleanup.yml` (manual, dry run by default).
- `docs/testing/CI_TIERS.md` updated to match.

## Open work (do in this order)

### 1. Boot test the demo (arm64, OrbStack)
```bash
./docker/try.sh --dry-run                 # sanity
./docker/try.sh up                        # expect healthy in about 1-2 min, prints URL
./docker/try.sh creds                     # prints Administrator + password (random)
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
./docker/try.sh status
./docker/try.sh down && ./docker/try.sh up   # volumes kept: creds must still work, no re-rotation
./docker/try.sh reset                        # then `up` again: fresh random password
```
Things most likely to be wrong (an independent review flagged these from reading only):
- Redis: compose sets `REDIS_CACHE/QUEUE/SOCKETIO=redis://localhost:6379/N` because `bench-start.sh` rewrites
  `common_site_config.json` from env. If socketio or the container is unhealthy, check this first.
- Startup ordering: mariadb waits for `/var/lib/mysql/.fasterdocker-snapshot-ready`, which frappe creates. There is
  deliberately no `depends_on`. Confirm `up --wait` does not deadlock.
- Healthcheck uses `curl` with `Host: ${SITE_NAME}`; start period 120s is a guess. Tune if needed.
- Image tag `latest` is an older develop build; `develop` tag will not exist until the publish workflow runs. If the
  published image lacks something the new compose needs, either fix the compose or rebuild locally (step 3).
- Port remap: occupy 8000 (`python3 -m http.server 8000`) then `./docker/try.sh up`; it should remap and say so.
  Also try `--no-port-remap`.
- Interrupted first boot: `docker kill fasterdocker-run-frappe` right after the snapshot copy, then `up` again.
  Expect the entrypoint to log "No saved credentials found; finishing first-boot setup." and `creds` to work.
- Do not override `MARIADB_ROOT_PASSWORD` for the demo; the baked database keeps its root password. Docs say so.

### 2. Lint the new/changed files (nobody could run these)
```bash
brew install shellcheck hadolint actionlint   # or run via docker
shellcheck --severity=error docker/try.sh docker/init.sh docker/fast/*.sh
hadolint --failure-threshold error docker/fast/Dockerfile.*
actionlint .github/workflows/fasterdocker-publish.yml .github/workflows/docker-checks.yml .github/workflows/ghcr-cleanup.yml
for f in docker/docker-compose.yml docker/docker-compose.legacy.yml docker/compose.*.yml; do docker compose -f "$f" config -q || echo "FAIL $f"; done
```
`docker-checks.yml` runs these in CI at error severity, so fix findings rather than loosening the checks.

### 3. Local-code path (bench variant)
Follow the exact recipe in `AGENTS.md` ("Testing local code"): build runtime and app images, bake the site seed,
rebuild, then `./docker/try.sh --variant bench`. Confirm it works on a clean checkout and fix the recipe if not.
Also `--variant fast` and `--variant fast-physical`.

### 4. Container names and `creds`
`creds` now resolves the credentials container per variant (`creds_container_for_variant` in `try.sh`): demo uses
`fasterdocker-run-frappe`; bench, fast and fast-physical write no credentials file, so `creds` prints a message
pointing at `ADMIN_PASSWORD` (env/.env, default `fasterdocker-admin` for fast variants). Container names are still
fixed, so `--project` cannot run two stacks at once (documented only, not changed).

Boot test should confirm: `./docker/try.sh creds` prints URL/user/password for demo, and
`./docker/try.sh creds --variant bench` prints the no-credentials-file message without error.

### 5. Publish workflow and registry
- Review `fasterdocker-publish.yml` once more on a real run (workflow_dispatch from the branch is not possible until
  merged to develop; dispatch needs the file on the default branch). Check the smoke job logs on the first run.
- Run `ghcr-cleanup.yml` with `dry_run: true`, read the plan, only then rerun with dry run off. It targets untagged
  versions, orphaned per-arch tags (`9c6817b-arm64`, `ef06e28-arm64`, `d4f3aac-arm64`, `86d9250-amd64`, `bf77457-amd64`
  were seen) and sha builds beyond the newest 30. Never touches `latest`, `develop`, or version tags.
- Decide the first release tag so `latest` moves to a build made by the new workflow.

### 6. Commit author
Commits `14bc6876` and `ffb797c8` have author `Claude <noreply@anthropic.com>`. The owner's rule is no Claude
authorship anywhere. Rewrite the author of those two commits to the repo owner's identity, then
`git push --force-with-lease` this branch. It only has commits from this work, so the rewrite is safe, but confirm with
`git log origin/develop..HEAD`. All commits you add must also use the owner's git identity and no co-author or
session trailer lines.

### Not fixed on purpose
- `HUF_WAIT_SECONDS` / container-name items beyond #4 are documented limits, not blockers.
- amd64 can only be validated by the CI smoke job on `ubuntu-latest`.
- Do not tag or promote `latest` from a laptop.

## Prompt to give the agent

> You are on the huf repo, branch `fix/intelligent-newton-f7052n`. Read `docker/HANDOFF.md` and do the open work in
> its order. You have a real Docker daemon (OrbStack, arm64). Boot-test `./docker/try.sh up`, fix every failure you
> find in the compose, `try.sh`, entrypoint or docs, run shellcheck/hadolint/actionlint and the compose config
> checks, then do the container-name fix and the commit author rewrite. Use the project rules in `CLAUDE.md`. Work in
> small commits, no co-author lines, no mention of AI tools in commit messages, comments or docs. Report what passed,
> what you fixed, and anything you could not verify. Do not run the cleanup workflow for real or promote `latest`.
