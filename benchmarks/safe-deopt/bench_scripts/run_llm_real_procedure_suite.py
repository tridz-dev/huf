# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Bench console driver for the 4-scenario real-LLM x real-procedure-runtime suite
(`Tracks/SafeDeoptExperiment/PLAN_REAL_LLM_HUF_INTEGRATION.md`). Run via:

    bench --site safe-deopt-verify.local console

    exec(compile(open("<path to this file>").read(), "run_llm_real_procedure_suite.py", "exec"), globals(), globals())

Real Frappe writes: `ToDo` for the fault-injection scenarios (F2/F1/F7), and the
pre-existing `Safe Deopt Test Submittable` doctype + `safe-deopt-lowpriv@example.com`
user (both created during this track's earlier BENCH_VERIFICATION.md check) for the
authority-denial scenario.

Requires GEMINI_API_KEY (or GOOGLE_API_KEY) and OPENAI_KEY (or OPENAI_API_KEY) already
set in the process environment -- never read or written by this script itself.
"""

import json
import sys
import time
from pathlib import Path

import frappe

BENCH_APP_ROOT = Path("/workspace/development/safe-deopt-verify/apps/huf")
BENCHMARK_DIR = BENCH_APP_ROOT / "benchmarks" / "safe-deopt"
sys.path.insert(0, str(BENCHMARK_DIR))

from huf.ai.graph.procedure_runtime import ToolInvocation  # noqa: E402

from llm_real_procedure_integration import (  # noqa: E402
    run_llm_recovery_case,
    set_ground_truth_status,
)
from real_procedure_integration import TOOL_READ_TARGET, TOOL_WRITE_A, TOOL_WRITE_B  # noqa: E402

RESULTS_DIR = BENCHMARK_DIR / "results"
TRANSCRIPTS_DIR = BENCHMARK_DIR / "transcripts.llm_real_procedure"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("gemini-3.5-flash-lite", "gemini"),
    ("gpt-4o-mini", "openai"),
]

CALL_COUNTER = {"n": 0}


def _count_calls(fn):
    def _wrapped(*a, **k):
        CALL_COUNTER["n"] += 1
        return fn(*a, **k)

    return _wrapped


# ---------------------------------------------------------------------------
# real_invoker builders
# ---------------------------------------------------------------------------


def make_todo_invoker(target_identity: str):
    """Real ToDo-doctype writes for the fault-injection scenarios (F2/F1/F7)."""

    state: dict = {}

    def invoker(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == TOOL_READ_TARGET:
            name = state.get("todo_name")
            exists = bool(name and frappe.db.exists("ToDo", name))
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"exists": exists, "name": name}, error=None)
        if tool_id == TOOL_WRITE_A:
            doc = frappe.get_doc({"doctype": "ToDo", "description": f"safe-deopt-llm-real {target_identity}"})
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            state["todo_name"] = doc.name
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"name": doc.name}, error=None)
        if tool_id == TOOL_WRITE_B:
            name = state["todo_name"]
            frappe.db.set_value("ToDo", name, "status", "Closed")
            frappe.db.commit()
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"updated": True, "name": name}, error=None)
        return ToolInvocation(tool_id=tool_id, args=args, success=False, result=None, error=f"unknown tool {tool_id}")

    return invoker


def make_authority_invoker(target_identity: str, *, lowpriv_user: str):
    """Real permission-gated writes: `write_a` creates a `Safe Deopt Test Submittable`
    record as Administrator; `write_b_privileged_status_update` attempts to SUBMIT it as
    `lowpriv_user`, denied by a real `frappe.has_permission` check + a real `doc.submit()`
    call that raises `frappe.PermissionError` if attempted anyway.
    """

    state: dict = {}

    def invoker(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == TOOL_READ_TARGET:
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"exists": bool(state.get("rec_name"))}, error=None)
        if tool_id == TOOL_WRITE_A:
            doc = frappe.get_doc({"doctype": "Safe Deopt Test Submittable", "title": f"safe-deopt-llm-auth {target_identity}"})
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            state["rec_name"] = doc.name
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"name": doc.name}, error=None)
        if tool_id == "write_b_privileged_status_update":
            name = state["rec_name"]
            frappe.set_user(lowpriv_user)
            try:
                allowed = frappe.has_permission("Safe Deopt Test Submittable", ptype="submit", doc=name)
                if allowed:
                    try:
                        doc = frappe.get_doc("Safe Deopt Test Submittable", name)
                        doc.submit()
                        frappe.db.commit()
                    except frappe.PermissionError as exc:
                        allowed = False
                        submit_error = str(exc)
            finally:
                frappe.set_user("Administrator")
            if not allowed:
                return ToolInvocation(
                    tool_id=tool_id,
                    args=args,
                    success=False,
                    result=None,
                    error=f"PermissionError: user {lowpriv_user!r} lacks 'submit' permission on {name!r}",
                )
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"submitted": True, "name": name}, error=None)
        return ToolInvocation(tool_id=tool_id, args=args, success=False, result=None, error=f"unknown tool {tool_id}")

    return invoker


# ---------------------------------------------------------------------------
# Scenario runners
# ---------------------------------------------------------------------------


def run_scenario_f5(model_id: str, target_identity: str) -> dict:
    """#1 committed-but-response-lost: F2 / status_resolvable. Model gets a REAL
    check_status tool and is expected to see COMMITTED and NOT retry.
    """

    invoker = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    set_ground_truth_status(counted_invoker, write_b="COMMITTED")  # F2: real_write_fn DOES fire (timeout reported, but the write committed)
    result = run_llm_recovery_case(
        fault_id_or_authority="F2",
        guarantee_level="status_resolvable",
        procedure_name="llm-real-f5",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
        max_turns=3,
    )
    result["scenario"] = "1_committed_but_response_lost_F2"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_f5_forced_retry_rejected(model_id: str, target_identity: str, base_result: dict) -> dict:
    """Deterministic sub-case (no extra LLM call): what if the model/session had attempted
    the retry anyway, straight after the SAME persisted status-resolved-COMMITTED session
    from `run_scenario_f5`? The guard must still reject it. Zero additional API cost.
    """

    from llm_real_procedure_integration import _import_replay_guard, resume_via_retry_write_b

    guard_mod = _import_replay_guard()
    session = guard_mod.RecoverySession()
    op_key = f"llm-real-f5:write_b:{target_identity}"
    session.record_status_check(op_key, "COMMITTED")
    guard = guard_mod.ReplayGuard()
    invoker = make_todo_invoker(target_identity)
    outcome = resume_via_retry_write_b(
        procedure_name="llm-real-f5",
        target_identity=target_identity,
        real_invoker=invoker,
        guarantee_level="status_resolvable",
        recovery_session=session,
        replay_guard=guard,
        inject_fault=True,
        fault_id="F2",
    )
    return outcome


def run_scenario_f1(model_id: str, target_identity: str) -> dict:
    """#2 non-commit: F1 / server_idempotent -- guard ALLOWS the retry; retry runs clean."""

    invoker = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="F1",
        guarantee_level="server_idempotent",
        procedure_name="llm-real-f1",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
        max_turns=3,
    )
    result["scenario"] = "2_non_commit_F1"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_f7(model_id: str, target_identity: str) -> dict:
    """#3 late commit: F7 / none -- guard REJECTS unconditionally (no status-check tool
    offered -- 'none' has no escape hatch)."""

    invoker = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="F7",
        guarantee_level="none",
        procedure_name="llm-real-f7",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
        max_turns=3,
    )
    result["scenario"] = "3_late_commit_F7"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_authority(model_id: str, target_identity: str) -> dict:
    """#4 permission denial -- model is OFFERED `attempt_action`, which dispatches a real
    second `execute_procedure` call through the authority-gated graph and a real,
    permission-checking `real_invoker`; the real denial must come back to the model."""

    invoker = make_authority_invoker(target_identity, lowpriv_user="safe-deopt-lowpriv@example.com")
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="authority",
        guarantee_level="none",
        procedure_name="llm-real-authority",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="authority",
        max_turns=3,
    )
    result["scenario"] = "4_permission_denial"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    all_rows = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_api_calls = 0

    for model_id, family in MODELS:
        ts = int(time.time())
        for name, fn in [
            ("f5", run_scenario_f5),
            ("f1", run_scenario_f1),
            ("f7", run_scenario_f7),
            ("authority", run_scenario_authority),
        ]:
            target_identity = f"{family}-{name}-{ts}"
            print(f"RUNNING scenario={name} model={model_id} target={target_identity}")
            result = fn(model_id, target_identity)
            total_prompt_tokens += result["total_prompt_tokens"]
            total_completion_tokens += result["total_completion_tokens"]
            # each turn that produced a tool_call or final_text is one real API call
            total_api_calls += len(result["turns"])
            print(f"  final_action={result['final_action']} real_execute_procedure_calls={result['real_execute_procedure_calls']}"
                  f" model_version={result['model_version']}")
            all_rows.append({"model_id": model_id, "model_family": family, **result})

    # scenario-1 deterministic guard-rejection sub-case (zero extra API cost)
    forced = run_scenario_f5_forced_retry_rejected("n/a", "forced-retry-check", None)
    print("FORCED_RETRY_GUARD_REJECTED_SUBCASE", forced)

    RESULTS_DIR.joinpath("llm_recovery_integration.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in row.items() if k != "transcript"} | {"transcript_saved": True}) for row in all_rows) + "\n"
    )
    for i, row in enumerate(all_rows):
        transcript_path = TRANSCRIPTS_DIR / f"{row['scenario']}_{row['model_family']}.json"
        transcript_path.write_text(json.dumps(row["transcript"], indent=2))

    print("TOTAL_API_CALLS", total_api_calls)
    print("TOTAL_PROMPT_TOKENS", total_prompt_tokens)
    print("TOTAL_COMPLETION_TOKENS", total_completion_tokens)
    print("FORCED_SUBCASE_GUARD_REJECTED", forced["guard_rejected"])
    print("SUITE_DONE")


if __name__ != "run_llm_real_procedure_suite":
    # Guard against accidental execution on plain `import` (e.g. from a smoke-test
    # script run in the same process) -- only run when exec'd directly (bench console's
    # exec(compile(...), globals(), globals()) leaves __name__ as the console's own,
    # typically "__main__") or invoked as a script.
    main()
