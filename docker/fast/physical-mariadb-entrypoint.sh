#!/usr/bin/env bash
# MariaDB entrypoint for physical snapshot mode.
# Copies the baked /var/lib/mysql snapshot into the empty named volume before
# starting mysqld. The seed image supplies /seed/mysql-data/.

set -euo pipefail

SEED_SOURCE_DIR="${SEED_SOURCE_DIR:-/seed}"
MYSQL_DATA_DIR="${MYSQL_DATA_DIR:-/var/lib/mysql}"
MARKER="${MYSQL_DATA_DIR}/.fasterdocker-seed-complete"

log() { echo "[fasterdocker-mariadb] $*"; }

# If the volume already has data, start mysqld normally.
if [[ -f "${MYSQL_DATA_DIR}/mysql/db.MAD" || -d "${MYSQL_DATA_DIR}/mysql" || -f "${MARKER}" ]]; then
  log "Existing MariaDB data found; starting mysqld."
  exec /usr/local/bin/docker-entrypoint.sh "$@"
fi

if [[ ! -d "${SEED_SOURCE_DIR}/mysql-data" ]]; then
  log "ERROR: physical snapshot /seed/mysql-data/ not found"
  exit 1
fi

log "Copying physical /var/lib/mysql snapshot..."
cp -a "${SEED_SOURCE_DIR}/mysql-data/." "${MYSQL_DATA_DIR}/"
chown -R mysql:mysql "${MYSQL_DATA_DIR}" 2>/dev/null || true
touch "${MARKER}"
log "Physical snapshot ready; starting mysqld."

exec /usr/local/bin/docker-entrypoint.sh "$@"
