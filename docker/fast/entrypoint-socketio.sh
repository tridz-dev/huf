#!/usr/bin/env bash
# Entrypoint for the socketio service.
set -e

exec node /home/frappe/frappe-bench/apps/frappe/socketio.js "$@"
