#!/bin/bash
set -e

ASSETS_PATH="/home/frappe/frappe-bench/sites/assets"
BAKED_PATH="/home/frappe/frappe-bench/assets"

echo "Linking baked assets into sites volume..."

# The mounted sites volume is owned by root when empty. Make it frappe-writable
# before manipulating the assets symlink, then drop back to frappe for the
# actual workload.
if [[ "$(id -u)" == "0" ]]; then
  chown -R frappe:frappe /home/frappe/frappe-bench/sites || true
fi

rm -rf "$ASSETS_PATH"
mkdir -p "$(dirname "$ASSETS_PATH")"
ln -s "$BAKED_PATH" "$ASSETS_PATH"

if [[ "$(id -u)" == "0" ]]; then
  chown -R frappe:frappe /home/frappe/frappe-bench/sites || true
  exec setpriv --reuid=frappe --regid=frappe --clear-groups -- "$@"
else
  exec "$@"
fi
