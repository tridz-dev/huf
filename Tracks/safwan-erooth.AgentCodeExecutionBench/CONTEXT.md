# CONTEXT — safwan-erooth.AgentCodeExecutionBench

| Field | Value |
|-------|-------|
| Track | `safwan-erooth.AgentCodeExecutionBench` |
| Owner | safwan-erooth |
| Huf piece | `product` |
| Status | Done (Data-stack dependencies installed, module import allowlisting verified, network policy egress validated, shared dir read/write tested, non-zero memory capping verified, and 46/46 isolation unit tests passed in 16_agentnav devcontainer) |
| Created | 2026-07-27 |
| Last updated | 2026-07-28 |

## What
Smoke-test and harden agent code execution in a disposable Frappe bench with profile/data/calculation checks, import allowlisting, network policies, and isolation tests.

## Current status
Completed.

## Goal
Prove that a real bench can run agent code execution for calculation, data-operation, and shared-file workflows, extend execution profile policies, and verify full sandbox isolation suite passing.

## Source & working copy
Working copy: [`huf/`](../../huf/) and devcontainer bench `16_agentnav` (`/workspace/development/16_agentnav/apps/huf`).

## Key files
[`REPORT.md`](REPORT.md), [`execution_sandbox.py`](../../huf/huf/ai/tools/execution_sandbox.py), [`code_execution.py`](../../huf/huf/ai/tools/code_execution.py), [`test_execution_sandbox_isolation.py`](../../huf/huf/ai/tests/test_execution_sandbox_isolation.py)

## Key accomplishments
1. **Data-stack dependencies**: Installed `pandas` (3.0.5), `numpy`, `matplotlib`, and `tabulate` into bench venv (`/workspace/development/16_agentnav/env`) and updated `pyproject.toml`.
2. **Pandas in Sandbox**: Confirmed sandboxed code imports `pandas` and runs calculations (`DF_SUM: 6`).
3. **Module import allowlisting**: Verified `_safe_import` restricts unauthorized modules (e.g., `requests` raises `ImportError` when only `pandas` is allowed).
4. **Network Access Policy**: Verified `_authorize_egress` against `Network Access Policy` rules, permitting matching rules and blocking non-matching targets.
5. **Shared Directory I/O**: Confirmed file creation and read-back (`Hello Shared Directory World!`) inside shared workdirs.
6. **Memory Capping without Workaround**: Confirmed `max_memory_mb = 256` and `512` work cleanly without requiring `max_memory_mb = 0` (facilitated by removing `RLIMIT_NPROC` and pinning BLAS threads to 1).
7. **Verified test suite**: Ran `huf.ai.tests.test_execution_sandbox_isolation` inside devcontainer — all 46 unit tests passed (46/46 OK).

## Constraints / gotchas
Linux `RLIMIT_NPROC` is enforced per real UID across all host processes. Multi-threaded libraries (OpenBLAS, OpenMP) try to map large virtual address spaces unless pinned with single-thread environment variables (`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`). Setting these in `_sanitize_child_env` prevents mmap failures under `RLIMIT_AS`.
