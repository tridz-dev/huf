#!/usr/bin/env bash
# Run inside the site-baker container to create a HUF site and export seed artifacts.
# Outputs to ${BAKE_OUTPUT_DIR}:
#   sql/${SITE_NAME}.sql.gz
#   sites/
#   metadata.json

set -euo pipefail

SITE_NAME="${SITE_NAME:-huf.localhost}"
DB_HOST="${DB_HOST:-mariadb-bake}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-fasterdocker-mysql-root}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-fasterdocker-admin}"
BAKE_OUTPUT_DIR="${BAKE_OUTPUT_DIR:-/bake-output}"
REDIS_CACHE="${REDIS_CACHE:-redis://redis-cache-bake:6379}"
REDIS_QUEUE="${REDIS_QUEUE:-redis://redis-queue-bake:6379}"
REDIS_SOCKETIO="${REDIS_SOCKETIO:-redis://redis-queue-bake:6379}"

log() { echo "[fasterdocker-bake] $*"; }

log "Bake output directory: ${BAKE_OUTPUT_DIR}"
mkdir -p "${BAKE_OUTPUT_DIR}/sql" "${BAKE_OUTPUT_DIR}/sites"

cd /home/frappe/frappe-bench

log "Configuring bench..."
bench set-mariadb-host "${DB_HOST}"
bench set-redis-cache-host "${REDIS_CACHE}"
bench set-redis-queue-host "${REDIS_QUEUE}"
bench set-redis-socketio-host "${REDIS_SOCKETIO}"

log "Waiting for MariaDB..."
wait-for-it -t 120 "${DB_HOST}:3306"

log "Creating site ${SITE_NAME}..."
bench new-site "${SITE_NAME}" \
  --force \
  --mariadb-root-password "${DB_ROOT_PASSWORD}" \
  --admin-password "${ADMIN_PASSWORD}" \
  --no-mariadb-socket

log "Installing HUF app..."
bench --site "${SITE_NAME}" install-app huf

log "Running migrate..."
bench --site "${SITE_NAME}" migrate

log "Setting developer mode..."
bench --site "${SITE_NAME}" set-config developer_mode 1
bench --site "${SITE_NAME}" clear-cache

# Frappe generates a random database name/user; read it from site_config.json.
SITE_CONFIG="sites/${SITE_NAME}/site_config.json"
DB_NAME="$(jq -r '.db_name // empty' "${SITE_CONFIG}")"
if [[ -z "${DB_NAME}" ]]; then
  log "ERROR: could not read db_name from ${SITE_CONFIG}"
  exit 1
fi
log "Frappe database name: ${DB_NAME}"

log "Exporting SQL dump..."
mysqldump -h "${DB_HOST}" -u root -p"${DB_ROOT_PASSWORD}" \
  --single-transaction \
  --routines \
  --triggers \
  "${DB_NAME}" | gzip > "${BAKE_OUTPUT_DIR}/sql/${SITE_NAME}.sql.gz"

log "Copying sites folder..."
cp -a sites/. "${BAKE_OUTPUT_DIR}/sites/"

log "Writing metadata..."
ARCH="$(uname -m)"
MARIADB_DIGEST=""
if command -v docker >/dev/null 2>&1; then
  MARIADB_DIGEST="$(docker inspect "${MARIADB_IMAGE:-mariadb:10.11.11}" --format='{{index .RepoDigests 0}}' 2>/dev/null || true)"
fi

MARIADB_VERSION=""
if command -v mysql >/dev/null 2>&1; then
  MARIADB_VERSION="$(mysql --version | sed -n 's/.*Distrib \([0-9\.]*\).*/\1/p')"
fi

cat > "${BAKE_OUTPUT_DIR}/metadata.json" <<EOF
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "frappe_version": "v16.25.0",
  "huf_version": "$(cat /home/frappe/frappe-bench/apps/huf/huf/__init__.py | grep '__version__' | sed 's/.*= *"\(.*\)".*/\1/')",
  "site_name": "${SITE_NAME}",
  "mariadb_image": "${MARIADB_IMAGE:-mariadb:10.11.11}",
  "mariadb_digest": "${MARIADB_DIGEST}",
  "mariadb_version": "${MARIADB_VERSION}",
  "architecture": "${ARCH}",
  "seed_strategies": ["sql", "physical"]
}
EOF

log "Bake complete. Artifacts in ${BAKE_OUTPUT_DIR}."
