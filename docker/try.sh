#!/usr/bin/env bash
set -euo pipefail

# docker/try.sh — one-command wrapper for running HUF locally.
#
# NOTE: after creating this file, run:
#   chmod +x docker/try.sh
#
# Shell dialect: bash 3.2-compatible (macOS stock bash). Avoids associative
# arrays, mapfile, local -n, ${var,,}, and other bash 4+ features.

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
DOCKER_DIR="$REPO_ROOT/docker"

DEFAULT_PROJECT="huf"
DEFAULT_VARIANT="demo"
DEFAULT_ENV="$REPO_ROOT/.env"

# Compose files are relative to REPO_ROOT.
COMPOSE_DEMO="$DOCKER_DIR/docker-compose.yml"
COMPOSE_BENCH="$DOCKER_DIR/compose.bench.yml"
COMPOSE_FAST="$DOCKER_DIR/compose.fast.yml"
COMPOSE_FAST_PHYSICAL="$DOCKER_DIR/compose.fast-physical.yml"

# Container that persists the demo credentials file (demo-entrypoint.sh writes
# sites/<SITE_NAME>/.fasterdocker-credentials inside this container).
CREDS_CONTAINER="fasterdocker-run-frappe"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() { echo "[fasterdocker] $*"; }

fatal() {
  echo "[fasterdocker] ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fatal "$1 is not installed."
}

usage() {
  cat <<EOF
Usage: ./docker/try.sh [GLOBAL_FLAGS] [SUBCOMMAND] [ARGS]

Subcommands (default: up):
  up       Start the stack (detached, waits for healthy)
  down     Stop the stack (add --volumes to remove volumes)
  reset    Stop and remove volumes (cold re-seed on next up)
  logs     Tail logs: ./docker/try.sh logs [service ...]
  status   Show running containers, health, and ports
  creds    Print the saved credentials from the running frappe container

Global flags:
  --variant {demo|bench|fast|fast-physical}   default: demo
  --project NAME                              default: huf
  --env FILE                                  default: ./.env
  --tag TAG                                   sets HUF_IMAGE_TAG
  --site NAME                                 sets SITE_NAME
  --admin-password PASS                       sets ADMIN_PASSWORD
  --web-port PORT                             sets BENCH_WEB_PUBLISH_PORT
  --socketio-port PORT                        sets BENCH_SOCKETIO_PUBLISH_PORT
  --frontend-port PORT                        sets FRONTEND_PUBLISH_PORT
                                              (used by fast / fast-physical)
  --no-port-remap                             fail on port conflict instead of
                                              auto-remapping
  --dry-run                                   print resolved env/command, then
                                              exit without executing
  -h, --help                                  show this help

Examples:
  ./docker/try.sh
  ./docker/try.sh --variant fast-physical
  ./docker/try.sh --variant demo --web-port 8001
  ./docker/try.sh down
  ./docker/try.sh reset
  ./docker/try.sh logs frappe
  ./docker/try.sh creds
EOF
}


# Sets the global $compose_file. Not implemented via echo+command-substitution
# because `fatal`'s `exit 1` would only terminate the subshell, not the script.
variant_to_compose() {
  case "$1" in
    demo)          compose_file="$COMPOSE_DEMO" ;;
    bench)         compose_file="$COMPOSE_BENCH" ;;
    fast)          compose_file="$COMPOSE_FAST" ;;
    fast-physical) compose_file="$COMPOSE_FAST_PHYSICAL" ;;
    *)             fatal "Unknown variant: $1. Use demo, bench, fast, or fast-physical." ;;
  esac
}

# Returns the env var that controls the user-facing HTTP port for a variant.
user_facing_port_env() {
  case "$1" in
    demo|bench)         echo "BENCH_WEB_PUBLISH_PORT" ;;
    fast|fast-physical) echo "FRONTEND_PUBLISH_PORT" ;;
  esac
}

# Returns the user-facing URL path. All variants serve the app under /APP_NAME.
url_path() {
  echo "/${APP_NAME:-huf}"
}

