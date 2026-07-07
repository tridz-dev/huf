#!/usr/bin/env bash
# Entrypoint for worker services.
set -e

QUEUES="${1:-short,default}"
shift || true

exec bench worker --queue "${QUEUES}" "$@"
