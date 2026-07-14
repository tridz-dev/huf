#!/usr/bin/env bash
set -e

echo "Setting up HUF environment..."
echo "This is a one-time setup and may take 5–8 minutes. Please do not interrupt."

SITE_NAME=${SITE_NAME:-huf.localhost}
DB_ROOT_PW=${DB_ROOT_PW:-huf_dev_mysql_root}
ADMIN_PW=${ADMIN_PW:-huf_dev_admin}
HUF_REPO=${HUF_REPO:-https://github.com/tridz-dev/huf.git}
HUF_BRANCH=${HUF_BRANCH:-develop}

cd /home/frappe

# If bench already exists, just start
if [ -d "/home/frappe/frappe-bench" ]; then
  echo "Bench already exists. Starting..."
  cd /home/frappe/frappe-bench
  bench start
  exit 0
fi

echo "Creating new bench..."
echo "Downloading Frappe framework and installing dependencies."
echo "This may take 3–6 minutes on first run..."

# Ensure node path is available
export PATH="${NVM_DIR}/versions/node/v${NODE_VERSION_DEVELOP}/bin/:${PATH}"

# Initialize bench (heavy step)
bench init --skip-redis-config-generation frappe-bench
cd /home/frappe/frappe-bench

# Configure container service hosts
bench set-mariadb-host mariadb
bench set-redis-cache-host redis://redis:6379
bench set-redis-queue-host redis://redis:6379
bench set-redis-socketio-host redis://redis:6379

# Remove redis + watch from Procfile (external services)
sed -i '/redis/d' Procfile
sed -i '/watch/d' Procfile

# Wait for MariaDB to be ready
echo "Waiting for MariaDB..."
until mysqladmin ping -h mariadb --silent; do
  sleep 2
done
echo "MariaDB is ready."

# Get HUF app
echo "Cloning HUF repository..."
bench get-app huf "${HUF_REPO}" --branch "${HUF_BRANCH}"

echo "Creating site and setting up database."
echo "This step may take a few minutes..."

# Create site (heavy step)
bench new-site "${SITE_NAME}" \
  --force \
  --mariadb-root-password "${DB_ROOT_PW}" \
  --admin-password "${ADMIN_PW}" \
  --no-mariadb-socket

# Install HUF
echo "Installing HUF app..."
bench --site "${SITE_NAME}" install-app huf

# Dev setup
bench --site "${SITE_NAME}" set-config developer_mode 1
bench --site "${SITE_NAME}" clear-cache
bench use "${SITE_NAME}"

echo "Setup complete. Starting bench..."
bench start
