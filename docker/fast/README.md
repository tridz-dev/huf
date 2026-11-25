# FasterDocker Fast Boot Setup

This directory contains the Docker assets for warm-booting HUF on Frappe v16.25.0.

The fastest way for end users to **try** HUF is the single-image demo in [`docker/docker-compose.yml`](../docker-compose.yml). It is intended for demo/trial use only — it bundles a pre-seeded site and runs everything in one container.

```bash
git clone https://github.com/tridz-dev/huf.git && cd huf && ./docker/try.sh up
./docker/try.sh creds
```

Then open http://localhost:8000/huf (user `Administrator`, password from `creds`).

There is no local build, `bench init`, `new-site`, `install-app`, or seed step once the published image is available.

For local development or production-parity validation, see the other compose profiles below instead of `docker-compose.yml`.

## Platform support

The demo image is published as a multi-arch manifest for `linux/amd64` (Intel/AMD Linux) and `linux/arm64` (Apple Silicon and ARM64 Linux). Docker pulls the correct architecture automatically.

- amd64 and arm64 are both published by CI, each built on a native runner (never emulated, because the physical MariaDB snapshot is arch-specific).
- Published tags are listed on the GHCR package page for `tridz-dev/huf-demo`.

Force the platform only if needed (native arch only):

```bash
export DOCKER_PLATFORM=linux/arm64   # or linux/amd64, matching your host
./docker/try.sh up
```

## Prebuilt image

The compose file uses `ghcr.io/tridz-dev/huf-demo:${HUF_IMAGE_TAG:-latest}`. `latest` is the most recent promoted build (a stable `vX.Y.Z` release, or a manual publish with `promote_latest`); the `develop` tag is the tip of the develop branch (use `--tag develop` for it); `<sha>` is multi-arch and `<sha>-amd64` / `<sha>-arm64` are per-arch. See the GHCR package page for `tridz-dev/huf-demo` for published tags.

To build locally instead, see [Building locally](#building-locally).

## Quick start (single-image demo)

```bash
./docker/try.sh up
```

This runs the published image, not your local checkout. To test local changes use the bench variant (see [Building locally](#building-locally)).

Health checks:

```bash
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
```

Log in at http://localhost:8000/huf:

- **User:** `Administrator`
- **Password:** random per first boot; run `./docker/try.sh creds`

The image ships with an enabled **Demo Assistant** agent (Google's `gemini-3.5-flash-lite`) and a **Demo Assistant Prompt** so you can see HUF's AI layer immediately. Add a Google AI provider API key in the UI before it answers.

Restart only the app (keeps the MariaDB volume):

```bash
docker compose -f docker/docker-compose.yml restart frappe
```

Full reset (back to seeded first start):

```bash
./docker/try.sh reset
./docker/try.sh up
```

## Building locally

### 1. Build the runtime image

```bash
docker build -f docker/fast/Dockerfile.runtime -t huf-frappe-runtime:16.25.0 .
```

### 2. Build the HUF app image

```bash
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker build -f docker/fast/Dockerfile.huf -t huf-app:${HUF_IMAGE_TAG} .
```

### 3. Build the single demo image

```bash
./docker/fast/build-demo.sh
```

To build for a different architecture (slow under emulation):

```bash
export DOCKER_PLATFORM=linux/amd64
./docker/fast/build-demo.sh
```

### 4. Run it

To test your local code, run the bench variant (uses the `huf-app` image from step 2):

```bash
./docker/try.sh --variant bench
```

To run your locally built demo image instead:

```bash
export HUF_DEMO_IMAGE=huf-demo
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker compose -f docker/docker-compose.yml up --wait
```

## Other profiles

These profiles are mainly for development and production-parity comparison.

| Profile | Compose file | Use case |
|---------|--------------|----------|
| **single-image demo** | `docker/docker-compose.yml` | End-user pull-and-run path. Fastest and simplest. |
| **bench** | `docker/compose.bench.yml` | One container running `bench start` + MariaDB + Redis. Fastest developer path. |
| **split SQL** | `docker/compose.fast.yml` | Production-like split web/worker/scheduler/socketio/nginx containers with SQL seed. |
| **split physical** | `docker/compose.fast-physical.yml` | Same split layout using a physical MariaDB snapshot. |

### Bench profile

```bash
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker compose -p fasterdocker -f docker/compose.bench.yml up --wait
```

The bench web port is exposed directly:

```bash
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
```

### Split profiles

```bash
# SQL seed
docker compose -p fasterdocker -f docker/compose.fast.yml up --wait

# Physical snapshot
docker compose -p fasterdocker -f docker/compose.fast-physical.yml up --wait
```

## Container contract

Development and benchmark containers use only these prefixes:

- `fasterdocker-build-*`
- `fasterdocker-seed-*`
- `fasterdocker-run-*`

The end-user `docker/docker-compose.yml` uses explicit `fasterdocker-run-*` names so it also satisfies this contract when run locally.

## Reset to seeded first start

Bench profile:

```bash
docker compose -p fasterdocker -f docker/compose.bench.yml down -v --remove-orphans
```

Split profile:

```bash
docker compose -p fasterdocker -f docker/compose.fast.yml down -v --remove-orphans
```

Single-image demo:

```bash
./docker/try.sh reset
```

## Benchmark

```bash
# Default dev/test bench profile
./docker/fast/benchmark.sh bench 5

# Production-like split profiles (optional comparison)
./docker/fast/benchmark.sh sql 5
./docker/fast/benchmark.sh physical 5
```

Results are written to `../../benchmarks/results.csv`.

## Configuration

Copy `.env.example` to `.env` and adjust variables:

```bash
cp docker/fast/.env.example .env
```

## Architecture

- **Runtime phase** does no install/build/migrate/network operations.
- **Bake phase** performs `bench init`, `bench new-site`, `install-app huf`, `migrate`, and frontend build.
- **Single-image demo** bundles a physical MariaDB snapshot so first boot only copies data into the volume.
- **Seed-init** uses atomic completion markers:
  - `.fasterdocker-seed-in-progress` is created at start.
  - Renamed to `.fasterdocker-seed-complete` on success.
  - If in-progress exists without complete, the next run fails closed.

## Notes

- The Administrator password is random per first boot (`./docker/try.sh creds`); the demo is still for local trial use only.
- Physical snapshots are pinned to the exact MariaDB image digest used at bake time.
- On Apple Silicon, `pysqlite3` is built from source because the binary wheel is x86_64-only.
