#!/bin/bash
set -e

ASSETS_PATH="/home/frappe/frappe-bench/sites/assets"
BAKED_PATH="/home/frappe/frappe-bench/assets"

# The mounted sites volume is owned by root when empty. Make it frappe-writable
# before manipulating the assets symlink or running the seed init.
if [[ "$(id -u)" == "0" ]]; then
  chown -R frappe:frappe /home/frappe/frappe-bench/sites || true
fi

# Link baked assets into the sites volume so Frappe can find them.
rm -rf "$ASSETS_PATH"
mkdir -p "$(dirname "$ASSETS_PATH")"
ln -s "$BAKED_PATH" "$ASSETS_PATH"

# Run seed initialization if seed data is bundled in the image.
# This is idempotent: on warm restarts the completion marker makes it a no-op.
if [[ -x "/usr/local/bin/init-seed.sh" && -d "/seed" && "${SKIP_SEED_INIT:-}" != "true" ]]; then
  echo "[fasterdocker-entrypoint] Running seed initialization..."
  SEED_SOURCE_DIR="${SEED_SOURCE_DIR:-/seed}" \
  SEED_TARGET_DIR="${SEED_TARGET_DIR:-/home/frappe/frappe-bench/sites}" \
  /usr/local/bin/init-seed.sh
fi

if [[ "$(id -u)" == "0" ]]; then
  chown -R frappe:frappe /home/frappe/frappe-bench/sites || true
  exec setpriv --reuid=frappe --regid=frappe --clear-groups -- "$@"
else
  exec "$@"
fi
