# FasterDocker Fast Boot Setup

This directory contains the Docker assets for warm-booting HUF on Frappe v16.25.0.

## Container contract

Only these container name prefixes are used:

- `fasterdocker-build-*`
- `fasterdocker-seed-*`
- `fasterdocker-run-*`

All `docker compose` commands must use project name `fasterdocker`.

## Images

| Image | Purpose |
|-------|---------|
| `huf-frappe-runtime:16.25.0` | Base Frappe v16.25.0 runtime with Python/Node/toolchain |
| `huf-app:<sha>` | HUF app + built frontend assets |
| `huf-site-seed-sql:<sha>` | SQL dump + sites folder + metadata |
| `huf-site-seed-physical:<sha>` | Physical `/var/lib/mysql` snapshot + sites + metadata |

## Profiles

| Profile | Compose file | Use case |
|---------|--------------|----------|
| **bench** (default dev/test) | `docker/compose.bench.yml` | One container running `bench start` + MariaDB + Redis. Fastest local/test path. |
| split SQL | `docker/compose.fast.yml` | Production-like split web/worker/scheduler/socketio/nginx containers with SQL seed. |
| split physical | `docker/compose.fast-physical.yml` | Same split layout using a physical MariaDB snapshot. |

## Quick start (bench profile)

Set the image tag:

```bash
export HUF_IMAGE_TAG=$(git rev-parse --short HEAD)
```

### 1. Build runtime and app images

```bash
docker build -f docker/fast/Dockerfile.runtime -t huf-frappe-runtime:16.25.0 .
docker build -f docker/fast/Dockerfile.huf -t huf-app:${HUF_IMAGE_TAG} .
```

### 2. Bake site seed

SQL seed (used by the bench profile):

```bash
docker compose -p fasterdocker -f docker/compose.bake.yml up --build
./docker/fast/bake-seed.sh sql
```

Physical snapshot seed (optional):

```bash
docker compose -p fasterdocker -f docker/compose.bake.yml up --build
./docker/fast/bake-seed.sh physical
```

### 3. Run warm boot

Bench profile (default):

```bash
docker compose -p fasterdocker -f docker/compose.bench.yml up --wait
```

The bench web port is exposed directly:

```bash
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
```

Production-like split SQL mode:

```bash
docker compose -p fasterdocker -f docker/compose.fast.yml up --wait
```

Physical mode:

```bash
docker compose -p fasterdocker -f docker/compose.fast-physical.yml up --wait
```

### 4. Reset to seeded first start

Bench profile:

```bash
docker compose -p fasterdocker -f docker/compose.bench.yml down -v --remove-orphans
```

Split profile:

```bash
docker compose -p fasterdocker -f docker/compose.fast.yml down -v --remove-orphans
```

### 5. Benchmark

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
- **Seed-init** uses atomic completion markers:
  - `.fasterdocker-seed-in-progress` is created at start.
  - Renamed to `.fasterdocker-seed-complete` on success.
  - If in-progress exists without complete, the next run fails closed.

## Notes

- Default credentials are demo-only and insecure: `Administrator` / `fasterdocker-admin`.
- Physical snapshots are pinned to the exact MariaDB image digest used at bake time.
- On Apple Silicon, pysqlite3 is built from source because the binary wheel is x86_64-only.
