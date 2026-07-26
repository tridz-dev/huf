<!--
  Superseded notice: this README documents the current fasterdocker multi-service
  compose stack. The legacy single-container setup still exists in this directory
  as docker-compose.legacy.yml and init.sh, but is no longer the recommended path.
-->

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
  > **Current status:** `ghcr.io/tridz-dev/huf-demo:9c6817b-arm64` is a
  > freshly rebuilt, locally-verified native arm64 image containing the
  > credential-rotation and `common_site_config.json` fixes from this pass.
  > The matching native amd64 build (via `.github/workflows/fasterdocker-publish.yml`
  > on `ubuntu-latest`) has not run yet — that workflow only becomes
  > dispatchable once this branch is merged to `develop` (GitHub requires
  > `workflow_dispatch` workflows to exist on the default branch to be
  > triggered remotely). Until the merge + manifest run happens, `:latest`
  > still points at the older, pre-fix image; pin `--tag 9c6817b-arm64`
  > explicitly on arm64 machines if you want the fixed image now.
  `DOCKER_PLATFORM` can be set to force a specific architecture if your local
  engine supports it.

## Quick start

```bash
./docker/try.sh up
```

Then open the URL printed by the script (default: `http://localhost:8000/huf`).
Login credentials are shown in the banner and can be reprinted at any time with:

```bash
./docker/try.sh creds
```

## Common commands

```bash
./docker/try.sh                       # same as "up" with the demo variant
./docker/try.sh --variant demo        # prebuilt single-image demo (default)
./docker/try.sh --variant fast        # production-parity SQL seed restore
./docker/try.sh --variant fast-physical  # fastest cold boot (physical snapshot)
./docker/try.sh --variant bench       # single bench-start container
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

The demo image ships with **placeholder default credentials** baked in at build
time so the container can boot without user input:

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

If you explicitly set `ADMIN_PASSWORD` or `MARIADB_ROOT_PASSWORD`, the rotation
logic honors your value instead of generating a new one.

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
  `ghcr.io/tridz-dev/huf-demo` image. No local build required.
- **bench** (`docker/compose.bench.yml`): a single `bench start` container plus
  MariaDB/Redis. Requires a local `huf-app` image.
- **fast** (`docker/compose.fast.yml`): split services with SQL seed restore.
- **fast-physical** (`docker/compose.fast-physical.yml`): split services using a
  physical MariaDB snapshot for the fastest cold boot.

For local builds and advanced fasterdocker techniques, see
`docker/fast/README.md` and `docker/FASTERDOCKER_TECHNIQUES.md`.

## Generator provenance

The `demo` variant's `docker-compose.yml`, `fast/demo-entrypoint.sh`, `try.sh`,
and `fast/.env.example` are generated from `docker/ffast.yaml` by
[ffast](https://github.com/OWNER/ffast), a standalone Frappe Docker/Compose
generator extracted from this project's patterns. They are currently checked in
directly (ffast is not yet published to PyPI); `docker/ffast.yaml` is kept in
sync as the config that reproduces them. The `bench`/`fast`/`fast-physical`
variants are not yet templatized and remain hand-maintained.

### Installing ffast as a dev dependency

`ffast` is a **developer tool**, not a runtime dependency of the HUF Frappe app.
Install it once for local development with:

```bash
pip install ffast
```

It is intentionally **not** wired into `huf/hooks.py` as a `bench_commands`
entry. Frappe eagerly imports every app's `bench_commands` module list on every
`bench` invocation; adding an uninstalled package there would break `bench` for
any user who has HUF installed but has not installed `ffast`. Keeping ffast as a
standalone dev tool avoids that coupling.

`ffast` works the same way for Docker-based and bare-metal bench setups: it only
generates config files (Compose, entrypoint, helper scripts, and optionally a
`.github/workflows/publish-demo-image.yml` template). Running `ffast generate`
does not require Docker; building and pushing the generated image is a separate
step performed by the generated workflow or by local `docker` commands.

### GitHub Actions path

A reusable workflow template is included in the ffast generator at
`src/ffast/templates/demo/publish-demo-image.yml.j2`; when rendered it produces
`.github/workflows/publish-demo-image.yml` in the target project. That generated
workflow builds and pushes the demo image. HUF's own repository currently does
**not** contain a file generated from that template under
`.github/workflows/`; instead it contains a hand-maintained
`.github/workflows/fasterdocker-publish.yml` that uses native `ubuntu-latest`
(amd64) and `ubuntu-24.04-arm` (arm64) runners plus a manifest-list job, because
the physical-snapshot demo image must not be built with QEMU emulation.

## Legacy single-container setup

The files `docker/docker-compose.legacy.yml` and `docker/init.sh` are the legacy
single-container Docker setup. They are superseded by the fasterdocker
multi-service compose stack documented in this file (see
`docker/compose.fast.yml`). This legacy setup will be moved to a
`backup/docker-single-container-legacy` branch and may be removed from `main` in the
future.
