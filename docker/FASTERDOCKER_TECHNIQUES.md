# FasterDocker Deep-Dive: How HUF Dockerizes Frappe for Fast Boot

> A complete technical compendium of the Docker speed-up techniques, Frappe/Bench optimisations, and HUF-specific customisations used in this workspace. The goal is to capture enough depth to repeat this for any Frappe app, and to seed a future `bench add-docker` / `bench add-docker --fast` project.

---

## 1. Branch inventory and current state

### Branches visible in this workspace

```text
* feat/fasterdocker-warm-boot                     <-- current local branch
  remotes/origin/HEAD -> origin/develop           <-- default upstream branch
  remotes/origin/develop                          <-- latest shared branch
  remotes/origin/feat/fasterdocker-warm-boot      <-- upstream tracking branch
  remotes/origin/legacy
  remotes/origin/add-google-search-tool
  remotes/origin/add-perplexity-search-tool
  ... (many feature/doc/fix branches)
```

Full list (as of the moment this document was written):

| Branch | Type | Notes |
|--------|------|-------|
| `feat/fasterdocker-warm-boot` | local active | The Docker speed-up work lives here. |
| `origin/develop` | default / latest | `origin/HEAD` points here. This is the branch the FasterDocker workflow publishes from. |
| `origin/legacy` | old stable | Pre-FasterDocker baseline. |
| `origin/feature/*`, `origin/feat/*`, `origin/fix/*`, `origin/doc/*`, `origin/cursor/*`, `origin/claude/*`, `origin/kimi/*`, `origin/codex/*` | feature / fix / docs / agent-work branches | Various product workstreams unrelated to Docker boot speed. |

### Active vs. latest

- **Active branch in this workspace:** `feat/fasterdocker-warm-boot`
- **Latest upstream branch:** `origin/develop` (the GitHub default)
- The FasterDocker publish workflow triggers on pushes to `develop` and on version tags `v*`.

---

## 2. The problem we were solving

A stock Frappe/Bench Docker setup is slow for three independent reasons:

1. **Heavy first-time build.** `bench init` clones Frappe, installs Python/Node dependencies, builds frontend assets, and compiles native wheels. This can take 5–15 minutes on a clean machine.
2. **Heavy first start.** `bench new-site`, `install-app`, and `migrate` run schema creation, fixture installation, and frontend builds. This can add another 5–10 minutes before the site is reachable.
3. **Heavy warm restart.** Without careful design, every `docker compose up` repeats asset builds, dependency checks, or even site creation.

FasterDocker attacks all three by shifting work from **runtime to bake-time** and by **shipping pre-baked state** in images.

---

## 3. High-level architecture

```text
┌────────────────────────────────────────────────────────────────────┐
│                        Build / Bake Phase                          │
│  (runs once per release, in CI or on a developer machine)          │
│                                                                    │
│  1. Dockerfile.runtime  →  huf-frappe-runtime:16.25.0             │
│     (Frappe framework + bench + Python/Node toolchain)             │
│                                                                    │
│  2. Dockerfile.huf      →  huf-app:<sha>                           │
│     (HUF app source + Python deps + frontend build + SQL seed)     │
│                                                                    │
│  3. build-demo.sh       →  huf-demo:<sha>                          │
│     (physical MariaDB snapshot + redis-server layered on huf-app)  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ publishes to GHCR
┌────────────────────────────────────────────────────────────────────┐
│                        Runtime Phase                               │
│  (end user does `docker compose up --wait`)                        │
│                                                                    │
│  docker/docker-compose.yml:                                        │
│    - mariadb container waits for a snapshot marker                 │
│    - single frappe container copies snapshot, starts Redis,        │
│      waits for MariaDB, runs bench                                 │
│    - first boot: ~6 s, warm restart: ~5 s                          │
└────────────────────────────────────────────────────────────────────┘
```

Core philosophy:

- **Runtime does no install/build/migrate/network setup.** Everything expensive happens at bake time.
- **The demo image is a warm-boot appliance.** It contains not just code, but a ready-to-run database snapshot and site folder.
- **First boot only copies data; warm boots skip the copy.** Volumes persist across restarts.

---

## 4. Docker-specific techniques

### 4.1 Multi-stage builds

Files: `docker/fast/Dockerfile.runtime`, `docker/fast/Dockerfile.huf`, `docker/fast/Dockerfile.demo`

```dockerfile
# Dockerfile.runtime
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_BASE} AS base
# ... runtime packages only ...

FROM base AS builder
# ... build-only packages ...
RUN bench init ...

FROM base AS runtime
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
```

Why it helps:

