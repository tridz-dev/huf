#!/usr/bin/env bash
# Runs the safe-deopt experiment end to end: deterministic pieces (no API key needed),
# the LLM-condition matrix (mocked unless MODEL + an API key are present), and the test
# suite. See README.md for what this benchmark tests and how to read its output.
#
# Usage:
#   bash run_all.sh              # deterministic pieces + mocked LLM-condition matrix
#   MODEL=<id> ANTHROPIC_API_KEY=<key> bash run_all.sh   # attempt a real LLM run
#   bash run_all.sh --replay     # re-score existing results/runs*.jsonl, no model calls
#
# Exit code is non-zero if anything below fails.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

REPLAY=0
for arg in "$@"; do
	case "$arg" in
	--replay)
		REPLAY=1
		;;
	*)
		echo "run_all.sh: unknown argument '$arg' (only --replay is supported)" >&2
		exit 2
		;;
	esac
done

PYTHON="${PYTHON:-python3}"
FAIL=0

section() {
	echo
	echo "=== $1 ==="
}

if [ "$REPLAY" -eq 1 ]; then
	section "Replay mode: re-scoring existing results/runs*.jsonl (no model calls)"
	"$PYTHON" run_experiment.py --replay
	if [ $? -ne 0 ]; then
		echo "[run_all.sh] replay aggregation FAILED" >&2
		FAIL=1
	else
		echo "[run_all.sh] replay aggregation OK"
	fi

	section "pytest -- benchmarks/safe-deopt/tests/"
	"$PYTHON" -m pytest tests/ -v
	PYTEST_STATUS=$?
	if [ $PYTEST_STATUS -ne 0 ]; then
		echo "[run_all.sh] pytest FAILED (exit $PYTEST_STATUS)" >&2
		FAIL=1
	else
		echo "[run_all.sh] pytest: all green"
	fi

	if [ "$FAIL" -ne 0 ]; then
		echo
		echo "run_all.sh --replay: FAILED"
		exit 1
	fi
	echo
	echo "run_all.sh --replay: ALL GREEN"
	exit 0
fi

# ---------------------------------------------------------------------------
# 1. Deterministic pieces -- no API key needed at all.
#    C2/C3 (conditions.py), fault injection (faults.py), the authority experiment
#    (authority_experiment.py), and the guard/condition unit tests are pure Python and
#    are exercised together by the test suite below plus a direct authority-experiment
#    run for a human-readable summary.
# ---------------------------------------------------------------------------

section "Deterministic authority experiment (authority_experiment.py) -- no API key needed"
"$PYTHON" authority_experiment.py
if [ $? -ne 0 ]; then
	echo "[run_all.sh] authority_experiment.py FAILED" >&2
	FAIL=1
else
	echo "[run_all.sh] authority_experiment.py OK"
fi

# ---------------------------------------------------------------------------
# 2. LLM-condition matrix (run_experiment.py). This runs C1-C6 for every workload/fault/
#    guarantee cell. C2/C3 are always deterministic (no model). C1/C4/C4+G/C5/C6 use
#    MockedModel unless a MODEL env var AND a recognized API key are both present, in
#    which case we attempt a real run via recovery_harness.LiveAPIModel -- which is
#    currently a documented stub that raises NotImplementedError. We do not swallow that;
#    we let it fail loudly and point at the gap, per the task brief.
# ---------------------------------------------------------------------------

HAVE_KEY=0
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${OPENAI_API_KEY:-}" ]; then
	HAVE_KEY=1
fi

if [ -n "${MODEL:-}" ] && [ "$HAVE_KEY" -eq 1 ]; then
	section "Real-LLM attempt: MODEL=${MODEL} (API key present)"
	echo "[run_all.sh] MODEL and an API key are both set -- attempting a real LiveAPIModel run."
	echo "[run_all.sh] NOTE: recovery_harness.LiveAPIModel.next_step() is a documented stub"
	echo "[run_all.sh]       that raises NotImplementedError by design (see recovery_harness.py)."
	echo "[run_all.sh]       This is expected to fail loudly below until a real client is wired in."
	"$PYTHON" - <<'PYEOF'
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) or ".")
from recovery_harness import LiveAPIModel

model = LiveAPIModel(model_id=os.environ.get("MODEL"))
try:
	model.next_step(transcript=[], available_tools=[])
	print("[run_all.sh] UNEXPECTED: LiveAPIModel.next_step() returned instead of raising -- "
	      "someone implemented it; update run_all.sh to actually run run_experiment.py against it.")
	sys.exit(1)
except NotImplementedError as exc:
	print(f"[run_all.sh] Confirmed gap, as expected: {exc}")
	print("[run_all.sh] Real LLM conditions are NOT runnable yet -- LiveAPIModel needs an "
	      "implementation (a real API client + tool-use parsing) before this path can proceed.")
	sys.exit(3)
PYEOF
	REAL_LLM_STATUS=$?
	if [ "$REAL_LLM_STATUS" -eq 3 ]; then
		echo "[run_all.sh] Real-LLM path stopped at the documented LiveAPIModel gap (exit 3, expected today)." >&2
		FAIL=1
	elif [ "$REAL_LLM_STATUS" -ne 0 ]; then
		echo "[run_all.sh] Real-LLM path FAILED unexpectedly (exit $REAL_LLM_STATUS)" >&2
		FAIL=1
	fi
	echo
	echo "[run_all.sh] Falling back to the mocked matrix below so the rest of the pipeline still runs."
fi

section "Pilot / mocked LLM-condition matrix (run_experiment.py)"
cat <<'BANNER'
##########################################################################
# PILOT / MOCKED RUN -- NOT A REAL LLM RUN.
#
# Every LLM condition (C1, C4, C4+G, C5, C6) below runs against
# recovery_harness.MockedModel, a deterministic scripted stand-in -- no
# network call, no real model, no real tokens. This is n=1 seed/cell per
# PREREGISTRATION.md's pilot-run-transparency commitment. See README.md's
# "Known limitations" section before citing any number from this run.
##########################################################################
BANNER
"$PYTHON" run_experiment.py
if [ $? -ne 0 ]; then
	echo "[run_all.sh] run_experiment.py FAILED" >&2
	FAIL=1
else
	echo "[run_all.sh] run_experiment.py OK (results/runs.mock.jsonl, results/summary.csv, results/plots/, results/breakeven.json)"
fi

# ---------------------------------------------------------------------------
# 3. Test suite -- final step, always run, reported clearly.
# ---------------------------------------------------------------------------

section "pytest -- benchmarks/safe-deopt/tests/"
"$PYTHON" -m pytest tests/ -v
PYTEST_STATUS=$?
if [ $PYTEST_STATUS -ne 0 ]; then
	echo "[run_all.sh] pytest FAILED (exit $PYTEST_STATUS)" >&2
	FAIL=1
else
	echo "[run_all.sh] pytest: all green"
fi

echo
if [ "$FAIL" -ne 0 ]; then
	echo "run_all.sh: FAILED -- see sections above"
	exit 1
fi
echo "run_all.sh: ALL GREEN"
exit 0
