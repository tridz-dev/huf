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

# Prevent concurrent benchmark invocations from corrupting results.csv and
# racing on the same project-scoped Docker resources.
BENCHMARK_LOCK="/tmp/fasterdocker-benchmark.lock"

if [[ -e "${BENCHMARK_LOCK}" ]]; then
  lock_pid="$(cat "${BENCHMARK_LOCK}" 2>/dev/null || echo '')"
  if [[ -n "${lock_pid}" ]] && kill -0 "${lock_pid}" 2>/dev/null; then
    echo "Benchmark lock ${BENCHMARK_LOCK} held by PID ${lock_pid}; another benchmark is running. Exiting." >&2
    exit 1
  fi
  echo "Removing stale benchmark lock ${BENCHMARK_LOCK}" >&2
  rm -f "${BENCHMARK_LOCK}"
fi

trap 'rm -f "${BENCHMARK_LOCK}"' EXIT
printf '%s\n' "$$" > "${BENCHMARK_LOCK}"

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

huf_curl() {
  local site="${SITE_NAME:-huf.localhost}"
  curl -fsSL -H "Host: ${site}" "$(huf_endpoint)" >/dev/null 2>&1
}

_hr_now() {
  python3 -c 'import time; print("{:.9f}".format(time.time()))'
}

_fmt_diff() {
  python3 -c "import sys; print('{:.3f}'.format(float(sys.argv[1]) - float(sys.argv[2])))" "$1" "$2"
}

_fasterdocker_container_names() {
  docker ps -a --format '{{.Names}}' 2>/dev/null \
    | grep -E "^(fasterdocker-build-|fasterdocker-seed-|fasterdocker-run-)" \
    || true
}

scoped_fasterdocker_cleanup() {
  local remove_volumes="$1"
  log "Scoped cleanup of fasterdocker compose resources (volumes=${remove_volumes})..."

  # 1. Aggressively stop+remove all FasterDocker-scoped containers first.
  local attempt
  for attempt in $(seq 1 60); do
    local names
    names="$(_fasterdocker_container_names | tr '\n' ' ')"
    if [[ -z "${names// }" ]]; then
      break
    fi
    # shellcheck disable=SC2086
    docker stop --time 2 ${names} >/dev/null 2>&1 || true
    # shellcheck disable=SC2086
    docker rm -f ${names} >/dev/null 2>&1 || true
    sleep 1
  done

  # 2. Let compose down remove networks/volumes and any remaining compose state.
  local down_args=("--remove-orphans" "--timeout" "5")
  if [[ "${remove_volumes}" == "true" ]]; then
    down_args+=("-v")
  fi
  docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) down "${down_args[@]}" >/dev/null 2>&1 || true

  # 3. Remove project-scoped volumes if requested.
  if [[ "${remove_volumes}" == "true" ]]; then
    local vols
    vols="$(docker volume ls -q -f name="^${COMPOSE_PROJECT_NAME}_" 2>/dev/null | tr '\n' ' ' || true)"
    if [[ -n "${vols// }" ]]; then
      # shellcheck disable=SC2086
      docker volume rm ${vols} >/dev/null 2>&1 || true
    fi
  fi

  # 4. Remove project-scoped networks.
  local nets
  nets="$(docker network ls --format '{{.Name}}' 2>/dev/null | grep "^${COMPOSE_PROJECT_NAME}_" | tr '\n' ' ' || true)"
  if [[ -n "${nets// }" ]]; then
    # shellcheck disable=SC2086
    docker network rm ${nets} >/dev/null 2>&1 || true
  fi

  # 5. Final wait until no FasterDocker-scoped containers remain.
  local waited=0
  while [[ -n "$(_fasterdocker_container_names | head -n1)" ]] && (( waited < 30 )); do
    sleep 1
    ((waited+=1))
  done

  if [[ -n "$(_fasterdocker_container_names | head -n1)" ]]; then
    fatal "FasterDocker containers remain after cleanup: $(_fasterdocker_container_names | tr '\n' ' ')"
  fi

  # 6. Brief pause so OrbStack can fully release names/volumes/networks before the next up.
  sleep 5
}

wait_for_health() {
  local service="$1"
  local timeout_seconds="${2:-120}"
  local start
  start="$(_hr_now)"
  local last_progress=0
  while true; do
    local status=""
    local cid
    cid=$(docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) ps -q "${service}" 2>/dev/null || true)
    if [[ -n "${cid}" ]]; then
      status=$(docker inspect --format='{{.State.Health.Status}}' "${cid}" 2>/dev/null || true)
    fi
    if [[ "${status}" == "healthy" ]]; then
      log "${service} is healthy"
      return 0
    fi
    local now elapsed progress_int
    now="$(_hr_now)"
    elapsed="$(python3 -c "import sys; print('{:.0f}'.format(float(sys.argv[1]) - float(sys.argv[2])))" "${now}" "${start}")"
    progress_int=$((elapsed / 10))
    if (( progress_int > last_progress )); then
      last_progress="${progress_int}"
      log "still waiting for ${service} to become healthy (${elapsed}s elapsed, status=${status:-unknown})"
    fi
    if (( $(python3 -c "import sys; print('1' if float(sys.argv[1]) - float(sys.argv[2]) > ${timeout_seconds} else '0')" "${now}" "${start}") )); then
      log "timed out waiting for ${service} to become healthy"
      return 1
    fi
    sleep 2
  done
}

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
          log "seed-init completed successfully"
          return 0
        fi
        log "seed-init failed with exit code ${exit_code}"
        return 1
      fi
    fi
    if (( i % 10 == 0 )); then
      log "still waiting for seed-init to complete (${i} checks)"
    fi
    sleep 2
  done
  log "Timed out waiting for seed-init to complete"
  return 1
}