# Returns the user-facing port value after resolution.
user_facing_port() {
  local env_var
  env_var=$(user_facing_port_env "$1")
  echo "${!env_var:-}"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

parse_args() {
  subcommand=""
  variant=""
  project=""
  env_file=""
  tag=""
  site=""
  admin_password=""
  web_port=""
  socketio_port=""
  frontend_port=""
  no_port_remap=""
  dry_run=""
  volumes_flag=""
  rmi_flag=""
  extra_args=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      up|down|reset|logs|status|creds)
        subcommand="$1"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      --variant)
        [[ $# -ge 2 ]] || fatal "--variant requires a value."
        variant="$2"
        shift 2
        ;;
      --project)
        [[ $# -ge 2 ]] || fatal "--project requires a value."
        project="$2"
        shift 2
        ;;
      --env)
        [[ $# -ge 2 ]] || fatal "--env requires a value."
        env_file="$2"
        shift 2
        ;;
      --tag)
        [[ $# -ge 2 ]] || fatal "--tag requires a value."
        tag="$2"
        shift 2
        ;;
      --site)
        [[ $# -ge 2 ]] || fatal "--site requires a value."
        site="$2"
        shift 2
        ;;
      --admin-password)
        [[ $# -ge 2 ]] || fatal "--admin-password requires a value."
        admin_password="$2"
        shift 2
        ;;
      --web-port)
        [[ $# -ge 2 ]] || fatal "--web-port requires a value."
        web_port="$2"
        shift 2
        ;;
      --socketio-port)
        [[ $# -ge 2 ]] || fatal "--socketio-port requires a value."
        socketio_port="$2"
        shift 2
        ;;
      --frontend-port)
        [[ $# -ge 2 ]] || fatal "--frontend-port requires a value."
        frontend_port="$2"
        shift 2
        ;;
      --no-port-remap)
        no_port_remap=1
        shift
        ;;
      --dry-run)
        dry_run=1
        shift
        ;;
      --volumes)
        volumes_flag=1
        shift
        ;;
      --rmi)
        [[ $# -ge 2 ]] || fatal "--rmi requires a value."
        rmi_flag="$2"
        shift 2
        ;;
      --)
        shift
        while [[ $# -gt 0 ]]; do
          extra_args="${extra_args:+$extra_args }$1"
          shift
        done
        break
        ;;
      -*)
        fatal "Unknown option: $1"
        ;;
      *)
        if [[ -z "$subcommand" ]]; then
          subcommand="$1"
        else
          extra_args="${extra_args:+$extra_args }$1"
        fi
        shift
        ;;
    esac
  done

  subcommand=${subcommand:-up}
  variant=${variant:-$DEFAULT_VARIANT}
  project=${project:-$DEFAULT_PROJECT}
  env_file=${env_file:-$DEFAULT_ENV}
}

# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

load_env_file() {
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$env_file"
    set +a
  else
    log "No .env found at $env_file; using compose defaults."
    log "Copy docker/fast/.env.example to $REPO_ROOT/.env to customize."
  fi
}

apply_cli_overrides() {
  [[ -n "$tag" ]]            && export HUF_IMAGE_TAG="$tag"
  [[ -n "$site" ]]           && export SITE_NAME="$site"
  [[ -n "$admin_password" ]] && export ADMIN_PASSWORD="$admin_password"
  [[ -n "$web_port" ]]       && export BENCH_WEB_PUBLISH_PORT="$web_port"
  [[ -n "$socketio_port" ]]  && export BENCH_SOCKETIO_PUBLISH_PORT="$socketio_port"
  [[ -n "$frontend_port" ]]  && export FRONTEND_PUBLISH_PORT="$frontend_port"
  export COMPOSE_PROJECT_NAME="$project"
}

# ---------------------------------------------------------------------------
# Port detection and remapping
# ---------------------------------------------------------------------------

port_is_free() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    if lsof -Pi :"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 1
    fi
    return 0
  fi

  if command -v ss >/dev/null 2>&1; then
    if ss -tln sport = :"$port" >/dev/null 2>&1; then
      return 1
    fi
    return 0
  fi

  if command -v netstat >/dev/null 2>&1; then
    if netstat -an 2>/dev/null | grep -E "[.:]$port[[:space:]].*LISTEN" >/dev/null 2>&1; then
      return 1
    fi
    return 0
  fi

  # Last resort: attempt a TCP connection to 127.0.0.1 on the port.
  # Success means something is listening; failure means the port is free.
  if (exec 3<>/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
    return 1
  fi
  return 0
}

next_free_port() {
  local start="$1" end="$2" port
  for (( port = start; port <= end; port++ )); do
    if port_is_free "$port"; then
      echo "$port"
      return 0
    fi
  done
  return 1
}

resolve_port() {
  local env_var="$1" default_port="$2" purpose="$3"
  local requested final

  requested="${!env_var:-$default_port}"

  if port_is_free "$requested"; then
    export "$env_var"="$requested"
    return 0
  fi

  if [[ "${no_port_remap:-}" == "1" ]]; then
    fatal "Port $requested ($purpose) is in use. Free it or use the matching --*-port flag."
  fi

  final=$(next_free_port $((requested + 1)) $((default_port + 99)) || true)
  if [[ -z "$final" ]]; then
    fatal "Could not find a free port for $purpose between $requested and $((default_port + 99)). Free one of those ports or use the matching --*-port flag."
  fi

  log "Port $requested is in use; remapping $purpose port to $final."
  export "$env_var"="$final"
}

resolve_ports_for_variant() {
  case "$variant" in
    demo|bench)
      resolve_port BENCH_WEB_PUBLISH_PORT 8000 "web"
      resolve_port BENCH_SOCKETIO_PUBLISH_PORT 9000 "socketio"
      ;;
    fast|fast-physical)
      # FRONTEND_PUBLISH_PORT is consumed by compose.fast.yml / compose.fast-physical.yml.
      resolve_port FRONTEND_PUBLISH_PORT 8080 "frontend"
      # Export bench/socketio defaults for consistency even though they are not
      # published by the fast variants.
      export BENCH_WEB_PUBLISH_PORT=${BENCH_WEB_PUBLISH_PORT:-8000}
      export BENCH_SOCKETIO_PUBLISH_PORT=${BENCH_SOCKETIO_PUBLISH_PORT:-9000}
      ;;
  esac
}

# ---------------------------------------------------------------------------
# Boot type detection
# ---------------------------------------------------------------------------

# Heuristic: a "warm" restart is reported when the MariaDB data volume for
# this project already exists (docker compose down without --volumes keeps
# the volume but removes the container, so checking container existence
# instead of the volume would misreport that common case as cold). `reset`
# (down --volumes) removes the volume, so the next up is correctly "cold".
detect_boot_type() {
  if docker volume ls -q --filter name="^${project}_mariadb-data$" 2>/dev/null | grep -q .; then
    echo "warm"
  else
    echo "cold"
  fi
}

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

read_credentials_from_container() {
  local site="${SITE_NAME:-huf.localhost}"
  local creds_path="sites/${site}/.fasterdocker-credentials"
  docker exec "${CREDS_CONTAINER}" cat "$creds_path" 2>/dev/null
}

# Returns the host-side published port for a given container/internal port.
get_container_published_port() {
  local container="$1" internal_port="$2"
  docker port "$container" "$internal_port" 2>/dev/null | head -n1 | sed 's/.*://' | tr -d '[:space:]'
}

parse_credential_value() {
  local key="$1" creds="$2"
  echo "$creds" | grep "^${key}=" | head -n1 | cut -d= -f2-
}

# ---------------------------------------------------------------------------
# HTTP readiness probe
# ---------------------------------------------------------------------------

wait_for_http_200() {
  local url="$1" host="$2" port="$3"
  local i line

  for (( i = 1; i <= 30; i++ )); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS -H "Host: $host" "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      # Fallback using bash /dev/tcp when curl is unavailable.
      line=""
      if (exec 3<>/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
        echo -e "GET ${url#http://localhost:$port} HTTP/1.1\r\nHost: $host\r\nConnection: close\r\n\r\n" >&3
        read -r line <&3 || true
        exec 3<&- 3>&- || true
      fi
      if [[ "$line" == *" 200 "* ]]; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

diagnose_failure() {
  local variant="$1"
  local up_out_file="$2"

  # Docker daemon may have stopped mid-run.
  if ! docker info >/dev/null 2>&1; then
    fatal "Docker daemon is not running. Start Docker Desktop or run 'sudo systemctl start docker', then retry."
  fi

  # Image pull failure.
  if [[ -f "$up_out_file" ]] && grep -qiE "pull|denied|not found|no such image" "$up_out_file"; then
    local image
    image=$(grep -oE "ghcr\.io/[^[:space:]:]+:[^[:space:]]+" "$up_out_file" 2>/dev/null | head -n1 || true)
    [[ -z "$image" ]] && image="${HUF_DEMO_IMAGE:-ghcr.io/tridz-dev/huf-demo}:${HUF_IMAGE_TAG:-latest}"
    fatal "Failed to pull image $image. Check network, registry access, and HUF_IMAGE_TAG. To build locally see docker/fast/README.md."
  fi

  # Stale seed-in-progress marker for SQL/physical variants.
  if [[ "$variant" == "fast" || "$variant" == "fast-physical" ]]; then
    if docker run --rm -v "${project}_mariadb-data:/data" busybox \
       test -f /data/.fasterdocker-seed-in-progress >/dev/null 2>&1; then
      fatal "A previous seed operation was interrupted. Run './docker/try.sh reset' to clear volumes and re-seed, then try again."
    fi
  fi

  # Architecture / digest mismatch.
  local logs
  logs=$(docker compose -p "$project" -f "$compose_file" logs --tail=200 2>/dev/null || true)
  if echo "$logs" | grep -qiE "digest|architecture|platform|no matching manifest"; then
    fatal "The seed image does not match your host architecture or MariaDB digest. Use the SQL variant ('--variant fast') or build a local physical snapshot ('./docker/fast/build-demo.sh')."
  fi

  fatal "Services did not become healthy within the timeout. Run './docker/try.sh logs' and check the failing service. Common causes: port conflict, architecture mismatch, stale seed marker, or MariaDB digest mismatch."
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

print_banner() {
  local url="$1" site="$2" admin_user="$3" admin_pass="$4" variant="$5" boot_type="$6" elapsed="$7"

  cat <<EOF

  HUF is ready
  ------------------------------------------------------------
  URL:           ${url}
  Site:          ${site}
  Username:      ${admin_user}
  Password:      ${admin_pass}
  Variant:       ${variant}
  Boot type:     ${boot_type} boot
  Elapsed:       ${elapsed}s
  ------------------------------------------------------------

Next steps:
  View logs:   ./docker/try.sh logs
  Stop:        ./docker/try.sh down
  Reset data:  ./docker/try.sh reset

Note: default credentials are insecure and intended for local demo only.
EOF
}

# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

cmd_up() {
  local compose_file user_port_env user_port url start_time elapsed
  local creds admin_user admin_pass boot_type up_out_file rc

  require_command docker
  if ! docker info >/dev/null 2>&1; then
    fatal "Docker daemon is not running. Start Docker Desktop or run 'sudo systemctl start docker', then retry."
  fi

  variant_to_compose "$variant"
  [[ -f "$compose_file" ]] || fatal "Compose file $compose_file not found. Run from repo root or ensure the fasterdocker assets are present."

  load_env_file
  apply_cli_overrides
  resolve_ports_for_variant

  user_port_env=$(user_facing_port_env "$variant")
  user_port=${!user_port_env}
  url="http://localhost:${user_port}$(url_path)"
  boot_type=$(detect_boot_type)

  if [[ "$dry_run" == "1" ]]; then
    echo "Resolved environment:"
    echo "  COMPOSE_PROJECT_NAME=$project"
    echo "  SITE_NAME=${SITE_NAME:-huf.localhost}"
    echo "  APP_NAME=${APP_NAME:-huf}"
    echo "  HUF_IMAGE_TAG=${HUF_IMAGE_TAG:-latest}"
    echo "  BENCH_WEB_PUBLISH_PORT=${BENCH_WEB_PUBLISH_PORT:-8000}"
    echo "  BENCH_SOCKETIO_PUBLISH_PORT=${BENCH_SOCKETIO_PUBLISH_PORT:-9000}"
    echo "  FRONTEND_PUBLISH_PORT=${FRONTEND_PUBLISH_PORT:-8080}"
    echo "  $user_port_env=$user_port"
    echo "Compose command:"
    echo "  docker compose -p $project -f $compose_file up --wait -d --remove-orphans"
    exit 0
  fi

  start_time=$(date +%s)
  log "Starting HUF ($variant, project=$project, $user_port_env=$user_port)..."

  up_out_file=$(mktemp)
  if ! docker compose -p "$project" -f "$compose_file" up --wait -d --remove-orphans 2>&1 | tee "$up_out_file"; then
    rc=${PIPESTATUS[0]}
    diagnose_failure "$variant" "$up_out_file" "$rc"
  fi

  if ! wait_for_http_200 "$url" "${SITE_NAME:-huf.localhost}" "$user_port"; then
    fatal "HUF endpoint $url did not respond. Run './docker/try.sh logs' for details."
  fi

  elapsed=$(($(date +%s) - start_time))

  creds=$(read_credentials_from_container || true)
  if [[ -n "$creds" ]]; then
    admin_user=$(parse_credential_value ADMIN_USER "$creds")
    admin_pass=$(parse_credential_value ADMIN_PASSWORD "$creds")
    admin_user=${admin_user:-Administrator}
  fi

  admin_pass=${admin_pass:-${ADMIN_PASSWORD:-}}
  if [[ -z "$admin_pass" ]]; then
    admin_pass="(unknown — run './docker/try.sh creds' after first boot completes)"
  fi

  print_banner "$url" "${SITE_NAME:-huf.localhost}" "${admin_user:-Administrator}" "$admin_pass" "$variant" "$boot_type" "$elapsed"
}

cmd_down() {
  local compose_file volumes_arg
  variant_to_compose "$variant"
  [[ -f "$compose_file" ]] || fatal "Compose file $compose_file not found."

  volumes_arg=""
  [[ "$volumes_flag" == "1" ]] && volumes_arg="--volumes"

  load_env_file
  apply_cli_overrides

  if [[ "$dry_run" == "1" ]]; then
    echo "Compose command:"
    echo "  docker compose -p $project -f $compose_file down --remove-orphans $volumes_arg"
    exit 0
  fi

  docker compose -p "$project" -f "$compose_file" down --remove-orphans $volumes_arg
  log "Stack $project stopped${volumes_flag:+ and volumes removed}."
}

cmd_reset() {
  volumes_flag=1
  cmd_down
  log "Next 'up' will perform a cold boot and re-seed."
}

cmd_logs() {
  local compose_file
  variant_to_compose "$variant"
  [[ -f "$compose_file" ]] || fatal "Compose file $compose_file not found."

  load_env_file
  apply_cli_overrides

  docker compose -p "$project" -f "$compose_file" logs -f --tail=100 $extra_args
}

cmd_status() {
  local compose_file user_port url
  variant_to_compose "$variant"
  [[ -f "$compose_file" ]] || fatal "Compose file $compose_file not found."

  load_env_file
  apply_cli_overrides
  # Do not remap ports here; status reports on a stack that is already running.
  # The actual published ports are visible in the `docker compose ps` output.
  # (Avoid indirect expansion of an env var resolve_ports_for_variant never
  # exported in this path — it would trip `set -u`.)
  case "$variant" in
    demo|bench)         user_port="${BENCH_WEB_PUBLISH_PORT:-8000}" ;;
    fast|fast-physical)  user_port="${FRONTEND_PUBLISH_PORT:-8080}" ;;
  esac
  url="http://localhost:${user_port}$(url_path)"

  echo "Project: $project"
  echo "Variant: $variant"
  echo "URL:     $url"
  echo
  docker compose -p "$project" -f "$compose_file" ps
}

cmd_creds() {
  # Note: named site_name, not site — `site` collides with the global CLI-flag
  # variable of the same name that apply_cli_overrides reads (a `local site`
  # here would shadow it and trip `set -u` before apply_cli_overrides runs).
  local site_name creds admin_user admin_pass user_port_env user_port url

  load_env_file
  apply_cli_overrides
  resolve_ports_for_variant

  user_port_env=$(user_facing_port_env "$variant")
  user_port=${!user_port_env}
  url="http://localhost:${user_port}$(url_path)"
  site_name="${SITE_NAME:-huf.localhost}"

  if ! docker ps --filter name=^"${CREDS_CONTAINER}"$ --filter status=running --format '{{.Names}}' 2>/dev/null \
       | grep -qx "${CREDS_CONTAINER}"; then
    fatal "The credentials container (${CREDS_CONTAINER}) is not running. Run './docker/try.sh up' first."
  fi

  # For the demo variant the actual published bench port can be read from the
  # running container, which is more reliable than env vars in a fresh shell.
  if [[ "$variant" == "demo" ]]; then
    local actual_port
    actual_port=$(get_container_published_port "$CREDS_CONTAINER" 8000)
    [[ -n "$actual_port" ]] && user_port="$actual_port"
    url="http://localhost:${user_port}$(url_path)"
  fi

  # `|| true`: under `set -e`, a failing command inside `$(...)` (e.g. the file
  # not existing yet) would otherwise abort the script here silently, before
  # the intended fatal message below gets a chance to run.
  creds=$(read_credentials_from_container || true)
  if [[ -z "$creds" ]]; then
    fatal "Could not read credentials from ${CREDS_CONTAINER}:sites/${site_name}/.fasterdocker-credentials."
  fi

  admin_user=$(parse_credential_value ADMIN_USER "$creds")
  admin_pass=$(parse_credential_value ADMIN_PASSWORD "$creds")
  admin_user=${admin_user:-Administrator}

  echo "URL:      $url"
  echo "Site:     $site_name"
  echo "Username: $admin_user"
  echo "Password: $admin_pass"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
  parse_args "$@"

  # Resolve compose file early for the help path and for all subcommands.
  variant_to_compose "$variant"

  cd "$REPO_ROOT"

  case "$subcommand" in
    up)     cmd_up ;;
    down)   cmd_down ;;
    reset)  cmd_reset ;;
    logs)   cmd_logs ;;
    status) cmd_status ;;
    creds)  cmd_creds ;;
    *)      usage; exit 1 ;;
  esac
}

main "$@"
