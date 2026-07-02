#!/usr/bin/env bash
# Build the single-image HUF demo (huf-demo) with a physical MariaDB snapshot.
#
# Usage:
#   ./docker/fast/build-demo.sh
#
# This script:
#   1. Builds the huf-app image (if HUF_IMAGE_TAG is not already local).
#   2. Starts a temporary MariaDB container.
#   3. Restores the bundled SQL dump from the huf-app image into MariaDB.
#   4. Stops MariaDB cleanly.
#   5. Copies /var/lib/mysql into docker/fast/mysql-data/.
#   6. Builds the huf-demo image with the snapshot baked in.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/_lib.sh"

HUF_IMAGE_TAG="${HUF_IMAGE_TAG:-$(cd "${REPO_ROOT}" && git rev-parse --short HEAD)}"
export HUF_IMAGE_TAG

HUF_APP_IMAGE="${HUF_APP_IMAGE:-huf-app}"
DEMO_IMAGE="${DEMO_IMAGE:-huf-demo}"
MARIADB_IMAGE="${MARIADB_IMAGE:-mariadb:10.11.11}"
SITE_NAME="${SITE_NAME:-huf.localhost}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-fasterdocker-mysql-root}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-fasterdocker-admin}"

SNAPSHOT_DIR="${SCRIPT_DIR}/mysql-data"
PROJECT_NAME="fasterdocker-build"

log "Building ${DEMO_IMAGE}:${HUF_IMAGE_TAG}"
log "HUF app image: ${HUF_APP_IMAGE}:${HUF_IMAGE_TAG}"
log "MariaDB image: ${MARIADB_IMAGE}"

# Step 1: ensure huf-app image exists.
if ! docker image inspect "${HUF_APP_IMAGE}:${HUF_IMAGE_TAG}" >/dev/null 2>&1; then
  log "Building huf-app image..."
  docker build \
    -f "${SCRIPT_DIR}/Dockerfile.huf" \
    -t "${HUF_APP_IMAGE}:${HUF_IMAGE_TAG}" \
    "${REPO_ROOT}"
else
  log "Using existing ${HUF_APP_IMAGE}:${HUF_IMAGE_TAG}"
fi

# Step 2: clean up any previous build containers/volumes.
log "Cleaning up previous demo build resources..."
docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" down -v --remove-orphans 2>/dev/null || true

# Step 3: start MariaDB for snapshot generation.
log "Starting temporary MariaDB..."
export MARIADB_IMAGE SITE_NAME DB_ROOT_PASSWORD ADMIN_PASSWORD HUF_APP_IMAGE HUF_IMAGE_TAG
docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" up -d mariadb

# Wait for MariaDB health.
log "Waiting for MariaDB to be healthy..."
waited=0
while ! docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" ps mariadb | grep -q "healthy"; do
  if (( waited > 120 )); then
    fatal "MariaDB did not become healthy within 120 seconds"
  fi
  sleep 2
  ((waited+=2))
done
log "MariaDB is healthy."

# Step 4: restore SQL dump into MariaDB.
log "Restoring SQL dump into temporary MariaDB..."
docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" run --rm seed-restore

# Step 5: stop MariaDB cleanly so the data files are consistent.
log "Stopping MariaDB cleanly..."
docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" stop mariadb

# Step 6: copy /var/lib/mysql to host.
log "Copying MariaDB data to ${SNAPSHOT_DIR}..."
rm -rf "${SNAPSHOT_DIR}"
mkdir -p "${SNAPSHOT_DIR}"

# Find the MariaDB container name. compose.demo-build.yml sets container_name
# explicitly, so we use that instead of the generated name.
MARIADB_CONTAINER="fasterdocker-build-demo-mariadb"
docker cp "${MARIADB_CONTAINER}:/var/lib/mysql/." "${SNAPSHOT_DIR}/"

# Remove logs and temporary files that should not be baked.
rm -f "${SNAPSHOT_DIR}"/*.log "${SNAPSHOT_DIR}"/*.err "${SNAPSHOT_DIR}"/*.pid 2>/dev/null || true

# Step 7: remove temporary build resources.
log "Removing temporary demo build resources..."
docker compose -p "${PROJECT_NAME}" -f "${SCRIPT_DIR}/compose.demo-build.yml" down -v --remove-orphans

# Step 8: build huf-demo image.
log "Building ${DEMO_IMAGE}:${HUF_IMAGE_TAG}..."
docker build \
  -f "${SCRIPT_DIR}/Dockerfile.demo" \
  --build-arg "HUF_APP_IMAGE=${HUF_APP_IMAGE}" \
  --build-arg "HUF_IMAGE_TAG=${HUF_IMAGE_TAG}" \
  -t "${DEMO_IMAGE}:${HUF_IMAGE_TAG}" \
  "${REPO_ROOT}"

log "Built ${DEMO_IMAGE}:${HUF_IMAGE_TAG}"
log "To run locally: cd ${REPO_ROOT}/docker && docker compose up"