- Build tools (`build-essential`, `libsqlite3-dev`, `pkg-config`, `gcc`, etc.) never reach the final image.
- The final runtime image is smaller, has fewer CVEs, and starts faster because Docker pulls fewer layers.

### 4.2 Slim base image

```dockerfile
ARG PYTHON_VERSION=3.14.2
ARG DEBIAN_BASE=bookworm
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_BASE} AS base
```

- `python:3.14.2-slim-bookworm` is used instead of the full Debian image.
- wkhtmltopdf and Chromium are intentionally omitted from the demo image to keep size down. See `Dockerfile.runtime` header: "Chromium and wkhtmltopdf are intentionally omitted... PDF/print generation will not work."

### 4.3 Layer ordering for cache reuse

In `Dockerfile.runtime`:

1. Install OS runtime packages (changes rarely).
2. Install `frappe-bench` (changes rarely).
3. Install build tools in a separate stage (changes rarely).
4. Run `bench init` (changes only when Frappe version changes).
5. In `Dockerfile.huf`, copy HUF source and build frontend/Python assets (changes every HUF commit).

This ordering means a HUF code change only rebuilds the HUF layers, not the Frappe runtime layers.

### 4.4 Bake phase: shift heavy work to image build time

The **bake phase** performs these expensive operations once:

- `bench init`
- `bench new-site`
- `bench --site <site> install-app huf`
- `bench --site <site> migrate`
- `bench build` (frontend + Frappe assets)
- `mysqldump` of the seeded database

Artifacts are exported to `docker/fast/.bake-output/`:

```text
.bake-output/
├── sql/
│   └── huf.localhost.sql.gz
├── sites/
│   ├── apps.txt
│   ├── common_site_config.json
│   ├── assets -> /home/frappe/frappe-bench/assets   (symlink)
│   └── huf.localhost/
│       ├── site_config.json
│       └── ...
└── metadata.json
```

### 4.5 Physical MariaDB snapshot (fastest restore)

Files: `docker/fast/Dockerfile.demo`, `docker/fast/build-demo.sh`, `docker/fast/demo-entrypoint.sh`, `docker/fast/physical-mariadb-entrypoint.sh`

Two seed strategies exist:

| Strategy | How it restores | Best for |
|----------|-----------------|----------|
| SQL | `zcat site.sql.gz \| mysql` | Smaller images, architecture-independent. |
| Physical | Copy `/var/lib/mysql` files directly into the volume | Fastest first boot; used by the single-image demo. |

The single-image demo uses the physical strategy:

```dockerfile
# Dockerfile.demo
COPY --chown=999:999 docker/fast/mysql-data/ /var/lib/mysql-snapshot/
```

At runtime `demo-entrypoint.sh` copies the snapshot into the MariaDB volume if it looks empty:

```bash
if [[ ! -f "${MARIADB_DATA_DIR}/ibdata1" ]]; then
  cp -a "${SNAPSHOT_DIR}/." "${MARIADB_DATA_DIR}/"
  chown -R 999:999 "${MARIADB_DATA_DIR}"
  touch "${SNAPSHOT_MARKER}"
fi
```

MariaDB's container entrypoint waits for that marker before starting mysqld, avoiding a startup race:

```yaml
# docker-compose.yml
entrypoint:
  - /bin/bash
  - -c
  - |
    until test -f /var/lib/mysql/.fasterdocker-snapshot-ready; do
      sleep 1
    done
    exec docker-entrypoint.sh mysqld
```

This is the key trick that gets first boot down to ~6 seconds.

### 4.6 Atomic completion markers (fail-closed seeding)

Files: `docker/fast/init-seed.sh`

```bash
IN_PROGRESS="${MARKER_DIR}/.fasterdocker-seed-in-progress"
COMPLETE="${MARKER_DIR}/.fasterdocker-seed-complete"

# Fail-closed: if a previous run died, require manual cleanup.
if [[ -f "${IN_PROGRESS}" && ! -f "${COMPLETE}" ]]; then
  log "ERROR: incomplete seed marker found..."
  exit 1
fi

# Idempotent warm restart.
if [[ -f "${COMPLETE}" ]]; then
  log "Seed complete marker found; skipping restore."
  exit 0
fi

touch "${IN_PROGRESS}"
# ... do seed work ...
mv "${IN_PROGRESS}" "${COMPLETE}"
```

Why it matters:

- Prevents partially-seeded volumes from being mistaken as complete.
- Makes warm restarts deterministic.
- Makes debugging easier because the marker tells you exactly where a failed run stopped.

### 4.7 Docker layer optimisation

- Remove `.git` directories after `bench init`:
  ```bash
  find apps -mindepth 1 -path "*/.git" -prune -exec rm -rf {} +
  ```
