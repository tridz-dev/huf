#!/usr/bin/env bash
# FasterDocker benchmark driver.
# Usage:
#   ./docker/fast/benchmark.sh [sql|physical|bench|current] [iterations]
#
# Records results to ../../benchmarks/results.csv and per-run logs to
# ../../benchmarks/runs/<strategy>-run-<timestamp>-<start_type>-<n>/.
#
# Strategies:
#   sql      - split-container production-like profile using SQL seed
#              (docker/compose.fast.yml)
#   physical - split-container production-like profile using physical DB snapshot
#              (docker/compose.fast-physical.yml)
#   bench    - single-container dev/test profile running `bench start`
#              (docker/compose.bench.yml)
#   current  - the legacy docker/docker-compose.yml setup

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WORKSPACE_ROOT="$(cd "${REPO_ROOT}/../.." && pwd)"
source "${SCRIPT_DIR}/_lib.sh"

STRATEGY="${1:-sql}"
ITERATIONS="${2:-5}"
HUF_IMAGE_TAG="${HUF_IMAGE_TAG:-$(cd "${REPO_ROOT}" && git rev-parse --short HEAD)}"
export HUF_IMAGE_TAG
# OrbStack's Docker Compose sometimes races when creating many containers in
# parallel, producing "No such container" errors. Force sequential creation.
export COMPOSE_PARALLEL_LIMIT=1
# Pin the local images used by compose.fast.yml / compose.fast-physical.yml.
export HUF_APP_IMAGE="${HUF_APP_IMAGE:-huf-app}"
export SEED_IMAGE="${SEED_IMAGE:-huf-site-seed-sql}"
BRANCH="$(cd "${REPO_ROOT}" && git branch --show-current)"
SHA="$(cd "${REPO_ROOT}" && git rev-parse HEAD)"
RESULTS_CSV="${WORKSPACE_ROOT}/benchmarks/results.csv"
RUNS_BASE="${WORKSPACE_ROOT}/benchmarks/runs"

if [[ "${STRATEGY}" != "sql" && "${STRATEGY}" != "physical" && "${STRATEGY}" != "bench" && "${STRATEGY}" != "current" ]]; then
  fatal "usage: $0 [sql|physical|bench|current] [iterations]"
fi

RESULTS_DIR="$(dirname "${RESULTS_CSV}")"
mkdir -p "${RESULTS_DIR}" "${RUNS_BASE}"

if [[ ! -f "${RESULTS_CSV}" ]]; then
  echo "timestamp,branch,sha,strategy,start_type,run_number,down_v_used,image_warm,total_seconds,db_healthy_seconds,web_healthy_seconds,huf_ready_seconds,result,notes" > "${RESULTS_CSV}"
fi

if [[ "${STRATEGY}" == "physical" ]]; then
  COMPOSE_FAST=("-f" "${REPO_ROOT}/docker/compose.fast-physical.yml")
elif [[ "${STRATEGY}" == "bench" ]]; then
  COMPOSE_FAST=("-f" "${REPO_ROOT}/docker/compose.bench.yml")
else
  COMPOSE_FAST=("-f" "${REPO_ROOT}/docker/compose.fast.yml")
fi

COMPOSE_CURRENT=("-f" "${REPO_ROOT}/docker/docker-compose.yml")

compose_args() {
  if [[ "${STRATEGY}" == "current" ]]; then
    echo "${COMPOSE_CURRENT[@]}"
  else
    echo "${COMPOSE_FAST[@]}"
  fi
}

# Service/endpoint names differ between split-container and bench profiles.
web_service() {
  if [[ "${STRATEGY}" == "bench" ]]; then
    echo "bench"
  else
    echo "web"
  fi
}

huf_endpoint() {
  if [[ "${STRATEGY}" == "bench" ]]; then
    echo "http://localhost:${BENCH_WEB_PUBLISH_PORT:-8000}/huf"
  else
    echo "http://localhost:${FRONTEND_PUBLISH_PORT:-8080}/huf"
  fi
}

