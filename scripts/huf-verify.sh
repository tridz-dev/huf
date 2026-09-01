#!/usr/bin/env bash
#
# huf-verify.sh — the single verification entry point for this repo (GOAL.md §21).
#
# Both humans and coding agents MUST use this script instead of inventing
# ad-hoc test commands. If a check needs to change, change it here.
#
# Usage:
#   ./scripts/huf-verify.sh <target> [--base <ref>]
#
# Targets:
#   quick     - frontend typecheck + frontend unit tests + design parity (no bench needed)
#   frontend  - quick + production build (no bench needed)
#   backend   - `bench --site <site> run-tests --app huf` against a reachable bench
#               (optionally scoped to one module — see HUF_BACKEND_MODULE below)
#   e2e       - mocked/offline Playwright suite, fast subset (no bench needed)
#   security  - Semgrep static analysis (skipped gracefully if semgrep isn't installed)
#   full      - frontend + full mocked Playwright (incl. visual/a11y) + security,
#               plus deployed Playwright and backend tests IF a bench is reachable
#               (each is skipped with a clear warning, not a hard failure, if not)
#   changed   - diff against a base ref (default: develop) and run only the
#               subset of the above relevant to what changed
#
# Env vars:
#   HUF_BENCH_CONTAINER   docker container running the bench (default: frappe_docker_devcontainer-frappe-1)
#   HUF_BENCH_SITE        site name inside that bench (auto-detected if unset)
#   HUF_BENCH_PATH        bench directory inside the container (auto-detected if unset)
#   HUF_BACKEND_MODULE    dotted module path to scope `backend`/`full` backend tests to
#   HUF_VERIFY_BASE       base ref for `changed` (default: develop), overridable via --base
#   BASE_URL / E2E_BASE_URL  passed through to the deployed Playwright config as-is
#
# File -> target mapping used by `changed` (kept intentionally simple, not clever):
#   frontend/e2e/**      -> e2e (mocked, fast subset)
#   frontend/**          -> frontend (typecheck + unit + build + design parity)
#   huf/**  (*.py)        -> backend (scoped to huf/ai/tests/test_<basename>.py if it
#                            exists as a dotted module, else the full `--app huf` suite)
#   anything else         -> no targeted check added (falls back to `quick` if nothing matched)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
CHECK_NAMES=()
CHECK_RESULTS=()   # PASS | FAIL | SKIP
CHECK_NOTES=()
FAIL_COUNT=0

record() {
  CHECK_NAMES+=("$1")
  CHECK_RESULTS+=("$2")
  CHECK_NOTES+=("$3")
  if [ "$2" = "FAIL" ]; then
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

run_check() {
  # run_check "display name" cmd arg1 arg2 ...
  local name="$1"; shift
  echo ""
  echo "===== RUNNING: ${name} ====="
  echo "+ $*"
  if "$@"; then
    record "$name" PASS ""
    echo "===== PASS: ${name} ====="
  else
    local code=$?
    record "$name" FAIL "exit ${code}"
    echo "===== FAIL: ${name} (exit ${code}) ====="
  fi
}

skip_check() {
  local name="$1" reason="$2"
  echo ""
  echo "===== SKIPPED: ${name} (${reason}) ====="
  record "$name" SKIP "$reason"
}

print_summary() {
  echo ""
  echo "================ huf-verify summary ================"
  local i
  for i in "${!CHECK_NAMES[@]}"; do
    local status="${CHECK_RESULTS[$i]}"
    local mark="?"
    case "$status" in
      PASS) mark="PASS" ;;
      FAIL) mark="FAIL" ;;
      SKIP) mark="SKIP" ;;
    esac
    local note="${CHECK_NOTES[$i]}"
    if [ -n "$note" ]; then
      printf '  [%s] %s (%s)\n' "$mark" "${CHECK_NAMES[$i]}" "$note"
    else
      printf '  [%s] %s\n' "$mark" "${CHECK_NAMES[$i]}"
    fi
  done
  echo "======================================================"
  if [ "$FAIL_COUNT" -eq 0 ]; then
    echo "RESULT: PASS (${#CHECK_NAMES[@]} checks run, 0 failed)"
  else
    echo "RESULT: FAIL (${FAIL_COUNT} of ${#CHECK_NAMES[@]} checks failed)"
  fi
}

# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------
do_typecheck() {
  run_check "frontend:typecheck" bash -c "cd '$FRONTEND_DIR' && npx tsc -b"
}