up_services() {
  docker compose -p "${COMPOSE_PROJECT_NAME}" $(compose_args) up -d --no-deps "$@"
  sleep 2
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

  # Unique suffix per run avoids OrbStack name-conflict races when containers
  # from the previous run are still being garbage-collected.
  RUN_SUFFIX="${run_ts}-r${run_number}"
  export RUN_SUFFIX

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
  total_start="$(_hr_now)"

  local up_failed=false
  local notes=""

  if [[ "${STRATEGY}" == "current" ]]; then
    if ! up_services; then
      up_failed=true
      notes="docker compose up failed"
    fi
  elif [[ "${STRATEGY}" == "bench" ]]; then
    if ! up_services mariadb redis; then up_failed=true; fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health mariadb 120; then
      up_failed=true
      notes="mariadb healthcheck failed"
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health redis 60; then
      up_failed=true
      notes="redis healthcheck failed"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      db_done="$(_hr_now)"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      if ! up_services seed-init; then up_failed=true; fi
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_seed_init; then
      up_failed=true
      notes="seed-init did not complete"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      if ! up_services bench; then up_failed=true; fi
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health "$(web_service)" 180; then
      up_failed=true
      notes="bench healthcheck failed"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      web_done="$(_hr_now)"
    fi
  else
    if ! up_services mariadb; then up_failed=true; fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health mariadb 120; then
      up_failed=true
      notes="mariadb healthcheck failed"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      db_done="$(_hr_now)"
      if ! up_services redis-cache redis-queue redis-socketio; then up_failed=true; fi
    fi
    for svc in redis-cache redis-queue redis-socketio; do
      if [[ "${up_failed}" == "false" ]] && ! wait_for_health "${svc}" 60; then
        up_failed=true
        notes="${svc} healthcheck failed"
      fi
    done
    if [[ "${up_failed}" == "false" ]]; then
      if ! up_services seed-init; then up_failed=true; fi
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_seed_init; then
      up_failed=true
      notes="seed-init did not complete"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      if ! up_services web worker-short worker-long scheduler socketio; then up_failed=true; fi
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health "$(web_service)" 180; then
      up_failed=true
      notes="web healthcheck failed"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      web_done="$(_hr_now)"
    fi
    if [[ "${up_failed}" == "false" ]]; then
      if ! up_services frontend; then up_failed=true; fi
    fi
    if [[ "${up_failed}" == "false" ]] && ! wait_for_health frontend 180; then
      up_failed=true
      notes="frontend healthcheck failed"
    fi
  fi

  if [[ "${up_failed}" == "true" ]]; then
    total_end="$(_hr_now)"
    result="failed"
    [[ -z "${notes}" ]] && notes="docker compose up failed"
    printf '%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${BRANCH}" "${SHA}" "${env_strategy}" "${start_type}" "${run_number}" "${down_v}" \
      "$(_fmt_diff "${total_end}" "${total_start}")" "" "" "" "${result}" "${notes}" \
      >> "${RESULTS_CSV}"
    log "Run ${run_number}: ${result} - ${notes}"
    scoped_fasterdocker_cleanup true
    return
  fi

  huf_done=""
  if huf_curl; then
    huf_done="$(_hr_now)"
  fi

  total_end="$(_hr_now)"

  local result="success"
  local notes=""
  if [[ -z "${db_done}" || -z "${web_done}" || -z "${huf_done}" ]]; then
    result="failed"
    notes="health or /huf check failed"
  fi

  local total_s db_s web_s huf_s
  total_s="$(_fmt_diff "${total_end}" "${total_start}")"
  db_s="$( [[ -n "${db_done}" ]] && _fmt_diff "${db_done}" "${total_start}" || echo "")"
  web_s="$( [[ -n "${web_done}" ]] && _fmt_diff "${web_done}" "${total_start}" || echo "")"
  huf_s="$( [[ -n "${huf_done}" ]] && _fmt_diff "${huf_done}" "${total_start}" || echo "")"

  local timestamp
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  printf '%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,%s,%s\n' \
    "${timestamp}" "${BRANCH}" "${SHA}" "${env_strategy}" "${start_type}" "${run_number}" "${down_v}" \
    "${total_s}" "${db_s}" "${web_s}" "${huf_s}" "${result}" "${notes}" \
    >> "${RESULTS_CSV}"

  log "Run ${run_number}: ${result} in ${total_s}s"

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

  if [[ "${result}" == "failed" && "${start_type}" == "restart-warm-start" ]]; then
    scoped_fasterdocker_cleanup true
  else
    scoped_fasterdocker_cleanup false
  fi
}

log "Benchmarking strategy=${STRATEGY}, iterations=${ITERATIONS}"

# Setup phase (pull/build) is allowed before timing and is not measured.
if [[ "${STRATEGY}" != "current" ]]; then
  log "Setup phase: verifying fast images are present..."
  RUN_SUFFIX=setup
  export RUN_SUFFIX
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