scoped_fasterdocker_cleanup() {
  local remove_volumes="$1"
  log "Scoped cleanup of fasterdocker compose resources (volumes=${remove_volumes})..."
  # Use direct Docker commands for cleanup: OrbStack's compose down is unreliable
  # when containers are left in Created state or name conflicts exist.
  local cid
  cid=$(docker ps -a -q -f name="^${COMPOSE_PROJECT_NAME}-" | tr '\n' ' ')
  if [[ -n "${cid}" ]]; then
    docker stop ${cid} >/dev/null 2>&1 || true
    docker rm -f ${cid} >/dev/null 2>&1 || true
  fi
  local container_deadline=$((SECONDS + 30))
  while docker ps -a --format '{{.Names}}' | grep -qE "^${COMPOSE_PROJECT_NAME}-"; do
    if (( SECONDS >= container_deadline )); then
      fatal "Timed out waiting for FasterDocker containers to be removed"
    fi
    sleep 1
  done
  if [[ "${remove_volumes}" == "true" ]]; then
    local volume_deadline=$((SECONDS + 30))
    while docker volume ls -q -f name="^${COMPOSE_PROJECT_NAME}_" | grep -q .; do
      docker volume ls -q -f name="^${COMPOSE_PROJECT_NAME}_" | xargs -r docker volume rm >/dev/null 2>&1 || true
      if (( SECONDS >= volume_deadline )); then
        fatal "Timed out waiting for FasterDocker volumes to be removed"
      fi
      sleep 1
    done
  fi
  local network_deadline=$((SECONDS + 30))
  while docker network ls --format '{{.Name}}' | grep -q "^${COMPOSE_PROJECT_NAME}_"; do
    docker network ls --format '{{.Name}}' | grep "^${COMPOSE_PROJECT_NAME}_" | xargs -r docker network rm >/dev/null 2>&1 || true
    if (( SECONDS >= network_deadline )); then
      fatal "Timed out waiting for FasterDocker networks to be removed"
    fi
    sleep 1
  done
}

wait_for_health() {
  local service="$1"
  local timeout_seconds="${2:-120}"
  local start
  start=$(date +%s)
  while true; do
    local status
    status=$(docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) ps -q "${service}" 2>/dev/null | xargs -r docker inspect --format='{{.State.Health.Status}}' 2>/dev/null || true)
    if [[ "${status}" == "healthy" ]]; then
      return 0
    fi
    local now
    now=$(date +%s)
    if (( now - start > timeout_seconds )); then
      return 1
    fi
    sleep 2
  done
}

