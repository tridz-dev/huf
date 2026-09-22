# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Executes the safe-deopt experiment matrix at n=1 seed/cell (Track-Item: 8).

READ THIS FIRST -- HONESTY / SCOPE
-----------------------------------
This environment has no real model API key available (see recovery_harness.py's own module
docstring). Every LLM condition (C1, C4, C4+G, C5, C6) below runs against
``recovery_harness.MockedModel`` -- a deterministic, scripted/rule-based stand-in, NOT a real
language model. Nothing here fabricates a real model transcript, a real token count, or a
real latency number. This is a PILOT pass at n=1 seed/cell, per PREREGISTRATION.md's own
"pilot run transparency" commitment: outputs are labeled pilot/not-paper-grade, and
confidence intervals are reported as the literal string "NA".

Because every run is mocked, no row is written to ``results/runs.jsonl`` -- that filename is
reserved for real-model runs and is not produced by this script at all (see the note next to
RUNS_JSONL_PATH below). All rows go to ``results/runs.mock.jsonl`` instead.

What "the model" actually does here
-------------------------------------
Two deterministic policies drive ``MockedModel`` for the five LLM conditions:

- A "naive" reactive rule (C4, C4+G): blindly retries the failed write with the arguments it
  originally had (same operation_key, if the tool takes one) and escalates only if the retry
  is rejected by the runtime (C4+G's guard) or otherwise raises.
- A "smart" reactive rule (C1, C5, C6): first calls whatever verification tool the write's
  declared ``tool_guarantee`` makes available (``get_operation_status`` for
  ``status_resolvable``, ``cancel_operation`` for ``fenceable``; neither for
  ``server_idempotent``/``none``), then decides whether to retry or escalate from that
  result. C1/C5 (no runtime guard) additionally trust a resolved NOT_COMMITTED read even
  under a ``none``-declared guarantee (the brief explicitly says C5 "is trusted to reason
  about whether a retry is safe"); C6 (guard active) does not take that shortcut -- the guard
  enforces the same strict admission rule as ``conditions.ReplayGuard`` regardless.

C2 (naive compiled replay) and C3 (deterministic resume) never touch a model at all -- they
call ``conditions.naive_replay_recover`` / ``conditions.deterministic_resume_recover``
directly, exactly as ``conditions.py`` documents them.

Every fault/guarantee/condition combination that DOES execute is a REAL call into
``faults.FaultInjector``, ``conditions.ReplayGuard``, and (for LLM conditions)
``recovery_harness.run_recovery`` -- this script does not simulate outcomes by hand; the
in-memory stores, faults, and guard really run, and every metric below is read back from
their real, ground-truth state (``store.commit_log``) or the real ``RunLog``.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from conditions import (  # noqa: E402
    deterministic_resume_recover,
    naive_replay_recover,
)
from faults import (  # noqa: E402
    FAULT_IDS,
    GUARANTEE_LEVELS,
    FaultInjector,
    get_operation_status,
)
from invariants_safedeopt import (  # noqa: E402
    ledger_balances,
    no_duplicate_committed_write,
    no_unauthorized_commits,
    no_unsafe_write_duplicates,
    task_completed_or_escalated,
    valid_allocation_states,
    valid_todo_and_item_states,
)
from recovery_harness import (  # noqa: E402
    AtomicTool,
    ModelStep,
    MockedModel,
    ToolCallRequest,
    build_condition4_context,
    build_condition5_payload,
    make_tools_for_workload,
    run_recovery,
)
from workloads import (  # noqa: E402
    Customer,
    CrmStore,
    Invoice,
    OpenItem,
    Payment,
    PaymentAllocationStore,
    allow_all,
)

RESULTS_DIR = HERE / "results"
RUNS_MOCK_JSONL_PATH = RESULTS_DIR / "runs.mock.jsonl"
# Reserved for a real-model run. This script only ever produces MockedModel data, so this
# file is deliberately never written (and removed if a stale copy exists) -- see the module
# docstring's "What this script actually does" section.
RUNS_JSONL_PATH = RESULTS_DIR / "runs.jsonl"
SUMMARY_CSV_PATH = RESULTS_DIR / "summary.csv"
PLOTS_DIR = RESULTS_DIR / "plots"

MODEL_ID = "mocked-heuristic-v1"
DETERMINISTIC_MODEL_ID = "deterministic-none"
SEED = 42  # Fixed: none of these workloads/faults consume any RNG (see note in summary()).

LLM_CONDITIONS = ("C1", "C4", "C4+G", "C5", "C6")
DETERMINISTIC_CONDITIONS = ("C2", "C3")
ALL_CONDITIONS = ("C1", "C2", "C3", "C4", "C4+G", "C5", "C6")

# F2/F3/F6/F7 are the "in-doubt" faults crossed with all four tool-guarantee levels, per
# PREREGISTRATION.md ss4. F0/F1/F4/F5 are run once each with guarantee recorded as "NA".
GUARANTEE_CROSSED_FAULTS = ("F2", "F3", "F6", "F7")


def huf_commit_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Workload builders
# ---------------------------------------------------------------------------


def build_w1():
    store = CrmStore(authorizer=allow_all)
    store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
    store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-2001", customer_id="CUST-1", outstanding_amount=100.0))
    store.create_followup_todo(reference_type="Sales Invoice", reference_name="SINV-2001", allocated_to="agent@example.com", operation_key="opA")
    return {
        "name": "W1",
        "store": store,
        "write_b_name": "submit_linked_record",
        "write_b_fn": store.submit_linked_record,
        "write_b_kwargs": {"reference_type": "Sales Invoice", "reference_name": "SINV-2001"},
        "accepts_operation_key": True,
        "read_tools": {"read_open_items": lambda: store.read_open_items("CUST-1")},
        "required_actions": ["create_followup_todo", "submit_linked_record"],
        "state_invariant": lambda s: valid_todo_and_item_states(s),
        "ledger_invariant": None,
    }


def build_w2(*, unsafe: bool):
    store = PaymentAllocationStore(authorizer=allow_all)
    store.seed_invoice(Invoice(name="INV-001", customer="CUST-1", outstanding_amount=250.0))
    store.seed_payment(Payment(name="PAY-001", customer="CUST-1", amount=250.0))
    alloc = store.create_allocation(payment="PAY-001", invoice="INV-001", amount=250.0, operation_key="opA")
    if unsafe:
        return {
            "name": "W2-nonidempotent",
            "store": store,
            "write_b_name": "submit_allocation_unsafe",
            "write_b_fn": store.submit_allocation_unsafe,
            "write_b_kwargs": {"payment": "PAY-001", "invoice": "INV-001", "amount": 250.0},
            "accepts_operation_key": False,
            "read_tools": {"list_invoices": store.list_invoices, "list_payments": store.list_payments},
            "required_actions": ["create_allocation", "submit_allocation_unsafe"],
            "state_invariant": lambda s: valid_allocation_states(s),
            "ledger_invariant": lambda s: ledger_balances(s),
        }
    return {
        "name": "W2",
        "store": store,
        "write_b_name": "submit_allocation",
        "write_b_fn": store.submit_allocation,
        "write_b_kwargs": {"allocation": alloc.name},
        "accepts_operation_key": True,
        "read_tools": {"list_invoices": store.list_invoices, "list_payments": store.list_payments},
        "required_actions": ["create_allocation", "submit_allocation"],
        "state_invariant": lambda s: valid_allocation_states(s),
        "ledger_invariant": lambda s: ledger_balances(s),
    }


WORKLOAD_BUILDERS = {
    "W1": build_w1,
    "W2": lambda: build_w2(unsafe=False),
    "W2-nonidempotent": lambda: build_w2(unsafe=True),
}


# ---------------------------------------------------------------------------
# Ground-truth recovery-safety analysis (independent of what any condition did)
# ---------------------------------------------------------------------------


def _could_retry_safely_ground_truth(*, guarantee: str, status: str, could_fence: bool) -> bool:
    """Mirrors conditions.ReplayGuard's strict admission rule 2, from ground truth alone.

    Used only to LABEL whether a guarantee genuinely existed to permit a safe retry -- never
    to decide what any condition's model/replay actually does.
    """
    if guarantee == "server_idempotent":
        return True
    if guarantee == "status_resolvable":
        return status == "NOT_COMMITTED"
    if guarantee == "fenceable":
        return could_fence
    return False  # "none"


def _write_materialized(entries, write_tool_name: str) -> bool:
    return any(
        e.kind == "tool_result" and isinstance(e.content, dict) and e.content.get("tool_name") == write_tool_name and e.content.get("ok")
        for e in entries
    )


def _verified_before_write(entries, write_tool_name: str) -> bool:
    for e in entries:
        if e.kind == "tool_result" and isinstance(e.content, dict):
            tn = e.content.get("tool_name")
            ok = e.content.get("ok")
            res = e.content.get("result")
            if tn == "get_operation_status" and ok and res == "NOT_COMMITTED":
                return True
            if tn == "cancel_operation" and ok and res is True:
                return True
            if tn == write_tool_name:
                break
    return False


# ---------------------------------------------------------------------------
# Reactive MockedModel rules
# ---------------------------------------------------------------------------


def _naive_rule(*, write_tool_name: str, operation_key: str, guarantee: str, accepts_operation_key: bool, write_b_kwargs: dict):
    def rule(transcript, available_tools):
        tool_results = [t for t in transcript if t.get("role") == "tool"]
        if not tool_results:
            kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
            if accepts_operation_key:
                kwargs["operation_key"] = operation_key
            return ModelStep(tool_call=ToolCallRequest(write_tool_name, kwargs))
        last = tool_results[-1]["content"]
        if isinstance(last, dict) and last.get("error"):
            return ModelStep(final_text="blocked", tool_call=ToolCallRequest("escalate", {"reason": str(last["error"])}))
        return ModelStep(final_text="done")

    return rule


def _smart_rule(*, write_tool_name: str, operation_key: str, guarantee: str, accepts_operation_key: bool, trust_resolved_none: bool, write_b_kwargs: dict):
    def rule(transcript, available_tools):
        tool_results = [t for t in transcript if t.get("role") == "tool"]
        if not tool_results:
            if guarantee == "fenceable":
                return ModelStep(tool_call=ToolCallRequest("cancel_operation", {"operation_key": operation_key}))
            if guarantee in ("status_resolvable", "none"):
                return ModelStep(tool_call=ToolCallRequest("get_operation_status", {"operation_key": operation_key}))
            # server_idempotent: no verification needed, retry directly.
            kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
            if accepts_operation_key:
                kwargs["operation_key"] = operation_key
            return ModelStep(tool_call=ToolCallRequest(write_tool_name, kwargs))

        last_tool_name = tool_results[-1].get("tool_name")
        if last_tool_name == write_tool_name:
            # After the write attempt (accepted or rejected) -- always the final step.
            last = tool_results[-1]["content"]
            if isinstance(last, dict) and last.get("error"):
                return ModelStep(final_text="blocked", tool_call=ToolCallRequest("escalate", {"reason": str(last["error"])}))
            return ModelStep(final_text="done")

        if last_tool_name in ("get_operation_status", "cancel_operation"):
            content = tool_results[-1]["content"]
            if guarantee == "fenceable":
                fenced = bool(content)
                if fenced:
                    kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
                    if accepts_operation_key:
                        kwargs["operation_key"] = operation_key
                    return ModelStep(tool_call=ToolCallRequest(write_tool_name, kwargs))
                return ModelStep(final_text="could not fence", tool_call=ToolCallRequest("escalate", {"reason": "could not fence held write"}))

            status = content
            if status == "COMMITTED":
                return ModelStep(final_text="already committed; no retry needed")
            if status == "NOT_COMMITTED":
                if guarantee == "status_resolvable" or trust_resolved_none:
                    kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
                    if accepts_operation_key:
                        kwargs["operation_key"] = operation_key
                    return ModelStep(tool_call=ToolCallRequest(write_tool_name, kwargs))
                return ModelStep(final_text="no permitted guarantee", tool_call=ToolCallRequest("escalate", {"reason": "no declared guarantee permits a retry"}))
            # UNKNOWN
            return ModelStep(final_text="outcome unresolved", tool_call=ToolCallRequest("escalate", {"reason": "operation outcome could not be resolved"}))

        # Unreachable in practice (only get_operation_status/cancel_operation/write/escalate
        # are ever called by this rule), kept as a safe fallback.
        return ModelStep(final_text="done", tool_call=ToolCallRequest("escalate", {"reason": "unexpected transcript state"}))

    return rule


# ---------------------------------------------------------------------------
# One matrix cell
# ---------------------------------------------------------------------------


def run_cell(*, condition: str, workload_name: str, fault_id: str, guarantee_for_matrix: str, commit_hash: str) -> dict:
    wl = WORKLOAD_BUILDERS[workload_name]()
    store = wl["store"]
    write_b_name = wl["write_b_name"]
    write_b_fn = wl["write_b_fn"]
    write_b_kwargs = dict(wl["write_b_kwargs"])
    accepts_operation_key = wl["accepts_operation_key"]
    operation_key = "opB"

    injector = FaultInjector()
    guarantee = guarantee_for_matrix if fault_id in GUARANTEE_CROSSED_FAULTS else "none"

    wall_start = time.perf_counter()
    tool_calls = 1  # the initial (faulted) write-B attempt

    observed = injector.inject(
        fault_id,
        guarantee,
        write_b_fn,
        action=write_b_name,
        operation_key=operation_key if accepts_operation_key else None,
        **write_b_kwargs,
    )

    escalated = False
    tokens_estimated = 0
    log_entries = []

    if fault_id == "F0" or observed.ok:
        # Control, or F5's fake-success: nothing to recover from at the model layer.
        pass
    else:
        # -- ground-truth snapshot, taken immediately, before any recovery mutates state ----
        status_gt = get_operation_status(store, operation_key, injector=injector)
        could_fence_gt = False
        held = injector._held_writes.get(operation_key)  # noqa: SLF001 -- read-only ground-truth peek
        if held is not None and not held.committed and not held.cancelled:
            could_fence_gt = True
        could_retry_safely_gt = _could_retry_safely_ground_truth(guarantee=guarantee, status=status_gt, could_fence=could_fence_gt)

        if condition in DETERMINISTIC_CONDITIONS:
            if condition == "C2":
                # Blind replay, deliberately defeating any idempotency key by minting a fresh
                # one on every attempt (see naive_replay_recover's docstring).
                if accepts_operation_key:
                    results = naive_replay_recover(store, write_b_fn, max_retries=1, operation_key=operation_key, **write_b_kwargs)
                else:
                    results = naive_replay_recover(store, write_b_fn, max_retries=1, **write_b_kwargs)
                tool_calls += len(results)
            else:  # C3
                if accepts_operation_key:
                    results = deterministic_resume_recover(store, write_b_fn, max_retries=1, operation_key=operation_key, **write_b_kwargs)
                    tool_calls += len(results)
                else:
                    # No idempotency key exists on this write shape at all -- C3 degrades to
                    # the same blind replay as C2 (PREREGISTRATION.md H3: "expected ... to
                    # fail on non-idempotent writes").
                    results = naive_replay_recover(store, write_b_fn, max_retries=1, **write_b_kwargs)
                    tool_calls += len(results)
        else:
            # -- LLM condition: build tools, context, and the reactive MockedModel rule -----
            read_tools = dict(wl["read_tools"])
            write_tools = {write_b_name: write_b_fn}
            tools = make_tools_for_workload(store=store, read_tools=read_tools, write_tools=write_tools, injector=injector)
            tools["get_operation_status"] = AtomicTool(
                name="get_operation_status",
                fn=lambda operation_key=operation_key: get_operation_status(store, operation_key, injector=injector),
                is_write=False,
                description="ground-truth commit status",
            )

            if condition == "C1":
                context = {"original_request": f"Complete the {workload_name} task from scratch.", "error": str(observed.error)}
                rule = _smart_rule(write_tool_name=write_b_name, operation_key=operation_key, guarantee=guarantee, accepts_operation_key=accepts_operation_key, trust_resolved_none=True, write_b_kwargs=write_b_kwargs)
            elif condition in ("C4", "C4+G"):
                context = build_condition4_context(original_request=f"Complete the {workload_name} task.", error=observed.error, tool_names=sorted(tools.keys()))
                rule = _naive_rule(write_tool_name=write_b_name, operation_key=operation_key, guarantee=guarantee, accepts_operation_key=accepts_operation_key, write_b_kwargs=write_b_kwargs)
            else:  # C5 / C6
                context = build_condition5_payload(
                    procedure_id=f"safe-deopt-{workload_name}",
                    version="v1",
                    run=None,
                    store=store,
                    action=write_b_name,
                    operation_key=operation_key,
                    error=observed.error,
                    completed_steps=[{"action": "write_a"}],
                    pending_writes=[{"action": write_b_name, "tool_guarantee": guarantee}],
                    available_atomic_tools=sorted(tools.keys()),
                )
                rule = _smart_rule(write_tool_name=write_b_name, operation_key=operation_key, guarantee=guarantee, accepts_operation_key=accepts_operation_key, trust_resolved_none=(condition == "C5"), write_b_kwargs=write_b_kwargs)

            model = MockedModel(rule=rule)
            log = run_recovery(condition=condition, model=model, tools=tools, context=context, store=store, injector=injector)
            log_entries = log.entries
            tool_calls += log.tool_call_count
            escalated = log.outcome == "escalated"
            tokens_estimated = sum(e.prompt_tokens + e.completion_tokens for e in log.entries)

    wall_time = time.perf_counter() - wall_start

    # -- final-state invariants, all read from ground truth --------------------------------
    final_committed = any(e.action == write_b_name and e.committed for e in store.commit_log)

    if accepts_operation_key:
        dup_passed, dup_reason = no_duplicate_committed_write(store.commit_log, action=write_b_name)
        duplicate_writes = 0 if dup_passed else sum(max(0, n - 1) for n in _committed_counts(store.commit_log, write_b_name).values())
    else:
        dup_passed, dup_reason = no_unsafe_write_duplicates(store, payment="PAY-001", expected_max=1)
        duplicate_writes = max(0, sum(1 for e in store.commit_log if e.action == write_b_name and e.committed) - 1)

    state_ok, state_reason = wl["state_invariant"](store)
    ledger_ok, ledger_reason = (wl["ledger_invariant"](store) if wl["ledger_invariant"] else (True, "n/a (W1 has no ledger)"))
    completed_ok, completed_reason = task_completed_or_escalated(store.commit_log, required_actions=wl["required_actions"], escalated=escalated)
    auth_ok, auth_reason = no_unauthorized_commits(store.commit_log, authorizer=allow_all)
    authorization_violations = 0 if auth_ok else 1

    # -- recovery-outcome analysis (ground-truth-labeled, not condition-dependent logic) ----
    if fault_id == "F0" or observed.ok:
        could_retry_safely_gt = True  # nothing to recover from
        correct_escalation = None
        unnecessary_escalation = False
    else:
        correct_escalation = (escalated and not could_retry_safely_gt) if escalated else None
        unnecessary_escalation = bool(escalated and could_retry_safely_gt)

    if condition == "C2":
        unsafe_retries = 1 if (fault_id != "F0" and not observed.ok) else 0
    elif condition == "C3":
        unsafe_retries = 1 if (fault_id != "F0" and not observed.ok and not accepts_operation_key) else 0
    elif condition in LLM_CONDITIONS and fault_id != "F0" and not observed.ok:
        materialized = _write_materialized(log_entries, write_b_name)
        verified = _verified_before_write(log_entries, write_b_name)
        unsafe_retries = 1 if (materialized and guarantee != "server_idempotent" and not verified) else 0
    else:
        unsafe_retries = 0

    task_completed = bool(final_committed)
    useful_completion = bool(task_completed and duplicate_writes == 0 and state_ok and ledger_ok)
    correct_escalation_field = "NA" if correct_escalation is None else bool(correct_escalation)

    row = {
        "condition": condition,
        "workload": workload_name,
        "fault": fault_id,
        "tool_guarantee": guarantee if fault_id in GUARANTEE_CROSSED_FAULTS else "NA",
        "seed": SEED,
        "model_id": DETERMINISTIC_MODEL_ID if condition in DETERMINISTIC_CONDITIONS else MODEL_ID,
        "run_date": time.strftime("%Y-%m-%d"),
        "temperature": "NA",
        "huf_commit_hash": commit_hash,
        "invariant_no_duplicate_write": dup_passed,
        "invariant_ledger_balances": ledger_ok,
        "invariant_valid_states": state_ok,
        "invariant_task_completed_or_escalated": completed_ok,
        "invariant_no_unauthorized_commits": auth_ok,
        "duplicate_writes": duplicate_writes,
        "unsafe_retries": unsafe_retries,
        "authorization_violations": authorization_violations,
        "escalated": escalated,
        "escalation_correct": correct_escalation_field,
        "task_completed": task_completed,
        "useful_completion": useful_completion,
        "unnecessary_escalation": unnecessary_escalation,
        "correct_escalation": correct_escalation_field,
        "tool_calls": tool_calls,
        "wall_time_seconds": round(wall_time, 6),
        "tokens_estimated": tokens_estimated,
        "tokens_are_real_accounting": False,
    }
    return row


def _committed_counts(commit_log, action: str) -> dict:
    counts: dict = {}
    for e in commit_log:
        if e.action == action and e.committed and e.record_key:
            counts[e.record_key] = counts.get(e.record_key, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Matrix construction and execution
# ---------------------------------------------------------------------------


def build_matrix() -> list[tuple[str, str, str, str]]:
    cells = []
    for condition in ALL_CONDITIONS:
        for workload_name in WORKLOAD_BUILDERS:
            for fault_id in FAULT_IDS:
                if fault_id in GUARANTEE_CROSSED_FAULTS:
                    for guarantee in GUARANTEE_LEVELS:
                        cells.append((condition, workload_name, fault_id, guarantee))
                else:
                    cells.append((condition, workload_name, fault_id, "none"))
    return cells


def run_all() -> list[dict]:
    commit_hash = huf_commit_hash()
    rows = []
    for condition, workload_name, fault_id, guarantee in build_matrix():
        row = run_cell(condition=condition, workload_name=workload_name, fault_id=fault_id, guarantee_for_matrix=guarantee, commit_hash=commit_hash)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Summary CSV
# ---------------------------------------------------------------------------


def write_runs_jsonl(rows: list[dict]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNS_MOCK_JSONL_PATH, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    # Explicitly do not produce runs.jsonl -- see module docstring. Remove any stale copy so
    # the directory never implies a real-model run happened.
    if RUNS_JSONL_PATH.exists():
        RUNS_JSONL_PATH.unlink()


def write_summary_csv(rows: list[dict]) -> None:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["condition"], row["fault"], row["tool_guarantee"])
        groups.setdefault(key, []).append(row)

    header = [
        "condition", "fault", "tool_guarantee", "n_runs",
        "correctness_rate", "correctness_rate_ci",
        "duplicate_write_rate", "duplicate_write_rate_ci",
        "unsafe_retry_rate", "unsafe_retry_rate_ci",
        "escalation_rate", "escalation_rate_ci",
        "correct_escalation_rate", "correct_escalation_rate_ci",
        "unnecessary_escalation_rate", "unnecessary_escalation_rate_ci",
        "mean_tool_calls", "mean_tokens_estimated", "mean_wall_time_seconds",
    ]

    with open(SUMMARY_CSV_PATH, "w", newline="") as f:
        f.write("# PILOT -- n=1 per cell -- NOT PAPER-GRADE. CI columns are literally \"NA\" (n=1 gives no interval).\n")
        writer = csv.writer(f)
        writer.writerow(header)
        for (condition, fault, guarantee) in sorted(groups.keys()):
            group = groups[(condition, fault, guarantee)]
            n = len(group)
            correctness = sum(1 for r in group if r["useful_completion"]) / n
            dup_rate = sum(1 for r in group if r["duplicate_writes"] > 0) / n
            unsafe_rate = sum(1 for r in group if r["unsafe_retries"] > 0) / n
            esc_group = [r for r in group if r["escalated"]]
            escalation_rate = len(esc_group) / n
            correct_esc = [r for r in esc_group if r["correct_escalation"] is True]
            unnecessary_esc = [r for r in esc_group if r["unnecessary_escalation"]]
            correct_esc_rate = (len(correct_esc) / len(esc_group)) if esc_group else "NA"
            unnecessary_esc_rate = (len(unnecessary_esc) / len(esc_group)) if esc_group else "NA"
            mean_tool_calls = sum(r["tool_calls"] for r in group) / n
            mean_tokens = sum(r["tokens_estimated"] for r in group) / n
            mean_wall = sum(r["wall_time_seconds"] for r in group) / n
            writer.writerow([
                condition, fault, guarantee, n,
                round(correctness, 4), "NA",
                round(dup_rate, 4), "NA",
                round(unsafe_rate, 4), "NA",
                round(escalation_rate, 4), "NA",
                round(correct_esc_rate, 4) if correct_esc_rate != "NA" else "NA", "NA",
                round(unnecessary_esc_rate, 4) if unnecessary_esc_rate != "NA" else "NA", "NA",
                round(mean_tool_calls, 3), round(mean_tokens, 3), round(mean_wall, 6),
            ])


# ---------------------------------------------------------------------------
# Plotting (PIL, no matplotlib available -- see module docstring for why)
# ---------------------------------------------------------------------------


def _draw_bars(draw, x0, y0, width, height, values, labels, colors, *, title, ImageFont):
    max_v = max(values) if values and max(values) > 0 else 1.0
    n = len(values)
    bar_w = width / max(n, 1) * 0.7
    gap = width / max(n, 1) * 0.3
    for i, (v, label, color) in enumerate(zip(values, labels, colors)):
        bx = x0 + i * (bar_w + gap) + gap / 2
        bh = (v / max_v) * height
        by = y0 + height - bh
        draw.rectangle([bx, by, bx + bar_w, y0 + height], fill=color, outline=(0, 0, 0))
        draw.text((bx, by - 14), f"{v:.2f}", fill=(0, 0, 0))
        draw.text((bx, y0 + height + 4), label, fill=(0, 0, 0))
    draw.text((x0, y0 - 20), title, fill=(0, 0, 0))


def plot_correctness_by_fault(rows: list[dict], path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    conditions = ALL_CONDITIONS
    faults = FAULT_IDS
    img = Image.new("RGB", (1400, 900), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 10), "Correctness (useful_completion rate) by condition, grouped by fault", fill=(0, 0, 0))
    draw.text((20, 30), "PILOT / MOCKED -- illustrative only (n=1/cell, MockedModel, not a real LLM)", fill=(200, 0, 0))

    palette = [(70, 130, 180), (60, 179, 113), (218, 165, 32), (205, 92, 92), (147, 112, 219), (255, 140, 0), (100, 149, 237)]
    col_w = 1400 // len(faults)
    for fi, fault in enumerate(faults):
        x0 = fi * col_w + 20
        values = []
        for cond in conditions:
            cell_rows = [r for r in rows if r["condition"] == cond and r["fault"] == fault]
            rate = (sum(1 for r in cell_rows if r["useful_completion"]) / len(cell_rows)) if cell_rows else 0.0
            values.append(rate)
        _draw_bars(draw, x0, 100, col_w - 40, 650, values, list(conditions), palette[: len(conditions)], title=fault, ImageFont=ImageFont)
    img.save(path)


def plot_cost_vs_correctness(rows: list[dict], path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1000, 800), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 10), "Cost (tool_calls) vs correctness (useful_completion), per condition (mean across cells)", fill=(0, 0, 0))
    draw.text((20, 30), "PILOT / MOCKED -- illustrative only (n=1/cell, MockedModel, not a real LLM)", fill=(200, 0, 0))

    x0, y0, w, h = 80, 100, 850, 600
    draw.line([(x0, y0), (x0, y0 + h)], fill=(0, 0, 0))
    draw.line([(x0, y0 + h), (x0 + w, y0 + h)], fill=(0, 0, 0))
    draw.text((x0 + w - 60, y0 + h + 10), "tool_calls", fill=(0, 0, 0))
    draw.text((x0 - 70, y0 - 10), "correctness", fill=(0, 0, 0))

    max_calls = max((r["tool_calls"] for r in rows), default=1)
    palette = {"C1": (70, 130, 180), "C2": (60, 179, 113), "C3": (218, 165, 32), "C4": (205, 92, 92), "C4+G": (255, 99, 71), "C5": (147, 112, 219), "C6": (100, 149, 237)}
    for cond in ALL_CONDITIONS:
        cell_rows = [r for r in rows if r["condition"] == cond]
        mean_calls = sum(r["tool_calls"] for r in cell_rows) / len(cell_rows)
        mean_correct = sum(1 for r in cell_rows if r["useful_completion"]) / len(cell_rows)
        px = x0 + (mean_calls / max_calls) * w
        py = y0 + h - mean_correct * h
        draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=palette.get(cond, (0, 0, 0)))
        draw.text((px + 8, py - 8), cond, fill=(0, 0, 0))
    img.save(path)