- Remove caches after builds:
  ```bash
  rm -rf /home/frappe/.cache /home/frappe/frappe-bench/.cache /tmp/*
  ```
- In `Dockerfile.huf`, build frontend assets then delete `node_modules`:
  ```dockerfile
  RUN cd apps/huf/frontend \
      && yarn install --frozen-lockfile \
      && yarn build \
      && rm -rf node_modules
  ```

### 4.8 Cross-platform / multi-arch publishing

File: `.github/workflows/fasterdocker-publish.yml`

Because physical MariaDB snapshots are architecture-specific (the data files depend on the MariaDB binary format and page size), the demo image is built **per native architecture** and then assembled into a manifest list:

```yaml
strategy:
  matrix:
    include:
      - platform: linux/amd64
        os: ubuntu-latest
        suffix: amd64
      - platform: linux/arm64
        os: ubuntu-24.04-arm
        suffix: arm64
```

Then:

```yaml
docker buildx imagetools create \
  -t "ghcr.io/tridz-dev/huf-demo:${HUF_IMAGE_TAG}" \
  -t "ghcr.io/tridz-dev/huf-demo:latest" \
  "ghcr.io/tridz-dev/huf-demo:${HUF_IMAGE_TAG}-amd64" \
  "ghcr.io/tridz-dev/huf-demo:${HUF_IMAGE_TAG}-arm64"
```

Key decision: **no QEMU for snapshot generation.** Physical snapshots are created on native runners because emulated MariaDB would be fragile and slow.

### 4.9 Image registry caching in CI

```yaml
uses: docker/build-push-action@v5
with:
  cache-from: type=gha
  cache-to: type=gha,mode=max
```

- Uses GitHub Actions cache for Docker layer cache.
- `mode=max` caches all layers, including intermediate ones, giving the biggest speed-up on rebuilds.

### 4.10 `.dockerignore` discipline

File: `.dockerignore`

```text
.git
.github
.pytest_cache
__pycache__
*.pyc
*.pyo
*.egg-info
node_modules
frontend/node_modules
.vscode
.idea
.env
.env.example
.DS_Store
```

Deliberate choices:

- `*.md` is **not** excluded because `pyproject.toml` references `README.md`.
- `docker/fast/.bake-output/*` is **kept in the Docker context** (only excluded from git via `.gitignore`) because the app image bundles the seed artifacts.

### 4.11 Container naming contract

File: `docker/fast/_lib.sh`

```bash
ALLOWED_PREFIXES=(
  "fasterdocker-build-*"
  "fasterdocker-seed-*"
  "fasterdocker-run-*"
)
```

All compose files use these prefixes. This makes:

- Bulk cleanup safe.
- Benchmarking reproducible.
- CI teardown deterministic.

### 4.12 Health checks and dependency ordering

Every service has a `healthcheck`. Compose `depends_on` uses `condition: service_healthy` or `condition: service_completed_successfully` so containers start in the right order without brittle `sleep` scripts.

### 4.13 Volume persistence for warm restarts

```yaml
volumes:
  mariadb-data:
  sites:
  logs:
```

On `docker compose restart`:

- The MariaDB volume already contains data.
- The sites volume already contains the site folder.
- The seed/copy logic sees existing data and skips.

### 4.14 Avoid separate Redis service in single-image demo

File: `docker/fast/Dockerfile.demo`

```dockerfile
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y redis-server \
    && rm -rf /var/lib/apt/lists/*
```

The single-image demo runs Redis inside the Frappe container, eliminating the need for separate Redis containers and simplifying the compose file to just `mariadb` + `frappe`.

### 4.15 Unprivileged nginx frontend

File: `docker/fast/resources/nginx/nginx-entrypoint.sh`, `docker/fast/Dockerfile.huf`

The runtime image pre-owns nginx paths to the `frappe` user so the frontend container can run unprivileged:

```bash
chown -R frappe:frappe /etc/nginx/conf.d
chown -R frappe:frappe /etc/nginx/nginx.conf
chown -R frappe:frappe /var/log/nginx
chown -R frappe:frappe /var/lib/nginx
```

Nginx listens on the unprivileged port `8080`.

---

## 5. Frappe / Bench-specific techniques

### 5.1 `bench init` flags that speed things up

File: `docker/fast/Dockerfile.runtime`

```bash
bench init \
  --frappe-branch=${FRAPPE_VERSION} \
  --frappe-path=${FRAPPE_PATH} \
  --no-procfile \
  --no-backups \
  --skip-redis-config-generation \
  --verbose \
  /home/frappe/frappe-bench
```

Why each flag matters:

| Flag | Effect |
|------|--------|
| `--no-procfile` | Do not generate a `Procfile`; we generate our own at runtime. |
| `--no-backups` | Skip backup scheduling setup. |
| `--skip-redis-config-generation` | Redis runs in separate containers, so no local Redis config is needed. |
| `--verbose` | Helps debugging CI builds. |

### 5.2 Minimise the bench before copying it

```bash
echo "{}" > sites/common_site_config.json
find apps -mindepth 1 -path "*/.git" -prune -exec rm -rf {} +
rm -rf /home/frappe/.cache
rm -rf /home/frappe/frappe-bench/.cache
```

- An empty `common_site_config.json` is written so the baked bench has a known starting point.
- `.git` directories are removed to shrink the image and prevent accidental rebuilds triggered by git metadata changes.

### 5.3 Asset handling: bake once, symlink at runtime

File: `docker/fast/Dockerfile.runtime`

```dockerfile
RUN cp -r /home/frappe/frappe-bench/sites/assets /home/frappe/frappe-bench/assets \
    && rm -rf /home/frappe/frappe-bench/sites/assets
```

File: `docker/fast/resources/core/main-entrypoint.sh`

```bash
rm -rf "$ASSETS_PATH"
mkdir -p "$(dirname "$ASSETS_PATH")"
ln -s "$BAKED_PATH" "$ASSETS_PATH"
```

Frappe expects assets under `sites/assets`, but `sites` is a Docker volume. By baking assets into the image at `/home/frappe/frappe-bench/assets` and symlinking them into the volume at runtime, we:

- Avoid copying large asset directories into the volume on every start.
- Keep the volume small.
- Make asset updates automatic when a new image is deployed.

### 5.4 Runtime `common_site_config.json` rewrite

File: `docker/fast/bench-start.sh`, `docker/fast/init-seed.sh`

The baked `common_site_config.json` contains bake-time hostnames (`mariadb-bake`, `redis-cache-bake`). At runtime it is rewritten with runtime hostnames:

```bash
cat > sites/common_site_config.json <<EOF
{
  "db_host": "${DB_HOST}",
  "db_port": ${DB_PORT},
  "redis_cache": "${REDIS_CACHE}",
  "redis_queue": "${REDIS_QUEUE}",
  "redis_socketio": "${REDIS_SOCKETIO}",
  "socketio_port": 9000,
  "developer_mode": 1
}
EOF
```

This is essential because Docker Compose service names differ between the bake environment and the runtime environment.

### 5.5 Custom Procfile for containerised bench

File: `docker/fast/bench-start.sh`

```bash
cat > Procfile <<EOF
web: bench serve --port ${BENCH_START_PORT}
socketio: node /home/frappe/frappe-bench/apps/frappe/socketio.js
schedule: bench schedule
worker: bench worker --queue ${BENCH_WORKER_QUEUES}
EOF
```

- Removes `redis` from the Procfile (external Redis).
- Removes `watch` (file watcher not needed in a container).
- Uses `bench serve` directly for the dev/test bench profile.

### 5.6 Production-like split services

Files: `docker/compose.fast.yml`, `docker/compose.fast-physical.yml`

For production-parity testing, the app is split into:

- `web` (gunicorn)
- `worker-short`
- `worker-long`
- `scheduler`
- `socketio`
- `frontend` (nginx)
- `mariadb`
- `redis-cache`, `redis-queue`, `redis-socketio`

Each service uses the same `huf-app` image but runs a different command. This proves the image is production-ready, not just a demo shortcut.

### 5.7 Gunicorn tuning

File: `docker/fast/resources/core/start.sh`

```bash
exec /home/frappe/frappe-bench/env/bin/gunicorn \
  --chdir=/home/frappe/frappe-bench/sites \
  --bind=0.0.0.0:8000 \
  --threads="$GUNICORN_THREADS" \
  --workers="$GUNICORN_WORKERS" \
  --worker-class=gthread \
  --worker-tmp-dir=/dev/shm \
  --timeout="$GUNICORN_TIMEOUT" \
  --preload \
  frappe.app:application
```

Key choices:

- `--preload` loads the application once before forking workers, reducing memory and startup time.
- `--worker-tmp-dir=/dev/shm` keeps temporary files in memory.
- `gthread` worker class matches the threaded Frappe app.

### 5.8 MariaDB flags for Frappe compatibility

```yaml
command:
  - --character-set-server=utf8mb4
  - --collation-server=utf8mb4_unicode_ci
  - --skip-character-set-client-handshake
  - --skip-innodb-read-only-compressed
```

These flags are the same ones used by `frappe_docker` and are required for Frappe to create tables correctly.

### 5.9 `MARIADB_AUTO_UPGRADE: "1"`

