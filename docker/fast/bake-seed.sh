#!/usr/bin/env bash
# Build the seed image from bake output.
# Usage: ./docker/fast/bake-seed.sh [sql|physical]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/_lib.sh"

STRATEGY="${1:-sql}"
HUF_IMAGE_TAG="${HUF_IMAGE_TAG:-$(cd "${REPO_ROOT}" && git rev-parse --short HEAD)}"
MARIADB_IMAGE="${MARIADB_IMAGE:-mariadb:10.11.11}"
BAKE_OUTPUT="${SCRIPT_DIR}/.bake-output"

if [[ "${STRATEGY}" != "sql" && "${STRATEGY}" != "physical" ]]; then
  fatal "usage: $0 [sql|physical]"
fi

if [[ ! -f "${BAKE_OUTPUT}/metadata.json" ]]; then
  fatal "Bake output not found at ${BAKE_OUTPUT}. Run compose.bake.yml first."
fi

# Capture the exact MariaDB image digest used for the physical snapshot.
MARIADB_DIGEST=""
if command -v docker >/dev/null 2>&1; then
  MARIADB_DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "${MARIADB_IMAGE}" 2>/dev/null || true)"
fi

if [[ -n "${MARIADB_DIGEST}" ]]; then
  log "Captured MariaDB digest: ${MARIADB_DIGEST}"
  # Patch metadata.json in-place so the seed image carries the exact digest.
  if command -v jq >/dev/null 2>&1; then
    jq --arg digest "${MARIADB_DIGEST}" '.mariadb_digest = $digest' "${BAKE_OUTPUT}/metadata.json" > "${BAKE_OUTPUT}/metadata.json.tmp" \
      && mv "${BAKE_OUTPUT}/metadata.json.tmp" "${BAKE_OUTPUT}/metadata.json"
  else
    log "WARN: jq not available; cannot patch metadata.json with digest"
  fi
else
  log "WARN: could not capture MariaDB digest; physical snapshots may not be reproducible"
fi

SEED_IMAGE="huf-site-seed-${STRATEGY}:${HUF_IMAGE_TAG}"
log "Building seed image: ${SEED_IMAGE}"

docker build \
  -f "${SCRIPT_DIR}/Dockerfile.seed" \
  -t "${SEED_IMAGE}" \
  "${SCRIPT_DIR}"

log "Seed image built: ${SEED_IMAGE}"