run_benchmark() {
  local start_type="$1"
  local run_number="$2"
  local down_v="false"
  local env_strategy="${STRATEGY}"
  local run_ts
  run_ts=$(date +%Y%m%d-%H%M%S)
  local run_log_dir="${RUNS_BASE}/${STRATEGY}-run-${run_ts}-${start_type}-${run_number}"
  mkdir -p "${run_log_dir}"

  if [[ "${STRATEGY}" == "current" ]]; then
    env_strategy="current"
  fi

  if [[ "${start_type}" == "seeded-first-start" ]]; then
    down_v="true"
    log "Run ${run_number}: cleaning runtime state (down -v)..."
    scoped_fasterdocker_cleanup true
  else
    log "Run ${run_number}: keeping volumes for warm restart..."
    scoped_fasterdocker_cleanup false
  fi

  log "Run ${run_number}: starting services..."
  local total_start total_end db_done web_done huf_done
  total_start=$(date +%s.%N)

  # Start the whole stack in one compose up. Phased startup caused
  # container-recreate races on OrbStack; compose handles dependencies
  # via depends_on conditions, and we poll the milestones ourselves.
  docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) up -d
  sleep 2

  db_done=""
  if wait_for_health mariadb 120; then
    db_done=$(date +%s.%N)
  fi

  wait_seed_init() {
    local i
    for i in $(seq 1 120); do
      local cid status exit_code
      cid=$(docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) ps -a -q seed-init 2>/dev/null || true)
      if [[ -n "${cid}" ]]; then
        status=$(docker inspect --format='{{.State.Status}}' "${cid}" 2>/dev/null || true)
        exit_code=$(docker inspect --format='{{.State.ExitCode}}' "${cid}" 2>/dev/null || true)
        if [[ "${status}" == "exited" ]]; then
          if [[ "${exit_code}" == "0" ]]; then
            return 0
          fi
          log "seed-init failed with exit code ${exit_code}"
          return 1
        fi
      fi
      sleep 2
    done
    log "Timed out waiting for seed-init to complete"
    return 1
  }
  wait_seed_init || true

  web_done=""
  if wait_for_health "$(web_service)" 180; then
    web_done=$(date +%s.%N)
  fi

  huf_done=""
  # For the split profile we wait for the nginx frontend to proxy /huf.
  # For the bench profile the bench web container serves /huf directly.
  if [[ "${STRATEGY}" == "bench" ]]; then
    if curl -fsS "$(huf_endpoint)" >/dev/null 2>&1; then
      huf_done=$(date +%s.%N)
    fi
  else
    if wait_for_health frontend 180; then
      if curl -fsS "$(huf_endpoint)" >/dev/null 2>&1; then
        huf_done=$(date +%s.%N)
      fi
    fi
  fi

  total_end=$(date +%s.%N)

  local result="success"
  local notes=""
  if [[ -z "${db_done}" || -z "${web_done}" || -z "${huf_done}" ]]; then
    result="failed"
    notes="health or /huf check failed"
  fi

  local total_s db_s web_s huf_s
  total_s=$(awk "BEGIN {printf \"%.3f\", ${total_end}-${total_start}}")
  db_s=$( [[ -n "${db_done}" ]] && awk "BEGIN {printf \"%.3f\", ${db_done}-${total_start}}" || echo "")
  web_s=$( [[ -n "${web_done}" ]] && awk "BEGIN {printf \"%.3f\", ${web_done}-${total_start}}" || echo "")
  huf_s=$( [[ -n "${huf_done}" ]] && awk "BEGIN {printf \"%.3f\", ${huf_done}-${total_start}}" || echo "")

  local timestamp
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  printf '%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s\n' \
    "${timestamp}" "${BRANCH}" "${SHA}" "${env_strategy}" "${start_type}" "${run_number}" "${down_v}" \
    "${total_s}" "${db_s}" "${web_s}" "${huf_s}" "${result}" "${notes}" \
    >> "${RESULTS_CSV}"

  log "Run ${run_number}: ${result} in ${total_s}s"

  # Collect per-run artifacts after timing is complete.
  docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) ps > "${run_log_dir}/services.log" 2>&1 || true
  docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) logs --no-color > "${run_log_dir}/all-services.log" 2>&1 || true
  cat > "${run_log_dir}/meta.json" <<EOF
{
  "timestamp": "${timestamp}",
  "run_ts": "${run_ts}",
  "strategy": "${env_strategy}",
  "start_type": "${start_type}",
  "run_number": ${run_number},
  "down_v": ${down_v},
  "result": "${result}",
  "notes": "${notes}",
  "total_seconds": ${total_s},
  "db_healthy_seconds": "${db_s}",
  "web_healthy_seconds": "${web_s}",
  "huf_ready_seconds": "${huf_s}"
}
EOF

  # Between runs, keep volumes for restart-warm-start; first-start already
  # wiped them at the top of this function.
  scoped_fasterdocker_cleanup false
}

log "Benchmarking strategy=${STRATEGY}, iterations=${ITERATIONS}"

# Setup phase (pull/build) is allowed before timing and is not measured.
if [[ "${STRATEGY}" != "current" ]]; then
  log "Setup phase: verifying fast images are present..."
  docker compose -p "${COMPOSE_PROJECT_NAME}" "${COMPOSE_FAST[@]}" config >/dev/null
fi

for i in $(seq 1 "${ITERATIONS}"); do
  run_benchmark "seeded-first-start" "${i}"
done

if [[ "${STRATEGY}" != "current" ]]; then
  for i in $(seq 1 "${ITERATIONS}"); do
    run_benchmark "restart-warm-start" "${i}"
  done
fi

scoped_fasterdocker_cleanup true

log "Benchmark complete. Results written to ${RESULTS_CSV}"
