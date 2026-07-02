#!/bin/bash
set -euo pipefail

# FasterDocker single-image demo entrypoint.
#
# Responsibilities:
#   1. Copy the baked physical MariaDB snapshot into the shared MariaDB volume
#      if it looks empty.
#   2. Copy the baked site folder into the sites volume if it is missing.
#   3. Link baked assets into the sites volume.
#   4. Signal readiness via a marker file so the mariadb service can start.
#   5. Wait for MariaDB to be healthy.
#   6. Drop to frappe and start bench.

SITE_NAME="${SITE_NAME:-huf.localhost}"
DB_HOST="${DB_HOST:-mariadb}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-fasterdocker-mysql-root}"

MARIADB_DATA_DIR="/var/lib/mysql"
SNAPSHOT_DIR="/var/lib/mysql-snapshot"
SNAPSHOT_MARKER="${MARIADB_DATA_DIR}/.fasterdocker-snapshot-ready"

SITES_DIR="/home/frappe/frappe-bench/sites"
SEED_SITES_DIR="/seed/sites"
ASSETS_PATH="${SITES_DIR}/assets"
BAKED_ASSETS_PATH="/home/frappe/frappe-bench/assets"

log() { echo "[huf-demo] $*"; }

if [[ "$(id -u)" != "0" ]]; then
  log "ERROR: demo-entrypoint.sh must run as root to copy the MariaDB snapshot"
  exit 1
fi

# Ensure the sites volume is frappe-writable.
mkdir -p "${SITES_DIR}"
chown -R frappe:frappe "${SITES_DIR}" || true

# Copy physical MariaDB snapshot if the volume appears empty.
if [[ ! -f "${MARIADB_DATA_DIR}/ibdata1" ]]; then
  log "Copying physical MariaDB snapshot..."
  mkdir -p "${MARIADB_DATA_DIR}"
  cp -a "${SNAPSHOT_DIR}/." "${MARIADB_DATA_DIR}/"
  chown -R 999:999 "${MARIADB_DATA_DIR}"
  touch "${SNAPSHOT_MARKER}"
  log "Physical snapshot copied."
else
  log "Existing MariaDB data found; skipping snapshot copy."
  touch "${SNAPSHOT_MARKER}"
fi

# Copy the site folder into the sites volume if it is missing.
if [[ ! -d "${SITES_DIR}/${SITE_NAME}" ]]; then
  if [[ -d "${SEED_SITES_DIR}/${SITE_NAME}" ]]; then
    log "Copying site folder..."
    cp -a "${SEED_SITES_DIR}/." "${SITES_DIR}/"
    chown -R frappe:frappe "${SITES_DIR}" || true
    log "Site folder copied."
  else
    log "ERROR: site folder not found at ${SEED_SITES_DIR}/${SITE_NAME}"
    exit 1
  fi
fi

# Link baked assets into the sites volume.
rm -rf "${ASSETS_PATH}"
mkdir -p "$(dirname "${ASSETS_PATH}")"
ln -s "${BAKED_ASSETS_PATH}" "${ASSETS_PATH}"
chown -R frappe:frappe "${SITES_DIR}" || true

# Start Redis inside this container (no separate redis service).
log "Starting Redis..."
redis-server --daemonize yes

# Wait for Redis.
waited=0
until redis-cli ping | grep -q PONG; do
  if (( waited > 30 )); then
    log "ERROR: Redis did not start within 30 seconds"
    exit 1
  fi
  sleep 1
  ((waited+=1))
done
log "Redis is ready."

# Wait for MariaDB.
log "Waiting for MariaDB at ${DB_HOST}:3306..."
waited=0
until mysqladmin ping -h "${DB_HOST}" --silent 2>/dev/null; do
  if (( waited > 120 )); then
    log "ERROR: MariaDB did not become ready within 120 seconds"
    exit 1
  fi
  sleep 2
  ((waited+=2))
done
log "MariaDB is ready."

# Drop to frappe and start bench.
exec setpriv --reuid=frappe --regid=frappe --clear-groups -- "$@"