Enables automatic MariaDB minor-version upgrades on first start, which is important when users pull a newer MariaDB image than the one used to bake the snapshot.

### 5.10 Site config reuse

During the bake, Frappe generates a random `db_name` and `db_password` in `site_config.json`. At runtime we read these back:

```bash
DB_NAME="$(jq -r '.db_name // empty' "${SITE_CONFIG}")"
DB_PASSWORD="$(jq -r '.db_password // empty' "${SITE_CONFIG}")"
```

This means we do not need to hardcode database names; we just restore whatever Frappe created during baking.

### 5.11 Bench commands run at bake time, not runtime

- `bench new-site`
- `bench install-app huf`
- `bench migrate`
- `bench build`
- `bench set-config developer_mode 1`
- `bench clear-cache`

All of these happen in `bake-site.sh` during image build. The runtime containers only run the final services.

### 5.12 `bench use` for ad-hoc commands

File: `docker/fast/bench-start.sh`

```bash
bench use "${SITE_NAME}" >/dev/null 2>&1 || true
```

Pins the default site so any manual `docker exec ... bench ...` commands work without `--site`.

---

## 6. HUF-specific techniques

### 6.1 Frontend build inside the app image

File: `docker/fast/Dockerfile.huf`

```dockerfile
COPY --chown=frappe:frappe pyproject.toml README.md LICENSE package.json yarn.lock ./apps/huf/
COPY --chown=frappe:frappe huf ./apps/huf/huf
COPY --chown=frappe:frappe frontend ./apps/huf/frontend

RUN cd apps/huf/frontend \
    && yarn install --frozen-lockfile \
    && yarn build \
    && rm -rf node_modules
```

The HUF frontend is a Vite + React + TypeScript app. Building it at image-build time means:

- End users do not wait for `yarn install`.
- The final image contains compiled static assets.
- `node_modules` is deleted after the build to keep the image small.

### 6.2 Python dependency installation

```dockerfile
RUN ./env/bin/pip install --no-cache-dir -e ./apps/huf
```

HUF is installed in editable mode into the bench virtualenv. This keeps imports working as Frappe expects (`apps.huf.*`).

### 6.3 Dependency conflict resolution

```dockerfile
RUN ./env/bin/pip install --no-cache-dir "click~=8.3.1"
```

HUF's transitive dependencies pulled `click` 8.1.8, but Frappe v16.25.0 expects `click ~= 8.3.1`. The Dockerfile explicitly reconciles this at bake time so the runtime environment is consistent.

### 6.4 Register HUF in `sites/apps.txt`

```dockerfile
RUN ls -1 apps > sites/apps.txt
```

Frappe's asset build uses `sites/apps.txt` to know which apps to include. Without this, the HUF frontend assets would be missing from the built `sites/assets` directory.

### 6.5 Demo seed data

Files: `huf/huf/prompts/demo-assistant.json`, `huf/huf/agents/demo-assistant.json`

