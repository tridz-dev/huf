#!/usr/bin/env bash
# Entrypoint for the web (gunicorn) service.
set -e

export GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
export GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
export GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

exec /usr/local/bin/start.sh "$@"
