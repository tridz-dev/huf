# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Bench console driver for the 5-scenario real-LLM x real-procedure-runtime suite
(`Tracks/SafeDeoptExperiment/ACCEPTANCE_PLAN_V2.md` §3, task T4). Run via:

    bench --site safe-deopt-verify.local console

    exec(compile(open("<path to this file>").read(), "run_llm_real_procedure_suite_v2.py", "exec"), globals(), globals())

This is the T4 rewrite of `run_llm_real_procedure_suite.py` (kept on disk, superseded --
see that file's own docstring and REPORT_LLM_RECOVERY_INTEGRATION.md for why). Differences:

- 5 scenarios, not 4: adds S4 (clean pre-dispatch rejection, then a PERMITTED successful
  retry -- fault F1). S2's fault id is corrected from F1 to F3 (see
  `llm_real_procedure_integration.py`'s module docstring "Fault/scenario mapping" for the
  full corrected mapping and why).
- Every retry now goes through the REAL wired runtime replay guard
  (`execute_procedure(replay_guard_enabled=True, ...)`), never a standalone copy --
  `resume_via_retry_write_b` no longer takes a `recovery_session`/`replay_guard` argument.
- S3 (late commit, F7) explicitly drains the held write (`drain_result`) before its
  final-state check, and this script additionally re-reads the ToDo directly to confirm
  no duplicate `ToDo` was created for the same `target_identity`.
- S5 (permission denial) explicitly asserts the SAME `lowpriv_user` identity is used for
  BOTH the original denial and the recovery `attempt_action` call, and confirms zero
  unauthorized effect (`docstatus` stays 0, i.e. never submitted) via a direct Frappe read
  after the run.

Real Frappe writes: `ToDo` for the fault-injection scenarios (F2/F3/F7/F1), and the
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
TRANSCRIPTS_DIR = BENCHMARK_DIR / "transcripts.llm_real_procedure_v2"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

MODELS = [
    ("gemini-3.5-flash-lite", "gemini"),
    ("gpt-4o-mini", "openai"),
]

LOWPRIV_USER = "safe-deopt-lowpriv@example.com"

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
    """Real ToDo-doctype writes for the fault-injection scenarios (F2/F3/F7/F1). No
    prefilled status dict anywhere -- `frappe.db.exists` / `frappe.db.get_value` are the
    only source of truth `read_target`/status-check tools ever see.
    """

    state: dict = {}

    def invoker(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == TOOL_READ_TARGET:
            name = state.get("todo_name")
            exists = bool(name and frappe.db.exists("ToDo", name))
            status = frappe.db.get_value("ToDo", name, "status") if exists else None
            return ToolInvocation(
                tool_id=tool_id, args=args, success=True, result={"exists": exists, "name": name, "status": status}, error=None
            )
        if tool_id == TOOL_WRITE_A:
            doc = frappe.get_doc({"doctype": "ToDo", "description": f"safe-deopt-llm-real-v2 {target_identity}"})
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

    return invoker, state


def make_authority_invoker(target_identity: str, *, lowpriv_user: str):
    """Real permission-gated writes: `write_a` creates a `Safe Deopt Test Submittable`
    record as Administrator; `write_b_privileged_status_update` attempts to SUBMIT it as
    `lowpriv_user` -- denied by a real `frappe.has_permission` check (the real Frappe
    authorization boundary) plus a real `doc.submit()` call that raises
    `frappe.PermissionError` if somehow attempted anyway. The SAME closure (and therefore
    the SAME `lowpriv_user`) is reused for both the original denial and any later recovery
    `attempt_action` call -- there is only ever one identity here.
    """

    state: dict = {}

    def invoker(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == TOOL_READ_TARGET:
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"exists": bool(state.get("rec_name"))}, error=None)
        if tool_id == TOOL_WRITE_A:
            doc = frappe.get_doc({"doctype": "Safe Deopt Test Submittable", "title": f"safe-deopt-llm-authv2 {target_identity}"})
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            state["rec_name"] = doc.name
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"name": doc.name}, error=None)
        if tool_id == "write_b_privileged_status_update":
            name = state["rec_name"]
            frappe.set_user(lowpriv_user)
            allowed = False
            try:
                allowed = frappe.has_permission("Safe Deopt Test Submittable", ptype="submit", doc=name)
                if allowed:
                    try:
                        doc = frappe.get_doc("Safe Deopt Test Submittable", name)
                        doc.submit()
                        frappe.db.commit()
                    except frappe.PermissionError:
                        allowed = False
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

    return invoker, state


# ---------------------------------------------------------------------------
# Scenario runners (fault ids per llm_real_procedure_integration.py's corrected mapping)
# ---------------------------------------------------------------------------


def run_scenario_s1(model_id: str, target_identity: str) -> dict:
    """S1 committed, response lost: F2 / status_resolvable."""

    invoker, _state = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    set_ground_truth_status(counted_invoker, write_b="COMMITTED")
    result = run_llm_recovery_case(
        fault_id_or_authority="F2",
        guarantee_level="status_resolvable",
        procedure_name="llm-v2-s1",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
    )
    result["scenario"] = "S1_committed_response_lost_F2"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_s1_forced_retry_rejected(target_identity: str) -> dict:
    """Deterministic sub-case (zero extra API cost): given a session that already knows
    write_b is COMMITTED, the REAL wired guard must still reject a forced retry attempt --
    exercised directly against `resume_via_retry_write_b`, through one real
    `execute_procedure` call, guard enabled.
    """

    from llm_real_procedure_integration import resume_via_retry_write_b

    invoker, _state = make_todo_invoker(target_identity)
    outcome = resume_via_retry_write_b(
        procedure_name="llm-v2-s1",
        target_identity=target_identity,
        real_invoker=invoker,
        guarantee_level="status_resolvable",
        known_status="COMMITTED",
        inject_fault=True,
        fault_id="F2",
    )
    return outcome


