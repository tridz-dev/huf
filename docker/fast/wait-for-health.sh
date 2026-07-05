#!/usr/bin/env bash
# Wait for a Docker Compose service to become healthy.
# Usage: wait-for-health.sh <service_name> [timeout_seconds]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_lib.sh"

SERVICE="$1"
TIMEOUT="${2:-120}"

log "Waiting up to ${TIMEOUT}s for service ${SERVICE} to be healthy..."

start=$(date +%s)
while true; do
  status=$(docker compose -p "${COMPOSE_PROJECT_NAME}" ps -q "${SERVICE}" 2>/dev/null | xargs -r docker inspect --format='{{.State.Health.Status}}' 2>/dev/null || true)
  if [[ "${status}" == "healthy" ]]; then
    log "Service ${SERVICE} is healthy."
    exit 0
  fi
  now=$(date +%s)
  if (( now - start > TIMEOUT )); then
    fatal "Timeout waiting for ${SERVICE} to become healthy (last status: ${status:-unknown})"
  fi
  sleep 2
done
