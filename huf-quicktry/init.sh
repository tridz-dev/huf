#!/usr/bin/env bash
set -e

SITE_NAME=${SITE_NAME:-huf.localhost}
DB_ROOT_PW=${DB_ROOT_PW:-123}
ADMIN_PW=${ADMIN_PW:-admin}
HUF_REPO=${HUF_REPO:-https://github.com/tridz-dev/huf.git}
HUF_BRANCH=${HUF_BRANCH:-main}

if [ -d "/home/frappe/frappe-bench/apps/frappe" ]; then
  echo "Bench already exists. Starting..."
  cd /home/frappe/frappe-bench
  bench start
  exit 0
fi

echo "Creating new bench..."
export PATH="${NVM_DIR}/versions/node/v${NODE_VERSION_DEVELOP}/bin/:${PATH}"

cd /home/frappe
bench init --skip-redis-config-generation frappe-bench
cd /home/frappe/frappe-bench

# Use containers instead of localhost
bench set-mariadb-host mariadb
bench set-redis-cache-host redis://redis:6379
bench set-redis-queue-host redis://redis:6379
bench set-redis-socketio-host redis://redis:6379

# Remove redis, watch from Procfile (we run redis as a separate container)
sed -i '/redis/d' ./Procfile
sed -i '/watch/d' ./Procfile

# Get apps
bench get-app huf "${HUF_REPO}" --branch "${HUF_BRANCH}"

# Create site
bench new-site "${SITE_NAME}" \
  --force \
  --mariadb-root-password "${DB_ROOT_PW}" \
  --admin-password "${ADMIN_PW}" \
  --no-mariadb-socket

# Install HUF
bench --site "${SITE_NAME}" install-app huf

# Dev conveniences
bench --site "${SITE_NAME}" set-config developer_mode 1
bench --site "${SITE_NAME}" clear-cache
bench use "${SITE_NAME}"

echo "Starting bench..."
bench start