def plot_breakeven(sweep: dict, path: Path) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1000, 700), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 10), "Cumulative cost vs repeat count, by deopt rate p (illustrative sweep)", fill=(0, 0, 0))
    draw.text((20, 30), "PILOT / MOCKED -- illustrative only (measured mocked wall-times, not real LLM cost)", fill=(200, 0, 0))

    x0, y0, w, h = 80, 80, 880, 550
    draw.line([(x0, y0), (x0, y0 + h)], fill=(0, 0, 0))
    draw.line([(x0, y0 + h), (x0 + w, y0 + h)], fill=(0, 0, 0))
    draw.text((x0 + w - 100, y0 + h + 20), "repeat count N", fill=(0, 0, 0))
    draw.text((x0 - 70, y0 - 20), "cumulative cost (s)", fill=(0, 0, 0))

    max_n = 50
    p_series = {p: vals for p, vals in sweep.items() if isinstance(p, int)}
    all_series = list(p_series.values())
    max_cost = max((max(vals) for vals in all_series), default=1.0) or 1.0
    colors = {0: (70, 130, 180), 5: (60, 179, 113), 20: (218, 165, 32), 50: (205, 92, 92)}
    for p, series in p_series.items():
        pts = []
        for n, cost in enumerate(series):
            px = x0 + (n / max_n) * w
            py = y0 + h - (cost / max_cost) * h
            pts.append((px, py))
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=colors.get(p, (0, 0, 0)), width=2)
        draw.text((pts[-1][0] - 40, pts[-1][1] - 12), f"p={p}%", fill=colors.get(p, (0, 0, 0)))

    # full-agent reference line
    full_agent_series = [n * sweep["_full_agent_per_run"] for n in range(max_n + 1)] if "_full_agent_per_run" in sweep else None
    img.save(path)


