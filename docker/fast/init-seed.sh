#!/usr/bin/env bash
# FasterDocker seed-init entrypoint.
# Supports SEED_STRATEGY=sql and SEED_STRATEGY=physical.
# Uses atomic fail-closed completion markers.

set -euo pipefail

SEED_STRATEGY="${SEED_STRATEGY:-sql}"
SITE_NAME="${SITE_NAME:-huf.localhost}"
SEED_SOURCE_DIR="${SEED_SOURCE_DIR:-/seed}"
SEED_TARGET_DIR="${SEED_TARGET_DIR:-/seed-target}"
DB_HOST="${DB_HOST:-mariadb}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-fasterdocker-mysql-root}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-fasterdocker-admin}"

SITES_TARGET="${SEED_TARGET_DIR}/sites"
MARKER_DIR="${SITES_TARGET}"
IN_PROGRESS="${MARKER_DIR}/.fasterdocker-seed-in-progress"
COMPLETE="${MARKER_DIR}/.fasterdocker-seed-complete"

log() { echo "[fasterdocker-seed-init] $*"; }

fail_closed() {
  log "ERROR: incomplete seed marker found at ${IN_PROGRESS}"
  log "A previous seed attempt did not complete. Manual cleanup is required."
  exit 1
}

log "Strategy: ${SEED_STRATEGY}"
log "Site: ${SITE_NAME}"

mkdir -p "${SITES_TARGET}"

# Fail-closed check.
if [[ -f "${IN_PROGRESS}" && ! -f "${COMPLETE}" ]]; then
  fail_closed
fi

# Idempotency: if complete marker exists, do nothing.
if [[ -f "${COMPLETE}" ]]; then
  log "Seed complete marker found; skipping restore."
  exit 0
fi

# Begin seed operation atomically.
touch "${IN_PROGRESS}"

cleanup_in_progress() {
  # On failure we leave the in-progress marker to trigger fail-closed next run.
  log "Seed operation did not complete successfully."
}
trap cleanup_in_progress EXIT

# Rewrite common_site_config.json with runtime service names.
# The baked copy contains bake-time hostnames (mariadb-bake, redis-*-bake).
rewrite_common_site_config() {
  config_file="${SITES_TARGET}/common_site_config.json"
  mkdir -p "$(dirname "${config_file}")"
  cat > "${config_file}" <<EOF
{
  "db_host": "${DB_HOST}",
  "db_port": 3306,
  "redis_cache": "redis://redis-cache:6379",
  "redis_queue": "redis://redis-queue:6379",
  "redis_socketio": "redis://redis-socketio:6379",
  "socketio_port": 9000,
  "developer_mode": 1
}
EOF
  log "Rewrote common_site_config.json for runtime services."
}

# Copy sites folder for both strategies.
if [[ -d "${SEED_SOURCE_DIR}/sites" ]]; then
  log "Copying sites folder..."
  cp -a "${SEED_SOURCE_DIR}/sites/." "${SITES_TARGET}/"
fi

# Rewrite common_site_config.json after copying so runtime service names win.
rewrite_common_site_config

# Validate metadata for physical snapshots.
if [[ "${SEED_STRATEGY}" == "physical" ]]; then
  METADATA="${SEED_SOURCE_DIR}/metadata.json"
  if [[ ! -f "${METADATA}" ]]; then
    log "ERROR: metadata.json missing in seed image"
    exit 1
  fi

  CURRENT_DIGEST=""
  if command -v docker >/dev/null 2>&1; then
    # Best-effort: inspect the running MariaDB container's image digest.
    # This only works inside a sibling container with docker socket access.
    CURRENT_DIGEST="$(docker inspect "${DB_HOST}" --format='{{index .RepoDigests 0}}' 2>/dev/null || true)"
  fi

  SEED_DIGEST="$(jq -r '.mariadb_digest // ""' "${METADATA}")"
  SEED_ARCH="$(jq -r '.architecture // ""' "${METADATA}")"
  CURRENT_ARCH="$(uname -m)"

  if [[ -n "${SEED_ARCH}" && "${SEED_ARCH}" != "${CURRENT_ARCH}" ]]; then
    log "ERROR: seed architecture mismatch: seed=${SEED_ARCH} current=${CURRENT_ARCH}"
    exit 1
  fi

  if [[ -n "${SEED_DIGEST}" && -n "${CURRENT_DIGEST}" ]]; then
    if [[ "${CURRENT_DIGEST}" != "${SEED_DIGEST}" ]]; then
      log "ERROR: MariaDB digest mismatch. Seed: ${SEED_DIGEST} Running: ${CURRENT_DIGEST}"
      log "Regenerate the physical snapshot with the current MariaDB image."
      exit 1
    fi
  fi