do_unit() {
  run_check "frontend:unit" bash -c "cd '$FRONTEND_DIR' && npm run test"
}

do_build() {
  run_check "frontend:build" bash -c "cd '$FRONTEND_DIR' && npm run build"
}

do_design() {
  run_check "frontend:design-parity" bash -c "cd '$FRONTEND_DIR' && npm run check:design"
}

do_e2e_fast() {
  # Fast subset: every mocked spec except the two slow/flaky-by-nature ones
  # (visual-regression does pixel-diffing, accessibility runs axe-core over
  # every page) — those two run under `e2e:mocked (full suite)` in `full`.
  run_check "e2e:mocked (fast subset)" bash -c "
    cd '$FRONTEND_DIR' &&
    specs=\$(ls e2e/*.spec.ts | grep -v -e visual-regression.spec.ts -e accessibility.spec.ts) &&
    npx playwright test -c playwright.config.ts \$specs
  "
}

do_e2e_full() {
  run_check "e2e:mocked (full suite incl. visual/a11y)" bash -c "cd '$FRONTEND_DIR' && npx playwright test -c playwright.config.ts"
}

do_security() {
  if ! command -v semgrep >/dev/null 2>&1; then
    skip_check "security:semgrep" "semgrep is not installed — install it (e.g. 'pip install semgrep' or 'brew install semgrep') to run this check"
    return 0
  fi
  run_check "security:semgrep" bash -c "cd '$ROOT' && semgrep --config .semgrep.yml huf/"
}

# ---- bench discovery for the `backend` / deployed-e2e checks ----
BENCH_CONTAINER="${HUF_BENCH_CONTAINER:-frappe_docker_devcontainer-frappe-1}"
BENCH_SITE="${HUF_BENCH_SITE:-}"
BENCH_PATH="${HUF_BENCH_PATH:-}"
BENCH_DETECTED=0

detect_bench() {
  [ "$BENCH_DETECTED" = "1" ] && return 0
  command -v docker >/dev/null 2>&1 || return 1
  docker exec "$BENCH_CONTAINER" true >/dev/null 2>&1 || return 1

  if [ -n "$BENCH_SITE" ] && [ -n "$BENCH_PATH" ]; then
    : # both given explicitly, trust the caller
  elif [ -n "$BENCH_SITE" ]; then
    BENCH_PATH=$(docker exec "$BENCH_CONTAINER" bash -c "for b in /workspace/benches/*/; do [ -d \"\${b}sites/${BENCH_SITE}\" ] && echo \"\$b\" && break; done" 2>/dev/null)
  else
    local found
    found=$(docker exec "$BENCH_CONTAINER" bash -c '
      for b in /workspace/benches/*/; do
        for s in "$b"sites/*/; do
          sn=$(basename "$s")
          if [ -f "${s}site_config.json" ]; then
            echo "${b}|${sn}"
          fi
        done
      done
    ' 2>/dev/null | head -1)
    [ -z "$found" ] && return 1
    BENCH_PATH="${found%%|*}"
    BENCH_SITE="${found##*|}"
  fi

  [ -z "$BENCH_PATH" ] && return 1
  [ -z "$BENCH_SITE" ] && return 1

  docker exec "$BENCH_CONTAINER" bash -c "cd '$BENCH_PATH' && bench --site '$BENCH_SITE' list-apps" >/dev/null 2>&1 || return 1
  BENCH_DETECTED=1
  return 0
}

bench_error_message() {
  cat <<EOF
No reachable Frappe bench found (container='${BENCH_CONTAINER}').
  - Set HUF_BENCH_SITE (and optionally HUF_BENCH_CONTAINER / HUF_BENCH_PATH) to
    point at a running bench, or
  - Provision a disposable bench first — see the 'frappe-multihand' skill
    (mh-tools/provision.sh) to spin one up in the shared Docker devcontainer.
EOF
}

do_backend() {
  local module="${1:-${HUF_BACKEND_MODULE:-}}"
  if ! detect_bench; then
    echo "$(bench_error_message)"
    record "backend:run-tests" FAIL "no bench reachable"
    return 1
  fi
  echo "Using bench: container=${BENCH_CONTAINER} path=${BENCH_PATH} site=${BENCH_SITE}"

  local name cmd_str out rc
  if [ -n "$module" ]; then
    name="backend:run-tests (--module ${module})"
    cmd_str="cd '$BENCH_PATH' && bench --site '$BENCH_SITE' run-tests --app huf --module '$module'"
  else
    name="backend:run-tests (--app huf)"
    cmd_str="cd '$BENCH_PATH' && bench --site '$BENCH_SITE' run-tests --app huf"
  fi

  echo ""
  echo "===== RUNNING: ${name} ====="
  echo "+ docker exec ${BENCH_CONTAINER} bash -c \"${cmd_str}\""
  out=$(docker exec "$BENCH_CONTAINER" bash -c "$cmd_str" 2>&1)
  rc=$?
  echo "$out"

  # NOTE: bench's `run-tests` (python unittest runner underneath) has a known
  # quirk where the process can exit 0 even when tests failed/errored — it is
  # NOT safe to trust $rc alone here. Treat the printed "FAILED (...)"/"OK"
  # summary line as the source of truth, falling back to $rc if neither marker
  # is present (e.g. a bench/import-time crash with no unittest summary at all).
  if echo "$out" | grep -qE '^FAILED \('; then
    record "$name" FAIL "unittest reported failures/errors (exit ${rc})"
    echo "===== FAIL: ${name} (unittest reported failures/errors) ====="
  elif echo "$out" | grep -qE '^OK($| \()'; then
    record "$name" PASS ""
    echo "===== PASS: ${name} ====="
  elif [ "$rc" -eq 0 ]; then
    record "$name" PASS ""
    echo "===== PASS: ${name} ====="
  else
    record "$name" FAIL "exit ${rc}, no unittest summary line found"
    echo "===== FAIL: ${name} (exit ${rc}) ====="
  fi
}

do_backend_or_skip() {
  local module="${1:-${HUF_BACKEND_MODULE:-}}"
  if detect_bench; then
    do_backend "$module"
  else
    skip_check "backend:run-tests" "no bench reachable — $(bench_error_message | tr '\n' ' ')"
  fi
}

do_deployed_or_skip() {
  if ! detect_bench; then
    skip_check "e2e:deployed" "no bench reachable — deployed Playwright suite needs a live, built bench (see 'frappe-multihand' skill)"
    return 0
  fi
  # A bench being reachable via `docker exec` (for `bench` CLI commands) does
  # NOT mean it's reachable over HTTP from wherever *this script* runs — the
  # deployed Playwright suite runs as a real browser process on the host, not
  # inside the bench's container, so it needs the site's actual host-mapped
  # URL. Probe BASE_URL/E2E_BASE_URL (or the config's own default) before
  # spending time on a doomed Playwright run.
  local probe_url="${BASE_URL:-${E2E_BASE_URL:-http://192.168.97.6:8000/huf/}}"
  if ! curl -sf -m 5 -o /dev/null "$probe_url" 2>/dev/null; then
    skip_check "e2e:deployed" "bench detected via docker exec, but '${probe_url}' is not reachable over HTTP from here — set BASE_URL/E2E_BASE_URL to this bench's host-mapped address if one exists, or run this check from inside the devcontainer"
    return 0
  fi
  run_check "e2e:deployed" bash -c "cd '$FRONTEND_DIR' && npx playwright test -c playwright.deployed.config.ts"
}

do_nightly_note() {
  # The nightly cross-browser suite runs on its own schedule (not on every
  # `full`, which is meant to be runnable on demand without a long cross-
  # browser matrix) — this is a visibility note, not a check, so it does not
  # affect the PASS/FAIL summary or exit code.
  if [ -f "$FRONTEND_DIR/playwright.nightly.config.ts" ]; then
    echo ""
    echo "NOTE: playwright.nightly.config.ts exists but is intentionally not run by 'full'"
    echo "      (cross-browser matrix, meant for a scheduled/nightly job). Run it explicitly with:"
    echo "      cd frontend && npx playwright test -c playwright.nightly.config.ts"
  else
    echo ""
    echo "NOTE: playwright.nightly.config.ts does not exist yet in this worktree — follow-up:"
    echo "      wire a nightly-cross-browser target into this script once it lands."
  fi
}

# ---------------------------------------------------------------------------
# `changed` target
# ---------------------------------------------------------------------------
map_backend_module() {
  local f="$1"
  local base
  base=$(basename "$f" .py)
  local candidate="huf/ai/tests/test_${base}.py"
  if [ -f "$ROOT/$candidate" ]; then
    echo "${candidate%.py}" | tr '/' '.'
  fi
}

do_changed() {
  local base_ref="${BASE_REF_OVERRIDE:-${HUF_VERIFY_BASE:-develop}}"
  echo "Diffing against base ref: ${base_ref}"

  local changed_files
  changed_files=$(git -C "$ROOT" diff --name-only "${base_ref}...HEAD" 2>/dev/null)
  if [ -z "$changed_files" ]; then
    changed_files=$(git -C "$ROOT" diff --name-only "${base_ref}" 2>/dev/null)
  fi

  if [ -z "$changed_files" ]; then
    echo "No diff found against '${base_ref}' (bad ref, or no changes). Falling back to 'quick'."
    do_typecheck
    do_unit
    do_design
    return 0
  fi

  echo "Changed files vs ${base_ref}:"
  echo "$changed_files" | sed 's/^/  /'

  local run_frontend=0 run_e2e=0 run_backend=0
  local backend_modules=()
  local unmapped_backend=0

  while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
      frontend/e2e/*)
        run_e2e=1
        ;;
      frontend/*)
        run_frontend=1
        ;;
      huf/*.py)
        run_backend=1
        local mod
        mod=$(map_backend_module "$f")
        if [ -n "$mod" ]; then
          backend_modules+=("$mod")
        else
          unmapped_backend=1
        fi
        ;;
    esac
  done <<< "$changed_files"

  if [ "$run_frontend" -eq 0 ] && [ "$run_e2e" -eq 0 ] && [ "$run_backend" -eq 0 ]; then
    echo "Changed files don't match any known target bucket — running 'quick' as a safe default."
    do_typecheck
    do_unit
    do_design
    return 0
  fi

  if [ "$run_frontend" -eq 1 ]; then
    echo "-> frontend files changed: running typecheck + unit + build + design parity"
    do_typecheck
    do_unit
    do_build
    do_design
  fi

  if [ "$run_e2e" -eq 1 ]; then
    echo "-> frontend/e2e/** changed: running mocked Playwright (fast subset)"
    do_e2e_fast
  fi

  if [ "$run_backend" -eq 1 ]; then
    if [ "$unmapped_backend" -eq 1 ] || [ "${#backend_modules[@]}" -eq 0 ]; then
      echo "-> huf/**.py changed with no 1:1 test-module mapping: running full backend suite"
      do_backend ""
    else
      echo "-> huf/**.py changed, mapped to modules: ${backend_modules[*]}"
      local seen=()
      local m
      for m in "${backend_modules[@]}"; do
        case " ${seen[*]-} " in *" $m "*) continue ;; esac
        seen+=("$m")
        do_backend "$m"
      done
    fi
  fi
}

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------
TARGET="${1:-}"
shift || true

BASE_REF_OVERRIDE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base)
      BASE_REF_OVERRIDE="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

usage() {
  cat <<'EOF'
Usage: ./scripts/huf-verify.sh <target> [--base <ref>]

Targets: quick | backend | frontend | e2e | security | full | changed

See the header comment in this script for what each target runs and for
relevant env vars (HUF_BENCH_SITE, HUF_BENCH_CONTAINER, HUF_BENCH_PATH,
HUF_BACKEND_MODULE, HUF_VERIFY_BASE).
EOF
}

case "$TARGET" in
  quick)
    echo "Target: quick — fastest useful signal, no bench needed"
    do_typecheck
    do_unit
    do_design
    ;;
  frontend)
    echo "Target: frontend — full frontend check, no bench needed"
    do_typecheck
    do_unit
    do_build
    do_design
    ;;
  backend)
    echo "Target: backend — bench run-tests --app huf"
    do_backend ""
    ;;
  e2e)
    echo "Target: e2e — mocked/offline Playwright, fast subset"
    do_e2e_fast
    ;;
  security)
    echo "Target: security — semgrep static analysis"
    do_security
    ;;
  full)
    echo "Target: full — everything, degrading gracefully where no bench is reachable"
    do_typecheck
    do_unit
    do_build
    do_design
    do_e2e_full
    do_nightly_note
    do_security
    do_backend_or_skip
    do_deployed_or_skip
    ;;
  changed)
    echo "Target: changed — diff-based subset"
    do_changed
    ;;
  *)
    usage
    exit 2
    ;;
esac

print_summary
[ "$FAIL_COUNT" -eq 0 ]
exit $?
