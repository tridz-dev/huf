#!/usr/bin/env bash
# Entrypoint for the nginx frontend service.
set -e

exec /usr/local/bin/nginx-entrypoint.sh "$@"