fi

# Strategy-specific database restoration.
if [[ "${SEED_STRATEGY}" == "sql" ]]; then
  SQL_FILE="${SEED_SOURCE_DIR}/sql/${SITE_NAME}.sql.gz"
  if [[ ! -f "${SQL_FILE}" ]]; then
    log "ERROR: SQL dump not found: ${SQL_FILE}"
    exit 1
  fi

  SITE_CONFIG="${SITES_TARGET}/${SITE_NAME}/site_config.json"
  if [[ ! -f "${SITE_CONFIG}" ]]; then
    log "ERROR: site_config.json not found at ${SITE_CONFIG}"
    exit 1
  fi

  DB_NAME="$(jq -r '.db_name // empty' "${SITE_CONFIG}")"
  DB_PASSWORD="$(jq -r '.db_password // empty' "${SITE_CONFIG}")"
  if [[ -z "${DB_NAME}" || -z "${DB_PASSWORD}" ]]; then
    log "ERROR: could not read db_name or db_password from ${SITE_CONFIG}"
    exit 1
  fi
  log "Frappe database name: ${DB_NAME}"

  log "Waiting for MariaDB at ${DB_HOST}:3306..."
  waited=0
  while ! mysqladmin ping -h "${DB_HOST}" --silent 2>/dev/null; do
    if (( waited > 120 )); then
      log "ERROR: MariaDB did not become ready within 120 seconds"
      exit 1
    fi
    sleep 2
    ((waited+=2))
  done

  log "Creating database, user and grants..."
  mysql -h "${DB_HOST}" -u root -p"${DB_ROOT_PASSWORD}" <<EOF
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_NAME}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_NAME}'@'%';
FLUSH PRIVILEGES;
EOF

  log "Restoring SQL dump..."
  zcat "${SQL_FILE}" | mysql -h "${DB_HOST}" -u root -p"${DB_ROOT_PASSWORD}" "${DB_NAME}"
  log "SQL restore complete."

elif [[ "${SEED_STRATEGY}" == "physical" ]]; then
  PHYSICAL_COPY_MYSQL_DATA="${PHYSICAL_COPY_MYSQL_DATA:-true}"
  if [[ "${PHYSICAL_COPY_MYSQL_DATA}" == "true" ]]; then
    MYSQL_TARGET="${SEED_TARGET_DIR}/mysql-data"
    if [[ ! -d "${SEED_SOURCE_DIR}/mysql-data" ]]; then
      log "ERROR: physical mysql-data snapshot not found in seed image"
      exit 1
    fi
    log "Copying physical MariaDB snapshot..."
    mkdir -p "${MYSQL_TARGET}"
    cp -a "${SEED_SOURCE_DIR}/mysql-data/." "${MYSQL_TARGET}/"
    # Fix ownership for the MariaDB container.
    chown -R 999:999 "${MYSQL_TARGET}" 2>/dev/null || true
    log "Physical snapshot copy complete."
  else
    log "PHYSICAL_COPY_MYSQL_DATA=false; skipping mysql-data copy (MariaDB entrypoint will handle it)."
  fi
else
  log "ERROR: unknown SEED_STRATEGY=${SEED_STRATEGY}"
  exit 1
fi

# Atomically promote in-progress marker to complete.
mv "${IN_PROGRESS}" "${COMPLETE}"
trap - EXIT

log "Seed initialization complete."
