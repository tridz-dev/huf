#!/bin/bash
set -euo pipefail

# FasterDocker single-image demo entrypoint.
#
# Responsibilities:
#   1. Copy the baked physical MariaDB snapshot into the shared MariaDB volume
#      if it looks empty.
#   2. Copy the baked site folder into the sites volume if it is missing,
#      renaming it to SITE_NAME if the baked site was built under a different name.
#   3. Link baked assets into the sites volume.
#   4. Signal readiness via a marker file so the mariadb service can start.
#   5. Wait for MariaDB to be healthy.
#   6. On first boot only: rotate the baked demo credentials to fresh random
#      values (or honor explicit overrides) so the public image never ships a
#      live default password, then persist them for `try.sh creds`.
#   7. Drop to frappe and start bench.

SITE_NAME="${SITE_NAME:-huf.localhost}"
DB_HOST="${DB_HOST:-mariadb}"

# These are the values baked into the public demo image at build time
# (see docker/fast/bake-site.sh). They are ONLY used to authenticate the
# very first credential rotation below; they are never the credentials a
# running container ends up with.
BAKED_DEFAULT_ROOT_PASSWORD="fasterdocker-mysql-root"
BAKED_DEFAULT_ADMIN_PASSWORD="fasterdocker-admin"

DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-${BAKED_DEFAULT_ROOT_PASSWORD}}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-${BAKED_DEFAULT_ADMIN_PASSWORD}}"
HUF_PRODUCTION="${HUF_PRODUCTION:-0}"

MARIADB_DATA_DIR="/var/lib/mysql"
SNAPSHOT_DIR="/var/lib/mysql-snapshot"
SNAPSHOT_MARKER="${MARIADB_DATA_DIR}/.fasterdocker-snapshot-ready"

SITES_DIR="/home/frappe/frappe-bench/sites"
SEED_SITES_DIR="/seed/sites"
ASSETS_PATH="${SITES_DIR}/assets"
BAKED_ASSETS_PATH="/home/frappe/frappe-bench/assets"
CREDENTIALS_FILE="${SITES_DIR}/${SITE_NAME}/.fasterdocker-credentials"

log() { echo "[huf-demo] $*"; }

if [[ "$(id -u)" != "0" ]]; then
  log "ERROR: demo-entrypoint.sh must run as root to copy the MariaDB snapshot"
  exit 1
fi

# This image is a physical-snapshot trial/demo path, not a supported
# production deployment. If someone flags HUF_PRODUCTION anyway, refuse to
# boot unless the baked demo credentials have been explicitly overridden.
if [[ "${HUF_PRODUCTION}" == "1" || "${HUF_PRODUCTION}" == "true" ]]; then
  if [[ "${DB_ROOT_PASSWORD}" == "${BAKED_DEFAULT_ROOT_PASSWORD}" || "${ADMIN_PASSWORD}" == "${BAKED_DEFAULT_ADMIN_PASSWORD}" ]]; then
    log "ERROR: HUF_PRODUCTION=${HUF_PRODUCTION} but MARIADB_ROOT_PASSWORD/ADMIN_PASSWORD are still the published demo defaults."
    log "Set both to strong, unique values before running with HUF_PRODUCTION=1."
    log "Note: this single-image physical-snapshot demo is intended for local trial use, not production hosting."
    exit 1
  fi
fi

gen_secret() {
  head -c 33 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24
}

# Ensure the sites volume is frappe-writable.
mkdir -p "${SITES_DIR}"
chown -R frappe:frappe "${SITES_DIR}" || true

# Copy physical MariaDB snapshot if the volume appears empty.
FIRST_BOOT=0
if [[ ! -f "${MARIADB_DATA_DIR}/ibdata1" ]]; then
  FIRST_BOOT=1
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

# Copy the site folder into the sites volume if it is missing. The image is
# baked with one site folder (name recorded at bake time); if the caller set
# SITE_NAME to something else, rename the copied folder to match instead of
# failing, so the physical snapshot demo works under any site name.
if [[ ! -d "${SITES_DIR}/${SITE_NAME}" ]]; then
  BAKED_SITE_NAME="$(find "${SEED_SITES_DIR}" -mindepth 1 -maxdepth 1 -type d \
    ! -name assets -printf '%f\n' | head -n1 || true)"
  if [[ -z "${BAKED_SITE_NAME}" ]]; then
    log "ERROR: no baked site folder found under ${SEED_SITES_DIR}"
    exit 1
  fi
  log "Copying site folder (baked as '${BAKED_SITE_NAME}', target '${SITE_NAME}')..."
  cp -a "${SEED_SITES_DIR}/." "${SITES_DIR}/"
  if [[ "${BAKED_SITE_NAME}" != "${SITE_NAME}" ]]; then
    log "Renaming baked site '${BAKED_SITE_NAME}' -> '${SITE_NAME}'"
    mv "${SITES_DIR}/${BAKED_SITE_NAME}" "${SITES_DIR}/${SITE_NAME}"
  fi
  echo "${SITE_NAME}" > "${SITES_DIR}/currentsite.txt"
  chown -R frappe:frappe "${SITES_DIR}" || true
  log "Site folder ready as '${SITE_NAME}'."