Commit `22e705c` added HUF demo seed data. The demo agent (Google's `gemini-3.5-flash-lite`) is **enabled by default** so it's ready to chat with as soon as a Google AI Provider API key is added — it costs nothing until then, since no run happens without one.

The seed data is loaded through HUF's app-seeding framework. The guard that skipped HUF during seeding was removed in that commit:

> "Enable the huf app to seed its own demo data by removing the 'skip huf' guard in `huf/ai/app_seeding/scanner.py`."

### 6.6 pysqlite3-binary conditional

File: `pyproject.toml`

```toml
"pysqlite3-binary; platform_machine == 'x86_64' and python_version < '3.14'",
```

On Apple Silicon / ARM64, `pysqlite3` is built from source because the binary wheel is x86_64-only. The Dockerfile includes `libsqlite3-dev` and `build-essential` in the builder stage for this reason.

### 6.7 HUF-specific runtime entrypoints

File: `docker/fast/Dockerfile.huf`

```dockerfile
COPY docker/fast/bench-start.sh /usr/local/bin/bench-start.sh
COPY docker/fast/resources/nginx/nginx-entrypoint.sh /usr/local/bin/nginx-entrypoint.sh
COPY docker/fast/resources/core/main-entrypoint.sh /usr/local/bin/entrypoint.sh
```

The app image layers HUF-specific scripts on top of the generic Frappe runtime image. This keeps the runtime image reusable for other apps while HUF customisations live only in the app image.

---

## 7. File-by-file reference guide

| File | Purpose | Key technique |
|------|---------|---------------|
| `docker/docker-compose.yml` | End-user single-image demo compose. | Two services, physical snapshot copy, Redis inside Frappe container. |
| `docker/docker-compose.legacy.yml` | Old slow-path compose. | `frappe/bench:latest` + `init.sh` doing full build at runtime. |
| `docker/compose.bench.yml` | Dev/test profile. | Single container `bench start` + bundled SQL seed. |
| `docker/compose.fast.yml` | Production-parity split, SQL seed. | Separate web/worker/scheduler/socketio/nginx/Redis. |
| `docker/compose.fast-physical.yml` | Production-parity split, physical snapshot. | MariaDB seed image with custom entrypoint. |
| `docker/compose.bake.yml` | Build-time bake environment. | Runs `bake-site.sh` to generate seed artifacts. |
| `docker/fast/Dockerfile.runtime` | Frappe runtime base image. | Multi-stage, slim base, build/runtime split. |
| `docker/fast/Dockerfile.huf` | HUF app image. | Installs HUF, builds frontend, bundles SQL seed. |
| `docker/fast/Dockerfile.seed` | Minimal seed image. | Alpine + mariadb-client + jq; no full MariaDB server. |
| `docker/fast/Dockerfile.demo` | Single-image demo. | Layers physical snapshot and redis-server on huf-app. |
| `docker/fast/bake-site.sh` | Bake-phase site creation. | `bench new-site`, `install-app`, `migrate`, `mysqldump`. |
| `docker/fast/bake-seed.sh` | Builds seed image from bake output. | Captures MariaDB digest for physical snapshots. |
| `docker/fast/build-demo.sh` | Generates physical snapshot and builds demo image. | Uses temporary compose + `docker cp`. |
| `docker/fast/init-seed.sh` | Runtime seed restore (SQL or physical). | Atomic markers, architecture/digest validation. |
| `docker/fast/bench-start.sh` | Single-container `bench start`. | Custom Procfile, config rewrite. |
| `docker/fast/demo-entrypoint.sh` | Single-image demo entrypoint. | Snapshot copy, site copy, Redis start, drop to frappe. |
| `docker/fast/physical-mariadb-entrypoint.sh` | Physical seed MariaDB entrypoint. | Copies `/seed/mysql-data` into volume. |
| `docker/fast/resources/core/main-entrypoint.sh` | Generic entrypoint. | Asset symlink, seed init, privilege drop. |
| `docker/fast/resources/core/start.sh` | Gunicorn starter. | `--preload`, `gthread`, `/dev/shm`. |
| `docker/fast/resources/nginx/*` | Nginx frontend config and entrypoint. | Unprivileged, envsubst-based templating. |
| `docker/fast/benchmark.sh` | Benchmark driver. | Locks, scoped cleanup, multiple strategies, CSV output. |
| `docker/fast/_lib.sh` | Shared helpers. | Container naming contract, safe cleanup. |
| `docker/fast/.env.example` | Environment defaults. | Centralised tuning variables. |
| `.dockerignore` | Build context exclusions. | Keeps image context small. |
| `.github/workflows/fasterdocker-publish.yml` | CI publish workflow. | Native per-arch builds + manifest list. |

---

## 8. Build pipelines

### 8.1 Local build sequence

```bash
# 1. Build runtime image
docker build -f docker/fast/Dockerfile.runtime -t huf-frappe-runtime:16.25.0 .

# 2. Build HUF app image (bundles SQL seed)
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker build -f docker/fast/Dockerfile.huf -t huf-app:${HUF_IMAGE_TAG} .

# 3. Build single-image demo (optional)
./docker/fast/build-demo.sh

# 4. Run single-image demo
cd docker
export HUF_DEMO_IMAGE=huf-demo
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker compose up --wait
```

### 8.2 CI publish sequence

```text
push to develop or tag v*
  │
  ▼
GitHub Actions matrix:
  ├─ linux/amd64 runner
  │   └─ build-demo.sh → push huf-demo:<sha>-amd64
  └─ linux/arm64 runner
      └─ build-demo.sh → push huf-demo:<sha>-arm64
  │
  ▼
manifest job
  └─ docker buildx imagetools create
       ├─ huf-demo:<sha>
       └─ huf-demo:latest
```

---

## 9. Benchmarking methodology

File: `docker/fast/benchmark.sh`

Benchmarked strategies:

| Strategy | Compose file | What it measures |
|----------|--------------|------------------|
| `bench` | `compose.bench.yml` | Fastest dev/test path. |
| `sql` | `compose.fast.yml` | Production-like split with SQL restore. |
| `physical` | `compose.fast-physical.yml` | Production-like split with physical snapshot. |
| `current` | `docker-compose.yml` (legacy) | Old slow-path baseline. |

Each strategy runs:

1. `seeded-first-start` — volumes removed, full seed/copy measured.
2. `restart-warm-start` — volumes kept, restart measured.

Recorded metrics:

- `total_seconds`
- `db_healthy_seconds`
- `web_healthy_seconds`
- `huf_ready_seconds` (HTTP 200 on `/huf`)

Result CSV columns:

```csv
timestamp,branch,sha,strategy,start_type,run_number,down_v_used,image_warm,
total_seconds,db_healthy_seconds,web_healthy_seconds,huf_ready_seconds,result,notes
```

Observed results (from commit messages):

| Scenario | Time |
|----------|------|
| Single-image first boot | ~5.8 s |
| Single-image warm restart | ~5.1 s |

Hardening in `benchmark.sh`:

- PID-based lock file prevents concurrent runs.
- `COMPOSE_PARALLEL_LIMIT=1` avoids OrbStack container-creation races.
- All cleanup is scoped to `fasterdocker-*` container prefixes.

---

## 10. Future project: `bench add-docker` / `bench add-docker --fast`

The techniques above are currently hardcoded for HUF. They can be generalised into a Frappe CLI command that any app developer can run.

### 10.1 Proposed CLI

```bash
# Add standard Docker support to the current Frappe app
bench add-docker

# Add the optimised, prebaked, fast-boot variant
bench add-docker --fast

# Options
bench add-docker --fast \
  --app myapp \
  --frappe-version v16.25.0 \
  --python 3.14.2 \
  --node 24.13.0 \
  --registry ghcr.io/myorg \
  --site myapp.localhost
```

### 10.2 What the command would generate

| Output | Description |
|--------|-------------|
| `docker/Dockerfile.runtime` | Multi-stage Frappe runtime image for the chosen versions. |
| `docker/Dockerfile.<app>` | App image with editable pip install, frontend build, seed bundle. |
| `docker/Dockerfile.demo` | Optional single-image demo with physical snapshot. |
| `docker/compose.bake.yml` | Bake environment for generating site seed. |
| `docker/compose.bench.yml` | Fast dev/test single-container compose. |
| `docker/compose.fast.yml` | Production-parity split compose (SQL seed). |
| `docker/compose.fast-physical.yml` | Production-parity split compose (physical snapshot). |
| `docker/docker-compose.yml` | End-user pull-and-run single-image compose. |
| `docker/fast/*.sh` | Bake, seed, build-demo, benchmark scripts. |
| `.github/workflows/<app>-docker-publish.yml` | CI workflow for native per-arch builds + manifest list. |
| `.dockerignore` | Context exclusions. |

### 10.3 Configuration inputs the tool would need

- App name and source path
- Frappe version, Python version, Node version
- Site name and admin password
- MariaDB image/version
- Registry and image prefix
- Frontend build command (yarn/npm, build directory, output path)
- Seed data loader (e.g. `fixtures`, app-seeding framework, custom SQL)
- Whether to include wkhtmltopdf/Chromium (defaults: no for `--fast`)

### 10.4 Key abstractions

1. **Runtime contract.** Any Frappe app image produced by the tool must expose:
   - `/home/frappe/frappe-bench/sites` as a volume.
   - `/home/frappe/frappe-bench/logs` as a volume.
   - A `bench-start.sh` or equivalent command.
   - An entrypoint that symlinks baked assets and runs seed init if bundled.

2. **Bake contract.** The tool runs:
   ```bash
   bench init
   bench get-app <app>
   bench new-site <site>
   bench --site <site> install-app <app>
   bench --site <site> migrate
   bench build
   mysqldump ... > seed.sql.gz
   ```

3. **Seed strategy contract.** Support both:
   - `sql` — smaller, arch-independent.
   - `physical` — fastest, arch-specific.

4. **Naming contract.** Prefix all generated containers with `<app>-build-*`, `<app>-seed-*`, `<app>-run-*`.

### 10.5 Suggested implementation stack

- Python package installed into the bench environment.
- Jinja2 templates for Dockerfiles, compose files, and shell scripts.
- A small YAML config file (e.g. `.bench/docker.yml`) in the app repo.
- CLI uses `click` or `bench`'s own command registration.

### 10.6 Open questions to resolve

- How to handle apps with multiple frontend apps or non-Vite builds?
- How to handle apps that require wkhtmltopdf/Chromium for production?
- How to make physical snapshots reproducible across MariaDB patch versions?
- Should the tool support Kubernetes manifests in addition to Compose?
- How to integrate with Frappe Cloud / Press builds?

---

## 11. Lessons learned and gotchas

1. **Physical snapshots are architecture-specific.** Never build an AMD64 demo image on an ARM64 runner using QEMU. Use native runners and a manifest list.
2. **MariaDB digest pinning matters.** A physical snapshot baked with one MariaDB image may not start with another. Capture and validate the digest in `metadata.json`.
3. **Asset symlinks must be recreated every start.** The sites volume is host-managed; do not assume the symlink survives.
4. **`.git` directories bloat images and bust caches.** Remove them after `bench init`.
5. **Build dependencies must not leak into the runtime image.** Use multi-stage builds aggressively.
6. **Compose `depends_on` with `service_healthy` removes most shell `sleep` hacks.** Use it.
7. **Fail-closed markers prevent mysterious half-seeded states.** Always write an in-progress marker and atomically rename it to complete.
8. **OrbStack has container-creation races.** `COMPOSE_PARALLEL_LIMIT=1` fixed flaky benchmark runs.
9. **Click version conflicts are real.** Pin transitive dependency versions at the end of the app Dockerfile.
10. **The end-user demo should be a single pull-and-run image.** Every extra service or build step is friction.

---

## 12. Quick command reference

```bash
# Try the published demo
git clone https://github.com/tridz-dev/huf.git
cd huf/docker
docker compose up --wait

# Build everything locally
cd huf
docker build -f docker/fast/Dockerfile.runtime -t huf-frappe-runtime:16.25.0 .
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker build -f docker/fast/Dockerfile.huf -t huf-app:${HUF_IMAGE_TAG} .
./docker/fast/build-demo.sh

# Run dev bench profile
docker compose -p fasterdocker -f docker/compose.bench.yml up --wait

# Run production-parity SQL profile
docker compose -p fasterdocker -f docker/compose.fast.yml up --wait

# Benchmark
./docker/fast/benchmark.sh bench 5
./docker/fast/benchmark.sh sql 5
./docker/fast/benchmark.sh physical 5

# Full reset
docker compose -p fasterdocker -f docker/compose.bench.yml down -v --remove-orphans
```

---

## 13. References and links

### Upstream patterns

- Frappe Docker production images: https://github.com/frappe/frappe_docker
- Docker multi-stage builds: https://docs.docker.com/build/building/multi-stage/
- Docker Buildx GitHub Actions cache: https://docs.docker.com/build/cache/backends/gha/
- Docker manifest lists: https://docs.docker.com/reference/cli/docker/manifest/

### HUF / project files

- End-user Docker README: [`docker/fast/README.md`](./fast/README.md)
- Single-image compose: [`docker/docker-compose.yml`](./docker-compose.yml)
- Legacy slow compose: [`docker/docker-compose.legacy.yml`](./docker-compose.legacy.yml)
- Bench profile: [`docker/compose.bench.yml`](./compose.bench.yml)
- Fast split SQL profile: [`docker/compose.fast.yml`](./compose.fast.yml)
- Fast split physical profile: [`docker/compose.fast-physical.yml`](./compose.fast-physical.yml)
- Bake environment: [`docker/compose.bake.yml`](./compose.bake.yml)
- CI workflow: [`.github/workflows/fasterdocker-publish.yml`](../.github/workflows/fasterdocker-publish.yml)
- App seeding scanner: `huf/ai/app_seeding/scanner.py`
- Project root README: [`README.md`](../README.md)

### Key commits in this effort

| Commit | Message |
|--------|---------|
| `fdecbe9` | `feat: add fast seeded Docker startup profiles` |
| `6ff26b9` | `chore: harden benchmark.sh against concurrent runs and macOS quirks` |
| `976c22a` | `feat: add simple docker-compose.yml and image publishing workflow` |
| `1448ce1` | `feat(docker): single-image pull-and-run HUF demo` |
| `3c6026c` | `feat(docker): cross-platform single-image demo, docs, and publish workflow` |
| `22e705c` | `feat(demo): add HUF demo seed data and document credentials` |
| `c9ec7d5` | `docs(docker): note ARM64-only prebuilt image and private GHCR status` |
| `fd7c3d6` | `docs(docker): image is now multi-arch (arm64 + amd64) via Rosetta` |
| `499f860` | `docs(docker): clarify single-image demo is trial-only and GHCR is public` |

---

## 14. Conclusion

FasterDocker achieves sub-10-second first boots for HUF by combining four ideas:

1. **Bake everything expensive once** (`bench init`, `new-site`, `install-app`, `migrate`, `bench build`).
2. **Ship pre-baked state** in images (SQL dump, sites folder, physical MariaDB snapshot).
3. **Make runtime a pure copy-and-start operation** with atomic markers and deterministic sequencing.
4. **Keep images small and cacheable** with multi-stage builds, slim bases, and strict `.dockerignore`.

The same pattern is applicable to any Frappe app. The next step is to package it as a reusable `bench add-docker --fast` command that generates these files from a small app-specific config.