def run_scenario_s2(model_id: str, target_identity: str) -> dict:
    """S2 did NOT commit, ambiguous timeout: F3 / server_idempotent -- guard ALLOWS the
    retry (rule 2a, unconditional for server_idempotent); the real second attempt inside
    the SAME execute_procedure call is unfaulted and should commit for real."""

    invoker, _state = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="F3",
        guarantee_level="server_idempotent",
        procedure_name="llm-v2-s2",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
    )
    result["scenario"] = "S2_not_committed_ambiguous_timeout_F3"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_s3(model_id: str, target_identity: str) -> dict:
    """S3 late commit after inconclusive read: F7 / none -- guard REJECTS unconditionally
    (rule 4, no escape hatch for "none"); the held write from the ORIGINAL run is drained
    before the final-state check (`drain_result` in the returned dict)."""

    invoker, state = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="F7",
        guarantee_level="none",
        procedure_name="llm-v2-s3",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
    )
    result["scenario"] = "S3_late_commit_F7"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    # Extra, real-persisted-state confirmation that no duplicate ToDo exists for this
    # target_identity after the drain: count matching ToDos directly.
    matching = frappe.get_all("ToDo", filters={"description": f"safe-deopt-llm-real-v2 {target_identity}"})
    result["post_drain_todo_count"] = len(matching)
    return result


def run_scenario_s4(model_id: str, target_identity: str) -> dict:
    """S4 clean pre-dispatch rejection, then a PERMITTED successful retry: F1 /
    server_idempotent. F4 (concurrent-drift, robustness_only per ACCEPTANCE_PLAN_V2.md §2)
    is deliberately NOT used here or anywhere in this suite."""

    invoker, _state = make_todo_invoker(target_identity)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="F1",
        guarantee_level="server_idempotent",
        procedure_name="llm-v2-s4",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="fault",
    )
    result["scenario"] = "S4_reject_then_permitted_retry_F1"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    return result


def run_scenario_s5(model_id: str, target_identity: str) -> dict:
    """S5 permission denial, including an attempted recovery write under the SAME
    restricted identity. `attempt_action` re-dispatches through the SAME `real_invoker`
    closure (same `lowpriv_user`), never a different identity."""

    invoker, state = make_authority_invoker(target_identity, lowpriv_user=LOWPRIV_USER)
    counted_invoker = _count_calls(invoker)
    result = run_llm_recovery_case(
        fault_id_or_authority="authority",
        guarantee_level="none",
        procedure_name="llm-v2-s5",
        target_identity=target_identity,
        real_invoker=counted_invoker,
        model_id=model_id,
        scenario_kind="authority",
    )
    result["scenario"] = "S5_permission_denial_same_identity"
    result["real_invoker_calls"] = CALL_COUNTER["n"]
    CALL_COUNTER["n"] = 0
    # Zero-unauthorized-effect check: read the record directly and confirm it was never
    # submitted (docstatus stays 0), regardless of how many attempt_action calls happened.
    rec_name = state.get("rec_name")
    docstatus = frappe.db.get_value("Safe Deopt Test Submittable", rec_name, "docstatus") if rec_name else None
    result["zero_unauthorized_effect_check"] = {"rec_name": rec_name, "docstatus": docstatus, "unauthorized_effect": bool(docstatus)}
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
            ("s1", run_scenario_s1),
            ("s2", run_scenario_s2),
            ("s3", run_scenario_s3),
            ("s4", run_scenario_s4),
            ("s5", run_scenario_s5),
        ]:
            target_identity = f"{family}-{name}-{ts}"
            print(f"RUNNING scenario={name} model={model_id} target={target_identity}")
            result = fn(model_id, target_identity)
            total_prompt_tokens += result["total_prompt_tokens"]
            total_completion_tokens += result["total_completion_tokens"]
            total_api_calls += len(result["turns"])
            print(
                f"  final_action={result['final_action']} real_execute_procedure_calls={result['real_execute_procedure_calls']}"
                f" model_version={result['model_version']}"
            )
            all_rows.append({"model_id": model_id, "model_family": family, **result})

    # S1 deterministic guard-rejection sub-case (zero extra API cost)
    forced = run_scenario_s1_forced_retry_rejected("forced-retry-check-v2")
    print("FORCED_RETRY_GUARD_REJECTED_SUBCASE", forced)

    RESULTS_DIR.joinpath("llm_recovery_integration_v2.jsonl").write_text(
        "\n".join(json.dumps({k: v for k, v in row.items() if k != "transcript"} | {"transcript_saved": True}) for row in all_rows) + "\n"
    )
    for row in all_rows:
        transcript_path = TRANSCRIPTS_DIR / f"{row['scenario']}_{row['model_family']}.json"
        transcript_path.write_text(json.dumps(row["transcript"], indent=2))

    print("TOTAL_API_CALLS", total_api_calls)
    print("TOTAL_PROMPT_TOKENS", total_prompt_tokens)
    print("TOTAL_COMPLETION_TOKENS", total_completion_tokens)
    print("FORCED_SUBCASE_GUARD_REJECTED", forced["guard_rejected"])
    print("SUITE_DONE")


if __name__ != "run_llm_real_procedure_suite_v2":
    # Guard against accidental execution on plain `import` -- only run when exec'd
    # directly (bench console's exec(compile(...), globals(), globals()) leaves
    # __name__ as the console's own, typically "__main__") or invoked as a script.
    main()
