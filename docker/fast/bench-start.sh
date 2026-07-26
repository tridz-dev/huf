#!/usr/bin/env bash
# FasterDocker dev/test entrypoint: single container running `bench start`.
# Relies on an external MariaDB and a single external Redis (db 0/1/2 for
# cache/queue/socketio). No nginx, no split web/worker/socketio containers.
#
# This script is image-agnostic: set APP_NAME/SITE_NAME/REDIS_* via environment
# to reuse it for other Frappe apps.

set -euo pipefail

SITE_NAME="${SITE_NAME:-huf.localhost}"
DB_HOST="${DB_HOST:-mariadb}"
DB_PORT="${DB_PORT:-3306}"
REDIS_CACHE="${REDIS_CACHE:-redis://redis:6379/0}"
REDIS_QUEUE="${REDIS_QUEUE:-redis://redis:6379/1}"
REDIS_SOCKETIO="${REDIS_SOCKETIO:-redis://redis:6379/2}"
BENCH_START_PORT="${BENCH_START_PORT:-8000}"
BENCH_WORKER_QUEUES="${BENCH_WORKER_QUEUES:-default,short,long}"
APP_NAME="${APP_NAME:-huf}"

cd /home/frappe/frappe-bench

# Make sure the sites volume has the runtime service map. The seed-init container
# already wrote this for the SQL seed path, but rewriting here makes the bench
# container self-describing and resilient to config drift.
mkdir -p sites
cat > sites/common_site_config.json <<EOF
{
  "db_host": "${DB_HOST}",
  "db_port": ${DB_PORT},
  "redis_cache": "${REDIS_CACHE}",
  "redis_queue": "${REDIS_QUEUE}",
  "redis_socketio": "${REDIS_SOCKETIO}",
  "socketio_port": 9000,
  "developer_mode": 1
}
EOF

# A dev Procfile with no local redis (external) and no file watcher.
# bench serve binds to all interfaces by default, so the Docker-published port
# is reachable from the host.
cat > Procfile <<EOF
web: bench serve --port ${BENCH_START_PORT}
socketio: node /home/frappe/frappe-bench/apps/frappe/socketio.js
schedule: bench schedule
worker: bench worker --queue ${BENCH_WORKER_QUEUES}
EOF

# Pin the default site for any ad-hoc bench commands.
bench use "${SITE_NAME}" >/dev/null 2>&1 || true

echo "[fasterdocker-bench] Starting bench start for site ${SITE_NAME} (app ${APP_NAME}) on port ${BENCH_START_PORT}..."
exec bench start
