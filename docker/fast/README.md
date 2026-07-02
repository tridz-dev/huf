# FasterDocker Fast Boot Setup

This directory contains the Docker assets for warm-booting HUF on Frappe v16.25.0.

The fastest way for end users to try HUF is the single-image demo in [`docker/docker-compose.yml`](../docker-compose.yml):

```bash
git clone https://github.com/tridz-dev/huf.git
cd huf/docker
docker compose up --wait
```

Then open http://localhost:8000/huf.

There is no local build, `bench init`, `new-site`, `install-app`, or seed step once the published image is available.

## Platform support

The demo image is intended to be published for both `linux/amd64` (Intel/AMD Linux) and `linux/arm64` (Apple Silicon Linux containers). The physical MariaDB snapshot baked into the image is architecture-specific, so each architecture is built separately and assembled into a single multi-arch manifest list.

- **macOS with Apple Silicon**: tested locally with OrbStack.
- **Intel/AMD Linux**: Dockerfile and build scripts were verified to build successfully for `linux/amd64` via cross-platform build on the Apple Silicon host. Runtime testing on Intel hardware is pending CI execution.
- **Windows**: not tested; WSL2 with Docker should work if the WSL distro is `linux/amd64`.

Override the platform explicitly if needed:

```bash
export DOCKER_PLATFORM=linux/amd64   # or linux/arm64
docker compose up --wait
```

## Prebuilt image

Once CI publishes it, the compose file uses:

```text
ghcr.io/tridz-dev/huf-demo:<sha>
```

Until then, build locally (see [Building locally](#building-locally)).

## Quick start (single-image demo)

```bash
cd huf/docker

# If the prebuilt image is not yet published, point to a locally built image:
export HUF_DEMO_IMAGE=huf-demo
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)

docker compose up --wait
```

Health checks:

```bash
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
```

Log in at http://localhost:8000/huf:

- **User:** `Administrator`
- **Password:** `fasterdocker-admin`

The image ships with a disabled **Demo Assistant** agent and a **Demo Assistant Prompt** so you can see HUF's AI layer immediately. Enable the agent and add your OpenAI API key to start chatting.

Restart only the app (keeps the MariaDB volume):

```bash
docker compose restart frappe
```

Full reset (back to seeded first start):

```bash
docker compose down -v --remove-orphans
docker compose up --wait
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

```bash
cd docker
export HUF_DEMO_IMAGE=huf-demo
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
docker compose up --wait
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
cd docker
docker compose down -v --remove-orphans
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

- Default credentials are demo-only and insecure: `Administrator` / `fasterdocker-admin`.
- Physical snapshots are pinned to the exact MariaDB image digest used at bake time.
- On Apple Silicon, `pysqlite3` is built from source because the binary wheel is x86_64-only.