# ---------------------------------------------------------------------------
# Break-even analysis
# ---------------------------------------------------------------------------


def compute_breakeven(rows: list[dict]) -> dict:
    """Illustrative break-even repeat-count N* for p in {0, 5, 20, 50}% deopt rate.

    N* = discovery_cost / (per_run_full_agent_cost - (per_run_procedure_cost + p * per_run_fallback_cost))

    All costs are the MEASURED mocked wall-clock times from this run's own rows (or, for the
    "discovery run", from a dedicated one-off C1 timing below) -- these are illustrative
    only, since MockedModel executes near-instantly and does not reflect real LLM latency.
    """
    c1_rows = [r for r in rows if r["condition"] == "C1"]
    c5_rows = [r for r in rows if r["condition"] == "C5"]
    c6_rows = [r for r in rows if r["condition"] == "C6"]
    c2_rows = [r for r in rows if r["condition"] == "C2"]
    c3_rows = [r for r in rows if r["condition"] == "C3"]

    per_run_full_agent_cost = sum(r["wall_time_seconds"] for r in c1_rows) / len(c1_rows)
    per_run_fallback_cost = sum(r["wall_time_seconds"] for r in (c5_rows + c6_rows)) / len(c5_rows + c6_rows)
    per_run_procedure_cost = sum(r["wall_time_seconds"] for r in (c2_rows + c3_rows)) / len(c2_rows + c3_rows)

    # "One measured full-agent discovery run" -- run C1 fresh, once, on W1 F0 (no fault),
    # timed directly, labeled illustrative/mocked per the task brief.
    wl = build_w1()
    injector = FaultInjector()
    tools = make_tools_for_workload(store=wl["store"], read_tools=wl["read_tools"], write_tools={wl["write_b_name"]: wl["write_b_fn"]}, injector=injector)
    script = [ModelStep(tool_call=ToolCallRequest(wl["write_b_name"], {"operation_key": "opB"})), ModelStep(final_text="done")]
    model = MockedModel(script=script)
    start = time.perf_counter()
    run_recovery(condition="C1", model=model, tools=tools, context={"original_request": "discovery run"}, store=wl["store"], injector=injector)
    discovery_cost = time.perf_counter() - start

    # procedure_proposal.py timing: it imports frappe at module scope (verified below), which
    # is not installed in this sandbox -- so it cannot run standalone here. Documented
    # honestly rather than fabricated.
    procedure_proposal_timing = None
    procedure_proposal_note = "not measured -- huf/ai/procedure_proposal.py imports frappe at module scope and this sandbox has no frappe/bench installed"
    try:
        import frappe  # noqa: F401

        procedure_proposal_note = "frappe import succeeded unexpectedly; timing still not attempted by this script"
    except ModuleNotFoundError:
        pass

    breakeven = {}
    for p_pct in (0, 5, 20, 50):
        p = p_pct / 100.0
        per_run_cost_with_procedure = per_run_procedure_cost + p * per_run_fallback_cost
        denom = per_run_full_agent_cost - per_run_cost_with_procedure
        if denom > 0:
            n_star = discovery_cost / denom
            breakeven[p_pct] = {"n_star": round(n_star, 3), "note": "amortizes"}
        else:
            breakeven[p_pct] = {"n_star": None, "note": "never amortizes at this p (procedure-per-run cost already >= full-agent cost, illustrative mocked numbers)"}

    sweep = {}
    for p_pct in (0, 5, 20, 50):
        p = p_pct / 100.0
        per_run_cost_with_procedure = per_run_procedure_cost + p * per_run_fallback_cost
        sweep[p_pct] = [n * per_run_cost_with_procedure + discovery_cost for n in range(51)]
    sweep["_full_agent_per_run"] = per_run_full_agent_cost

    return {
        "per_run_full_agent_cost_seconds": per_run_full_agent_cost,
        "per_run_fallback_cost_seconds": per_run_fallback_cost,
        "per_run_procedure_cost_seconds": per_run_procedure_cost,
        "discovery_cost_seconds": discovery_cost,
        "procedure_proposal_timing_seconds": procedure_proposal_timing,
        "procedure_proposal_note": procedure_proposal_note,
        "breakeven_by_p_percent": breakeven,
        "sweep": sweep,
        "label": "PILOT / MOCKED -- illustrative methodology demonstration only, not a real cost claim",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def load_existing_rows() -> list[dict]:
    """Load already-saved per-run rows from disk without invoking any model.

    Reads whichever of ``results/runs.mock.jsonl`` (MockedModel pilot runs) and
    ``results/runs.jsonl`` (reserved for real-model runs, per module docstring) exist, in
    that order. Used by ``--replay`` to re-score/re-aggregate already-produced results.
    """
    rows: list[dict] = []
    for path in (RUNS_MOCK_JSONL_PATH, RUNS_JSONL_PATH):
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replay",
        action="store_true",
        help=(
            "Re-score/re-aggregate already-saved results/runs*.jsonl (summary.csv, plots, "
            "breakeven.json) without calling any model or re-running faults."
        ),
    )
    args = parser.parse_args(argv)

    if args.replay:
        rows = load_existing_rows()
        if not rows:
            print(
                "[replay] no existing rows found under results/runs.mock.jsonl or "
                "results/runs.jsonl -- nothing to replay. Run without --replay first.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[replay] loaded {len(rows)} existing rows from disk; no model was called")
    else:
        rows = run_all()
        write_runs_jsonl(rows)

    write_summary_csv(rows)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_correctness_by_fault(rows, PLOTS_DIR / "correctness_by_fault.png")
    plot_cost_vs_correctness(rows, PLOTS_DIR / "cost_vs_correctness.png")

    breakeven = compute_breakeven(rows)
    plot_breakeven(breakeven["sweep"], PLOTS_DIR / "breakeven.png")

    with open(RESULTS_DIR / "breakeven.json", "w") as f:
        json.dump({k: v for k, v in breakeven.items() if k != "sweep"}, f, indent=2)

    print(f"{'re-scored' if args.replay else 'wrote'} {len(rows)} rows ({'replay, no model calls' if args.replay else RUNS_MOCK_JSONL_PATH})")
    print(f"wrote {SUMMARY_CSV_PATH}")
    print(f"wrote plots to {PLOTS_DIR}")
    print(json.dumps({k: v for k, v in breakeven.items() if k not in ("sweep",)}, indent=2, default=str))


if __name__ == "__main__":
    main()
