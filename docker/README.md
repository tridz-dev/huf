# HUF Docker quick start

## What is this?

This directory is the **FasterDocker demo and development environment for HUF**.
It provides a pull-and-run prebuilt demo image for quick local evaluation, plus
several compose variants for deeper development work (production-parity SQL seed
restore, fastest cold-boot physical snapshots, and a single `bench start`
container). The fastest path is the `demo` variant; the other variants are aimed
at developers who want to build images locally or test specific boot strategies.

## Prerequisites

- **Docker Engine >= 20.10.13** with the Compose V2 plugin (`docker compose`).
  The compose files use the Compose specification format and `docker compose up --wait`;
  the legacy `docker-compose` Python CLI is not required.
- The `demo` variant's image is intended to be **multi-architecture**
  (`linux/amd64` and `linux/arm64`) built with **native per-architecture
  runners**, not QEMU emulation. This is required because the demo image
  bakes a physical MariaDB snapshot, and MariaDB's on-disk data format is
  architecture-specific.
  Published tags are listed on the GHCR package page for `tridz-dev/huf-demo`.
  CI publishes both `amd64` and `arm64`, each built on a native runner.
  Never emulate the other architecture: the physical MariaDB snapshot is arch-specific.
  Set `DOCKER_PLATFORM` only to force the native architecture.

## Quick start

```bash
git clone https://github.com/tridz-dev/huf.git && cd huf && ./docker/try.sh up
```

`up` waits for the stack to be healthy (about a minute from a pulled image;
timeout is `HUF_WAIT_SECONDS`, default 300). Then open
`http://localhost:8000/huf` and sign in as `Administrator`. The password is
random per first boot and is shown in the banner. Reprint it any time with:

```bash
./docker/try.sh creds
```

The demo and legacy paths run published GitHub code, not your local checkout.
To test local changes, build the images locally and use `--variant bench`
(see `docker/fast/README.md`).

The demo ships a Demo Assistant agent; add a Google AI provider API key in the
UI before it answers. Health checks:

```bash
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/api/method/ping
curl -fsS -H 'Host: huf.localhost' http://localhost:8000/huf
```

## Common commands

```bash
./docker/try.sh                       # same as "up" with the demo variant
./docker/try.sh --variant demo        # prebuilt single-image demo (default)
./docker/try.sh --variant fast        # production-parity SQL seed restore
./docker/try.sh --variant fast-physical  # fastest cold boot (physical snapshot)
./docker/try.sh --variant bench       # single bench-start container (needs local images)
./docker/try.sh down                  # stop the stack
./docker/try.sh reset                 # stop and remove volumes; next up re-seeds
./docker/try.sh logs                  # tail all logs
./docker/try.sh logs frappe           # tail logs for a specific service
./docker/try.sh status                # show containers, health, and ports
./docker/try.sh creds                 # reprint the saved admin credentials
```

Run `./docker/try.sh --help` for the full flag list, including port overrides,
custom `.env` files, and `--dry-run`.

## Credentials & security model

The demo image has **placeholder build-time credentials** that exist only so the
image can be built. They are never what you log in with:

- MariaDB root password: `fasterdocker-mysql-root`
- Frappe Administrator password: `fasterdocker-admin`

These values are **never the credentials a running container ends up with** on
first boot. `docker/fast/demo-entrypoint.sh` detects a first boot by checking
whether the MariaDB data directory is empty (`ibdata1` is absent). On first boot
it rotates the baked defaults to fresh random values:

- `gen_secret()` reads 33 bytes from `/dev/urandom`, base64-encodes them, and
  strips non-alphanumeric characters to produce a 24-character password.
- If `ADMIN_PASSWORD` was not explicitly overridden, the script runs
  `bench --site <SITE_NAME> set-admin-password <new_random_password>`.
- If `MARIADB_ROOT_PASSWORD` was not explicitly overridden, the script runs
  `ALTER USER 'root'@'%' IDENTIFIED BY '<new_random_password>'; FLUSH PRIVILEGES;`
  via the original baked root password.
- The final credentials are written to
  `sites/<SITE_NAME>/.fasterdocker-credentials` with `chmod 600` and ownership
  set to `frappe:frappe`.

On subsequent boots the existing volume is reused, the rotation step is skipped,
and `try.sh creds` reads the persisted file from the running `frappe` container.

If you explicitly set `ADMIN_PASSWORD`, the rotation logic honors your value
instead of generating a new one. Do not override `MARIADB_ROOT_PASSWORD` with the
single-image demo: the baked database keeps its original root password, so a
different value would not match.

The entrypoint also refuses to run in a production context. If `HUF_PRODUCTION`
is set to `1` or `true` and either password is still the baked default, the
script exits with an error before starting services. This single-image physical-
snapshot path is intended for local trial and development only.

## Port conflicts

By default, `try.sh` checks whether the published ports are free and
automatically remaps to the next available port up to +99 from the default:

| Variant         | Default ports checked                              |
|-----------------|----------------------------------------------------|
| demo            | `BENCH_WEB_PUBLISH_PORT=8000`, `BENCH_SOCKETIO_PUBLISH_PORT=9000` |
| bench           | `BENCH_WEB_PUBLISH_PORT=8000`, `BENCH_SOCKETIO_PUBLISH_PORT=9000` |
| fast            | `FRONTEND_PUBLISH_PORT=8080`                       |
| fast-physical   | `FRONTEND_PUBLISH_PORT=8080`                       |

Use `--no-port-remap` to fail instead of remapping.

## Variants

- **demo** (`docker/docker-compose.yml`): pulls the prebuilt
  `ghcr.io/tridz-dev/huf-demo:${HUF_IMAGE_TAG:-latest}` image (`latest` is the most
  recent promoted build: a stable `vX.Y.Z` release or a manual publish with `promote_latest`. The `develop` tag tracks the develop branch tip, so use
  `--tag develop` for it. `<sha>`, `<sha>-amd64`, `<sha>-arm64` also exist). No local build required.
- **bench** (`docker/compose.bench.yml`): a single `bench start` container plus
  MariaDB/Redis. Requires a local `huf-app` image.
- **fast** (`docker/compose.fast.yml`): split services with SQL seed restore.
- **fast-physical** (`docker/compose.fast-physical.yml`): split services using a
  physical MariaDB snapshot for the fastest cold boot.

For local builds and advanced fasterdocker techniques, see
`docker/fast/README.md` and `docker/FASTERDOCKER_TECHNIQUES.md`.

## Generator reference config

`docker/ffast.yaml` is a reference config for `ffast`, a Frappe Docker/Compose
generator that is not published yet. The demo files (`docker-compose.yml`,
`fast/demo-entrypoint.sh`, `try.sh`) are checked in directly and maintained by
hand; there is nothing to install. The `bench`/`fast`/`fast-physical` variants
are hand-maintained too.

CI publishes the demo image with `.github/workflows/fasterdocker-publish.yml`,
using native `ubuntu-latest` (amd64) and `ubuntu-24.04-arm` (arm64) runners plus
a manifest-list job, because the physical-snapshot image must not be built under
QEMU.

## Legacy single-container setup

`docker/docker-compose.legacy.yml` and `docker/init.sh` are the superseded
runtime bench-init path. They clone Frappe `develop` at startup and are slow
(minutes, not seconds). Prefer `./docker/try.sh up`.