fi

# Link baked assets into the sites volume.
rm -rf "${ASSETS_PATH}"
mkdir -p "$(dirname "${ASSETS_PATH}")"
ln -s "${BAKED_ASSETS_PATH}" "${ASSETS_PATH}"
chown -R frappe:frappe "${SITES_DIR}" || true

# The baked common_site_config.json contains bake-time hostnames (mariadb-bake,
# redis-*-bake from docker/compose.bake.yml). Rewrite it to point at this
# container's runtime services: DB_HOST (the "mariadb" compose service) and
# localhost Redis, since the demo image runs Redis in-process (see below).
cat > "${SITES_DIR}/common_site_config.json" <<EOF
{
  "db_host": "${DB_HOST}",
  "db_port": 3306,
  "redis_cache": "redis://localhost:6379",
  "redis_queue": "redis://localhost:6379",
  "redis_socketio": "redis://localhost:6379",
  "socketio_port": 9000,
  "developer_mode": 1
}
EOF
chown frappe:frappe "${SITES_DIR}/common_site_config.json"
log "Rewrote common_site_config.json for runtime services."

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

# First boot only: rotate the baked demo credentials so the public image
# never leaves a live default password in place. If the caller explicitly
# overrode ADMIN_PASSWORD / DB_ROOT_PASSWORD away from the baked defaults,
# honor those values instead of generating new ones.
if [[ "${FIRST_BOOT}" == "1" ]]; then
  if [[ "${DB_ROOT_PASSWORD}" == "${BAKED_DEFAULT_ROOT_PASSWORD}" ]]; then
    NEW_ROOT_PASSWORD="$(gen_secret)"
    log "Rotating MariaDB root password..."
    mysql -h "${DB_HOST}" -uroot -p"${DB_ROOT_PASSWORD}" \
      -e "ALTER USER 'root'@'%' IDENTIFIED BY '${NEW_ROOT_PASSWORD}'; FLUSH PRIVILEGES;"
    DB_ROOT_PASSWORD="${NEW_ROOT_PASSWORD}"
  else
    log "MARIADB_ROOT_PASSWORD explicitly set; keeping caller-supplied value."
  fi

  if [[ "${ADMIN_PASSWORD}" == "${BAKED_DEFAULT_ADMIN_PASSWORD}" ]]; then
    NEW_ADMIN_PASSWORD="$(gen_secret)"
    log "Rotating Administrator password..."
    setpriv --reuid=frappe --regid=frappe --clear-groups -- bash -c \
      "cd /home/frappe/frappe-bench && bench --site '${SITE_NAME}' set-admin-password '${NEW_ADMIN_PASSWORD}'"
    ADMIN_PASSWORD="${NEW_ADMIN_PASSWORD}"
  else
    log "ADMIN_PASSWORD explicitly set; keeping caller-supplied value."
  fi

  cat > "${CREDENTIALS_FILE}" <<EOF
# Generated on first boot by demo-entrypoint.sh. Read via: ./try.sh creds
SITE_NAME=${SITE_NAME}
ADMIN_USER=Administrator
ADMIN_PASSWORD=${ADMIN_PASSWORD}
MARIADB_ROOT_PASSWORD=${DB_ROOT_PASSWORD}
EOF
  chmod 600 "${CREDENTIALS_FILE}"
  chown frappe:frappe "${CREDENTIALS_FILE}"

  log "============================================================"
  log " First boot complete. Login credentials (also saved to"
  log " sites/${SITE_NAME}/.fasterdocker-credentials, run ./try.sh creds):"
  log "   URL:            http://localhost:${BENCH_WEB_PUBLISH_PORT:-8000}/${APP_NAME:-huf}"
  log "   Administrator:  ${ADMIN_PASSWORD}"
  log "============================================================"
fi

# Drop to frappe and start bench.
exec setpriv --reuid=frappe --regid=frappe --clear-groups -- "$@"
