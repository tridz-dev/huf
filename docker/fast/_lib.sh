#!/usr/bin/env bash
# Shared helper library for FasterDocker scripts.
# Enforces container-name scoping and safe cleanup.

set -euo pipefail

ALLOWED_PREFIXES=(
  "fasterdocker-build-"
  "fasterdocker-seed-"
  "fasterdocker-run-"
)

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-fasterdocker}"

# is_allowed_container_name name
# Returns 0 if the name starts with one of the allowed prefixes.
is_allowed_container_name() {
  local name="$1"
  for prefix in "${ALLOWED_PREFIXES[@]}"; do
    if [[ "${name}" == "${prefix}"* ]]; then
      return 0
    fi
  done
  return 1
}

# validate_allowed_container_names [name ...]
# Fails if any name is outside the allowed prefixes.
validate_allowed_container_names() {
  local failed=()
  for name in "$@"; do
    if ! is_allowed_container_name "${name}"; then
      failed+=("${name}")
    fi
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "ERROR: container name(s) outside allowed prefixes: ${failed[*]}" >&2
    echo "Allowed prefixes: ${ALLOWED_PREFIXES[*]}" >&2
    exit 1
  fi
}

# docker_compose_project_args
# Echoes the standard compose project/name arguments used by this effort.
docker_compose_project_args() {
  echo "-p" "${COMPOSE_PROJECT_NAME}"
}

# scoped_compose_down compose_file...
# Runs docker compose down scoped to the project and the given compose file(s).
# Never passes --rmi or removes unrelated resources.
scoped_compose_down() {
  local files=("$@")
  local args=()
  for f in "${files[@]}"; do
    args+=("-f" "${f}")
  done
  docker compose -p "${COMPOSE_PROJECT_NAME}" "${args[@]}" down -v --remove-orphans
}

# log message
log() {
  echo "[fasterdocker] $*"
}

# fatal message
fatal() {
  echo "[fasterdocker] FATAL: $*" >&2
  exit 1
}
