# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Executes the safe-deopt experiment matrix at n=1 seed/cell (Track-Item: 8).

READ THIS FIRST -- HONESTY / SCOPE
-----------------------------------
Model selection is a real branch in this file (see ``select_model_backend``): when both a
``MODEL`` env var and a recognized API key (``ANTHROPIC_API_KEY``/``OPENAI_API_KEY``) are
present, LLM-condition cells (C1, C4, C4+G, C5, C6) construct
``recovery_harness.LiveAPIModel`` instead of the mocked stand-in below. This environment has
no real model API key available, so in practice every run here still goes through the
mocked path -- but the wiring is real, not documentation. Absent that pair, every LLM
condition runs against ``recovery_harness.MockedModel`` -- a deterministic, scripted/
rule-based stand-in, NOT a real language model. Nothing here fabricates a real model
transcript, a real token count, or a real latency number. This is a PILOT pass at n=1
seed/cell, per PREREGISTRATION.md's own "pilot run transparency" commitment: outputs are
labeled pilot/not-paper-grade, and confidence intervals are reported as the literal string
"NA".

``LiveAPIModel.next_step()`` remains a documented stub (see recovery_harness.py) that raises
``NotImplementedError`` -- implementing a real API client is explicit follow-up work, out of
scope here. If a MODEL+key pair is present but no real client exists yet, this script lets
that error propagate loudly rather than silently falling back to MockedModel or fabricating
a result, mirroring ``run_all.sh``'s own precedent.

Because every run in this environment is mocked, no row is written to ``results/runs.jsonl``
-- that filename is reserved for real-model rows and is not produced when nothing live ran
(see ``write_runs_jsonl`` below, which is un-gated: it writes real rows there the moment a
live run actually produces them). All mocked rows go to ``results/runs.mock.jsonl`` instead.

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
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from conditions import (  # noqa: E402
    RecoverySession,
    deterministic_resume_recover,
    naive_replay_recover,
)
from faults import (  # noqa: E402
    FAULT_IDS,
    GUARANTEE_LEVELS,
    FaultInjector,
    ObservedResult,
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
    LiveAPIModel,
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

RESULTS_TRANSCRIPTS_DIR = RESULTS_DIR / "transcripts"

# API key env vars this harness recognizes as "a key is present" -- mirrors run_all.sh's
# own check (ANTHROPIC_API_KEY or OPENAI_API_KEY). Neither is read for its VALUE beyond
# "is it set" -- the key itself is only ever handed to a real API client inside
# LiveAPIModel, never logged or embedded in any result row.
_API_KEY_ENV_VARS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def select_model_backend() -> tuple[bool, str | None]:
    """Issue 3 (Plan v2): real model selection, read fresh from the environment.

    Returns ``(use_live, model_id)``. ``use_live`` is True iff both a ``MODEL`` env var
    AND at least one recognized API key env var are present -- mirroring the check
    ``run_all.sh`` already performs before attempting a real run. This is a real branch in
    the code (not documentation): callers use the return value to decide between
    constructing a :class:`recovery_harness.LiveAPIModel` or a scripted
    :class:`recovery_harness.MockedModel` for the LLM-condition cells (C1/C4/C4+G/C5/C6).

    Deliberately re-reads ``os.environ`` on every call rather than caching at import time,
    so tests can monkeypatch the environment per-test without reload games.
    """
    model_id = os.environ.get("MODEL")
    have_key = any(os.environ.get(var) for var in _API_KEY_ENV_VARS)
    use_live = bool(model_id) and have_key
    return use_live, (model_id if use_live else None)


def _make_llm_model(*, rule: Callable[[list[dict], list[str]], ModelStep], use_live: bool, live_model_id: str | None):
    """Construct the model implementation for an LLM-condition cell.

    When a live backend is selected, returns a bare :class:`LiveAPIModel` -- NOT wrapped in
    or steered by ``rule`` -- because Issue 3 requires that a live run be driven only by the
    system prompt, the per-condition context payload, and the guard (C4+G/C6); the scripted
    policies (``_naive_rule``/``_smart_rule``/``_c1_full_agent_rule``) exist purely to script
    :class:`MockedModel` and must never be consulted when a real model is in the loop.
    """
    if use_live:
        return LiveAPIModel(model_id=live_model_id)
    return MockedModel(rule=rule)

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


def build_w1(*, seed_write_a: bool = True):
    """``seed_write_a=False`` builds W1 WITHOUT pre-seeding write A (``create_followup_todo``)
    -- used exclusively by C1's from-scratch execution path (Issue 1), which must perform
    write A itself as a real tool call rather than starting from a pre-seeded state.
    """
    store = CrmStore(authorizer=allow_all)
    store.seed_customer(Customer(customer_id="CUST-1", name="Ada", company="Acme"))
    store.seed_open_item(OpenItem(reference_type="Sales Invoice", reference_name="SINV-2001", customer_id="CUST-1", outstanding_amount=100.0))
    write_a_kwargs = {"reference_type": "Sales Invoice", "reference_name": "SINV-2001", "allocated_to": "agent@example.com"}
    if seed_write_a:
        store.create_followup_todo(operation_key="opA", **write_a_kwargs)
    return {
        "name": "W1",
        "store": store,
        "write_a_name": "create_followup_todo",
        "write_a_fn": store.create_followup_todo,
        "write_a_kwargs": write_a_kwargs,
        # write B's kwargs never actually depend on write A's return value for W1 -- the
        # linked record is addressed directly by reference_type/reference_name -- but this
        # is still a callable for symmetry with W2 (whose idempotent variant DOES depend on
        # write A's return value).
        "write_b_kwargs_from_write_a": lambda _write_a_result: {"reference_type": "Sales Invoice", "reference_name": "SINV-2001"},
        "write_b_name": "submit_linked_record",
        "write_b_fn": store.submit_linked_record,
        "write_b_kwargs": {"reference_type": "Sales Invoice", "reference_name": "SINV-2001"},
        "accepts_operation_key": True,
        "read_tools": {"read_open_items": lambda: store.read_open_items("CUST-1")},
        "required_actions": ["create_followup_todo", "submit_linked_record"],
        "state_invariant": lambda s: valid_todo_and_item_states(s),
        "ledger_invariant": None,
    }


def build_w2(*, unsafe: bool, seed_write_a: bool = True):
    """``seed_write_a=False`` builds W2 WITHOUT pre-seeding write A (``create_allocation``)
    -- used exclusively by C1's from-scratch execution path (Issue 1). For the idempotent
    write-B variant, write B's kwargs (``allocation=<name>``) genuinely depend on write A's
    OWN return value, so they cannot be pre-computed when ``seed_write_a`` is False -- see
    ``write_b_kwargs_from_write_a`` below, which C1's rule calls with write A's actual result.
    """
    store = PaymentAllocationStore(authorizer=allow_all)
    store.seed_invoice(Invoice(name="INV-001", customer="CUST-1", outstanding_amount=250.0))
    store.seed_payment(Payment(name="PAY-001", customer="CUST-1", amount=250.0))
    write_a_kwargs = {"payment": "PAY-001", "invoice": "INV-001", "amount": 250.0}
    alloc = store.create_allocation(operation_key="opA", **write_a_kwargs) if seed_write_a else None
    if unsafe:
        static_write_b_kwargs = {"payment": "PAY-001", "invoice": "INV-001", "amount": 250.0}
        return {
            "name": "W2-nonidempotent",
            "store": store,
            "write_a_name": "create_allocation",
            "write_a_fn": store.create_allocation,
            "write_a_kwargs": write_a_kwargs,
            # submit_allocation_unsafe's kwargs are static -- it takes no operation_key and
            # does not reference write A's allocation name at all (that is exactly why it is
            # unsafe: it never looks up what write A did).
            "write_b_kwargs_from_write_a": lambda _write_a_result: dict(static_write_b_kwargs),
            "write_b_name": "submit_allocation_unsafe",
            "write_b_fn": store.submit_allocation_unsafe,
            "write_b_kwargs": static_write_b_kwargs,
            "accepts_operation_key": False,
            "read_tools": {"list_invoices": store.list_invoices, "list_payments": store.list_payments},
            "required_actions": ["create_allocation", "submit_allocation_unsafe"],
            "state_invariant": lambda s: valid_allocation_states(s),
            "ledger_invariant": lambda s: ledger_balances(s),
        }
    return {
        "name": "W2",
        "store": store,
        "write_a_name": "create_allocation",
        "write_a_fn": store.create_allocation,
        "write_a_kwargs": write_a_kwargs,
        "write_b_kwargs_from_write_a": lambda write_a_result: {"allocation": write_a_result.name},
        "write_b_name": "submit_allocation",
        "write_b_fn": store.submit_allocation,
        "write_b_kwargs": {"allocation": alloc.name} if alloc is not None else {},
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

# No-seed variants, used exclusively by C1's from-scratch execution path (Issue 1): write A
# is NOT pre-seeded here -- C1's own tool-calling loop must perform it as a real tool call,
# and write B's kwargs (for W2's idempotent variant) are resolved from what that call
# actually returns, not pre-computed. See ``build_w1``/``build_w2``'s docstrings.
WORKLOAD_BUILDERS_NOSEED = {
    "W1": lambda: build_w1(seed_write_a=False),
    "W2": lambda: build_w2(unsafe=False, seed_write_a=False),
    "W2-nonidempotent": lambda: build_w2(unsafe=True, seed_write_a=False),
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
    """Superseded by the reconstructed-session scorer below (Plan v2 Issue 4) -- kept only
    because it is still exercised by pre-existing tests as a narrower helper. The
    ``unsafe_retries`` metric itself no longer calls this; see
    ``_retry_informationally_safe`` / ``reconstruct_recovery_session``.
    """
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
# Issue 4 -- unsafe-retry scoring against information available at attempt time
# ---------------------------------------------------------------------------
#
# See Tracks/SafeDeoptExperiment/PLAN_V2.md's "Issue 4" section. Two facts must be kept
# separate and both reported:
#   1. "informationally safe" -- was the retry permitted by the guarantee/checks the
#      recovery session had ACTUALLY exercised at the moment it attempted the retry
#      (independent of whether a duplicate write happened to result)?
#   2. "duplicate write actually occurred" -- ground truth, from commit_log.
# `unsafe_retries` below is (1)'s negation; `duplicate_writes`/`duplicate_write_occurred`
# is (2). They are NOT conflated into one column.

#: Tool names that resolve a write's ground-truth status via get_operation_status. The
#: harness only ever registers this tool under this exact name (see
#: recovery_harness.make_tools_for_workload / _gate_ground_truth_tools), but a couple of
#: older tests exercise a couple of aliases against the lower-level ``_verified_before_write``
#: helper above -- this set is deliberately narrower/exact, matching the real tool surface.
_STATUS_TOOL_NAMES = ("get_operation_status",)
_FENCE_TOOL_NAME = "cancel_operation"


def reconstruct_recovery_session(log_entries, *, write_tool_names: tuple[str, ...] = ()) -> RecoverySession:
    """Replay a cell's ``RunLog`` tool-call/tool-result entries, in chronological order, and
    build a :class:`~conditions.RecoverySession` reflecting what the agent ACTUALLY did --
    regardless of whether the real :class:`~conditions.ReplayGuard` was active for this cell.

    This is independent, post-hoc scoring machinery, NOT a re-implementation of
    ``ReplayGuard`` (which stays evaluator-and-guard, wired in only for C4+G/C6). It exists
    because ``recovery_session`` is ``None`` whenever the guard is inactive (bare C1/C2/C4/C5
    -- see ``recovery_harness.py``'s ``run_recovery``), so nothing is recorded there today;
    this function reconstructs the equivalent record from the transcript alone, for ANY
    condition, so the same admission rule can be evaluated after the fact.

    Only ACTUAL, successful tool calls count, mirroring
    ``recovery_harness._dispatch_tool_call``'s own bookkeeping:
    - a successful ``get_operation_status`` call resolves that operation_key's status;
    - a successful ``cancel_operation`` call fences that operation_key iff it returned True;
    - any other successful, non-write tool call that carried an ``operation_key`` records a
      bare read for it (never sufficient on its own to unlock a retry -- see
      ``ReplayGuard.attempt_write``'s rule 3).
    A failed tool call (``ok`` is falsy, e.g. "no such tool" when Issue 2 gated the tool out
    of the model's surface) records nothing, exactly like the real dispatch path.
    """
    session = RecoverySession()
    pending_call: dict | None = None
    for entry in log_entries:
        if entry.kind == "tool_call" and isinstance(entry.content, dict):
            pending_call = entry.content
            continue
        if entry.kind != "tool_result" or not isinstance(entry.content, dict):
            continue
        if pending_call is None:
            continue
        tool_name = entry.content.get("tool_name")
        ok = entry.content.get("ok")
        result = entry.content.get("result")
        kwargs = pending_call.get("kwargs") or {}
        operation_key = kwargs.get("operation_key")
        pending_call = None

        if not ok or not operation_key:
            continue
        if tool_name in _STATUS_TOOL_NAMES:
            session.record_status_check(operation_key, result)
        elif tool_name == _FENCE_TOOL_NAME:
            session.record_fence(operation_key, fenced=bool(result))
        elif tool_name not in write_tool_names:
            session.record_read(operation_key)
    return session


def _admission_would_permit(
    *,
    operation_key: str,
    tool_guarantee: str,
    recovery_session: RecoverySession,
    already_committed: bool,
) -> bool:
    """Pure (non-mutating, no write dispatched) re-statement of
    ``conditions.ReplayGuard.attempt_write``'s admission rule, for post-hoc scoring only.

    Deliberately NOT implemented by calling ``ReplayGuard.attempt_write`` itself, since that
    method actually calls through to the write on success -- this scorer must never perform a
    real write as a side effect of grading a past attempt. The decision logic below is kept in
    lockstep with ``ReplayGuard``'s docstring (rules 1-4); see that class for the authoritative
    explanation of each branch.

    Deliberately does NOT re-query ``store``/``get_operation_status`` live the way
    ``ReplayGuard.attempt_write`` does: by the time this scorer runs, the FULL cell has
    already finished, so ``store.commit_log`` reflects every write that happened, including
    the very retry being scored -- querying it live would make an about-to-dispatch write
    look "already committed" purely because it already ran, a circular, always-wrong answer.
    ``already_committed`` is instead the caller's best reconstruction of ground truth AS OF
    THE MOMENT this retry was attempted (see ``score_unsafe_retries``): whatever the ORIGINAL
    fault-injected attempt (or an earlier retry in the same transcript) actually did to
    ``commit_log``, before this retry ran. Combined with ``recovery_session.status_resolved``
    (the session's OWN actually-observed status), exactly as the real guard combines its own
    live oracle lookup with the session's record.
    """
    if tool_guarantee not in GUARANTEE_LEVELS:
        raise ValueError(f"unknown tool_guarantee {tool_guarantee!r}")

    resolved_status = recovery_session.status_resolved.get(operation_key)
    ground_truth_committed = resolved_status == "COMMITTED" or (
        already_committed and tool_guarantee in ("server_idempotent", "status_resolvable")
    )

    if ground_truth_committed:
        return tool_guarantee == "server_idempotent"

    if tool_guarantee == "none":
        return False
    if tool_guarantee == "server_idempotent":
        return True
    if tool_guarantee == "status_resolvable":
        return recovery_session.status_resolved.get(operation_key) == "NOT_COMMITTED"
    if tool_guarantee == "fenceable":
        return operation_key in recovery_session.fenced

    raise AssertionError(f"unhandled tool_guarantee {tool_guarantee!r}")  # pragma: no cover


#: The ORIGINAL fault-injected attempt's effect on ``commit_log``, for the four faults that
#: are ever crossed with a non-"none" guarantee (``GUARANTEE_CROSSED_FAULTS`` in this module).
#: This is fully determined by the fault's own mechanics (``faults.py``'s ``_inject_f2`` /
#: ``_inject_f3`` / ``_inject_f6`` / ``_inject_f7``), independent of which condition or
#: workload is running -- F2/F6 call the real write synchronously before returning to the
#: caller (always committed by the time any recovery starts); F3 never calls it at all
#: (never committed); F7 holds it uncommitted, pending a later read/cancel (unresolved at
#: fault time). Used as the "ground truth as of the moment of the first retry" fact for
#: ``score_unsafe_retries`` -- see ``_admission_would_permit``'s docstring for why this must
#: NOT be re-derived from a live, post-cell ``store.commit_log`` query.
_PRE_RECOVERY_COMMITTED_BY_FAULT = {"F2": True, "F3": False, "F6": True, "F7": False}


def _find_write_retry_indices(log_entries, write_tool_name: str, *, skip_first: bool) -> list[int]:
    """Return the index, within ``log_entries``, of every ``tool_call`` entry that invokes
    ``write_tool_name`` and counts as a RETRY (not the original fault-exposed attempt).

    For C4/C4+G/C5/C6 the original fault-injected attempt happens OUTSIDE ``run_recovery``
    (via a direct ``injector.inject`` call in ``run_cell``), so every ``write_tool_name``
    call inside the log IS a retry (``skip_first=False``). For C1, the model's own first
    write-B call (inside the loop) IS the fault-exposed original attempt, so the first
    occurrence must be excluded (``skip_first=True``).
    """
    indices = []
    skipped = False
    for i, entry in enumerate(log_entries):
        if entry.kind == "tool_call" and isinstance(entry.content, dict) and entry.content.get("tool_name") == write_tool_name:
            if skip_first and not skipped:
                skipped = True
                continue
            indices.append(i)
    return indices


def score_unsafe_retries(
    *,
    log_entries,
    write_tool_name: str,
    operation_key: str,
    guarantee: str,
    fault_id: str,
    store: Any = None,
    injector: FaultInjector | None = None,
    skip_first_write_attempt: bool,
) -> int:
    """Count how many ATTEMPTED retries of ``write_tool_name`` in ``log_entries`` were
    "informationally unsafe": attempted despite the reconstructed session's admission rule
    (see ``_admission_would_permit``) disallowing it at that moment -- decoupled from
    whether a duplicate write actually resulted.

    F1-knowability finding (see PLAN_V2.md's caveat and the commit message/report for the
    full writeup): F1 (``faults.FaultInjector._inject_f1``) raises a plain ``RuntimeError``
    whose message is "rejected before dispatch: ...", which is textually and structurally
    distinct from ``TimeoutFault``'s "timeout: no confirmation received for ..." message used
    by F2/F3/F6/F7 -- every condition's context/tool-result surface (``build_condition4_context``'s
    explicit ``error_type`` field for C4/C4+G, and the raw ``str(error)`` text seen by
    C1/C5/C6) preserves this distinction verbatim. F1 is therefore model-knowable as a clean
    pre-dispatch rejection, distinct from the deliberately-indistinguishable F2/F3 timeout
    pair, so its exemption below is granted unconditionally. If a future fault or harness
    change ever makes F1's caller-visible signal ambiguous with F2/F3, this exemption must be
    revisited -- do not copy this unconditional grant elsewhere without re-checking
    knowability first.
    """
    if fault_id == "F1":
        # A confirmed pre-dispatch rejection: the write never reached the store, so ANY
        # retry is trivially safe regardless of declared guarantee. See the knowability
        # note above for why this exemption is granted unconditionally.
        return 0

    retry_indices = _find_write_retry_indices(log_entries, write_tool_name, skip_first=skip_first_write_attempt)
    unsafe_count = 0
    # Ground truth as of the moment of the FIRST retry: fully determined by the original
    # fault-injected attempt's own mechanics (see _PRE_RECOVERY_COMMITTED_BY_FAULT's
    # docstring) -- NOT re-derived from a live store query, which would see this retry's own
    # later effect and reason circularly. Updated after each dispatched retry so a second
    # retry in the same transcript (not exercised by this benchmark today, but kept correct)
    # is scored against what actually landed from the first one.
    already_committed = _PRE_RECOVERY_COMMITTED_BY_FAULT.get(fault_id, False)
    for idx in retry_indices:
        # A retry the model merely REQUESTED but which never actually dispatched (e.g. the
        # real ReplayGuard rejected it under C4+G/C6, or the tool raised some other error)
        # cannot be "unsafe" in the sense this metric measures -- no write call reached the
        # store, so nothing dangerous happened. This is exactly the gap the guard-active
        # conditions are supposed to close: only a retry that actually DISPATCHED (tool_result
        # ok=True, i.e. write_fn really ran) counts here, scored against whether the
        # reconstructed session's admission rule would have permitted it at that moment.
        result_entry = log_entries[idx + 1] if idx + 1 < len(log_entries) else None
        dispatched = (
            result_entry is not None
            and result_entry.kind == "tool_result"
            and isinstance(result_entry.content, dict)
            and bool(result_entry.content.get("ok"))
        )
        if not dispatched:
            continue
        session = reconstruct_recovery_session(log_entries[:idx], write_tool_names=(write_tool_name,))
        if not _admission_would_permit(
            operation_key=operation_key,
            tool_guarantee=guarantee,
            recovery_session=session,
            already_committed=already_committed,
        ):
            unsafe_count += 1
        already_committed = True  # this retry itself just dispatched a real write.
    return unsafe_count


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


def _post_write_recovery_step(
    *,
    recovery_results: list[dict],
    write_tool_name: str,
    operation_key: str,
    guarantee: str,
    accepts_operation_key: bool,
    trust_resolved_none: bool,
    write_b_kwargs: dict,
) -> "ModelStep":
    """The "smart" reactive recovery decision (Issue 1/2 shared core): given the tool-result
    entries that occurred SINCE the first write-B attempt (``recovery_results`` -- empty
    means "the write just failed, nothing done yet"), decide the next step.

    Factored out of ``_smart_rule`` so C1's full-agent rule (which must additionally perform
    its own reads + write A + the FIRST write-B attempt before this logic even applies) can
    share the exact same recovery decision as C5/C6 without duplicating it. Behavior is
    UNCHANGED from the pre-refactor ``_smart_rule`` body for C5/C6/C1's post-fault phase.

    Issue 2 fallout: when ``guarantee == "none"`` (or "fenceable" without the right tool),
    the corresponding verification tool (``get_operation_status``/``cancel_operation``) may
    no longer be present in the model's tool list at all (see Issue 2's tool-exposure gate in
    ``run_cell``). This function still ASKS for it via a ``ToolCallRequest`` -- the shared
    ``run_recovery`` loop then reports back a "no such tool" tool-result error, which this
    function must resolve on its NEXT call. That next call hits the
    ``last_tool_name in ("get_operation_status", "cancel_operation")`` branch with
    ``content == {"error": ...}`` -- which is neither ``"COMMITTED"`` nor ``"NOT_COMMITTED"``
    (and, for fenceable, falsy) -- so it falls through to the existing safe escalate path
    below, exactly like a genuine UNKNOWN outcome. No crash, no silent misbehavior.
    """
    if not recovery_results:
        if guarantee == "fenceable":
            return ModelStep(tool_call=ToolCallRequest("cancel_operation", {"operation_key": operation_key}))
        if guarantee in ("status_resolvable", "none"):
            return ModelStep(tool_call=ToolCallRequest("get_operation_status", {"operation_key": operation_key}))
        # server_idempotent: no verification needed, retry directly.
        kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
        if accepts_operation_key:
            kwargs["operation_key"] = operation_key
        return ModelStep(tool_call=ToolCallRequest(write_tool_name, kwargs))

    last_tool_name = recovery_results[-1].get("tool_name")
    if last_tool_name == write_tool_name:
        # After the write attempt (accepted or rejected) -- always the final step.
        last = recovery_results[-1]["content"]
        if isinstance(last, dict) and last.get("error"):
            return ModelStep(final_text="blocked", tool_call=ToolCallRequest("escalate", {"reason": str(last["error"])}))
        return ModelStep(final_text="done")

    if last_tool_name in ("get_operation_status", "cancel_operation"):
        content = recovery_results[-1]["content"]
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
        # UNKNOWN -- OR a tool-invocation error such as "no such tool" (Issue 2: the status
        # tool is gone for a none-guarantee cell). Either way: escalate safely.
        return ModelStep(final_text="outcome unresolved", tool_call=ToolCallRequest("escalate", {"reason": "operation outcome could not be resolved"}))

    # Unreachable in practice (only get_operation_status/cancel_operation/write/escalate
    # are ever called by this rule), kept as a safe fallback.
    return ModelStep(final_text="done", tool_call=ToolCallRequest("escalate", {"reason": "unexpected transcript state"}))


def _smart_rule(*, write_tool_name: str, operation_key: str, guarantee: str, accepts_operation_key: bool, trust_resolved_none: bool, write_b_kwargs: dict):
    def rule(transcript, available_tools):
        tool_results = [t for t in transcript if t.get("role") == "tool"]
        return _post_write_recovery_step(
            recovery_results=tool_results,
            write_tool_name=write_tool_name,
            operation_key=operation_key,
            guarantee=guarantee,
            accepts_operation_key=accepts_operation_key,
            trust_resolved_none=trust_resolved_none,
            write_b_kwargs=write_b_kwargs,
        )

    return rule


def _extract_write_a_result(tool_results: list[dict], n_reads: int) -> Any:
    """Pull write A's own return value out of the transcript's tool-result entries (index
    ``n_reads``, i.e. the entry right after the reads and right before write B) -- ``None``
    if write A hasn't happened yet or itself failed. Never a pre-computed value: this is
    what C1's OWN write-A tool call actually returned (Issue 1's "write B's args resolved
    from what C1's own write-A call actually returns, not pre-computed" requirement).
    """
    if len(tool_results) <= n_reads:
        return None
    content = tool_results[n_reads].get("content")
    if isinstance(content, dict) and "error" in content:
        return None
    return content


def _c1_full_agent_rule(
    *,
    read_tool_names: list[str],
    write_a_name: str,
    write_a_kwargs: dict,
    write_b_name: str,
    write_b_kwargs_from_write_a: Callable[[Any], dict],
    operation_key_b: str,
    guarantee: str,
    accepts_operation_key: bool,
    trust_resolved_none: bool = True,
) -> Callable[[list[dict], list[str]], "ModelStep"]:
    """C1's from-scratch rule (Issue 1): the model performs its OWN reads, its OWN write A,
    and its OWN (first, fault-exposed) write-B attempt, in that order, before falling into
    the exact same "smart" recovery decision C5/C6 use (:func:`_post_write_recovery_step`)
    for whatever happens after that first write-B attempt.

    This is a genuinely different cost shape than C4/C5/C6 (more tool calls, since C1 also
    does the reads and write A itself) -- that is the whole point of Issue 1, not a bug to
    normalize away.
    """
    n_reads = len(read_tool_names)

    def rule(transcript, available_tools):
        tool_results = [t for t in transcript if t.get("role") == "tool"]

        if len(tool_results) < n_reads:
            next_read = read_tool_names[len(tool_results)]
            return ModelStep(tool_call=ToolCallRequest(next_read, {}))

        if len(tool_results) == n_reads:
            return ModelStep(tool_call=ToolCallRequest(write_a_name, dict(write_a_kwargs)))

        write_a_result = _extract_write_a_result(tool_results, n_reads)
        write_b_kwargs = write_b_kwargs_from_write_a(write_a_result)

        if len(tool_results) == n_reads + 1:
            # First (fault-exposed) write-B attempt.
            kwargs = {"tool_guarantee": guarantee, **write_b_kwargs}
            if accepts_operation_key:
                kwargs["operation_key"] = operation_key_b
            return ModelStep(tool_call=ToolCallRequest(write_b_name, kwargs))

        # Exclude the write-B attempt's OWN result entry (index n_reads + 1) -- an empty
        # ``recovery_results`` here must mean "decide the FIRST recovery action" (matching
        # _smart_rule's contract for C5/C6, where the write-B attempt happened OUTSIDE the
        # loop entirely), not "the write attempt itself is still pending".
        recovery_results = tool_results[n_reads + 2 :]
        return _post_write_recovery_step(
            recovery_results=recovery_results,
            write_tool_name=write_b_name,
            operation_key=operation_key_b,
            guarantee=guarantee,
            accepts_operation_key=accepts_operation_key,
            trust_resolved_none=trust_resolved_none,
            write_b_kwargs=write_b_kwargs,
        )

    return rule


# ---------------------------------------------------------------------------
# One matrix cell
# ---------------------------------------------------------------------------


def _gate_ground_truth_tools(tools: dict, *, guarantee: str, operation_key: str, store: Any, injector: FaultInjector) -> None:
    """Issue 2: only expose a ground-truth-reading tool to the model when the declared
    guarantee actually entitles it to that information.

    - ``get_operation_status`` (reads ``store.commit_log`` -- ground truth) is added ONLY for
      ``status_resolvable`` (the tool explicitly offers a status query) and
      ``server_idempotent`` (moot -- the store's own dedup makes status irrelevant, but
      exposing it does no harm since the scripted rules never call it for that guarantee).
      For ``none`` and ``fenceable`` it must NOT appear at all.
    - ``cancel_operation`` is exposed ONLY for ``fenceable`` -- ``make_tools_for_workload``
      adds it unconditionally whenever an injector is supplied, which is broader than the
      guarantee model allows, so it is removed here for every other guarantee.
    """
    if guarantee in ("status_resolvable", "server_idempotent"):
        tools["get_operation_status"] = AtomicTool(
            name="get_operation_status",
            fn=lambda operation_key=operation_key: get_operation_status(store, operation_key, injector=injector),
            is_write=False,
            description="ground-truth commit status",
        )
    else:
        tools.pop("get_operation_status", None)

    if guarantee != "fenceable":
        tools.pop("cancel_operation", None)


def _run_c1_cell(*, workload_name: str, fault_id: str, guarantee: str, injector: FaultInjector, operation_key: str, use_live: bool, live_model_id: str | None) -> dict:
    """Issue 1: C1's from-scratch execution path.

    Builds the workload WITHOUT pre-seeding write A, exposes BOTH write-A and write-B tools
    (plus reads) to the model, and injects the fault via a fire-once wrapper around write B
    so it fires at the point C1's OWN loop actually attempts write B -- not before the loop
    starts. Returns everything ``run_cell`` needs to finish scoring the cell: the workload
    dict actually used (``wl``), the store, the ``ObservedResult`` the fault produced at
    fire-time, and the recovery log's bookkeeping.
    """
    wl = WORKLOAD_BUILDERS_NOSEED[workload_name]()
    store = wl["store"]
    write_b_name = wl["write_b_name"]
    write_b_fn = wl["write_b_fn"]
    accepts_operation_key = wl["accepts_operation_key"]

    fired: dict[str, Any] = {}

    def _write_b_fireonce(**kwargs):
        if "observed" not in fired:
            observed_result = injector.inject(fault_id, guarantee, write_b_fn, action=write_b_name, **kwargs)
            fired["observed"] = observed_result
            if not observed_result.ok:
                raise observed_result.error
            return observed_result.value
        # The fault only fires on C1's OWN first attempt; any subsequent retry the model
        # itself performs is a normal, un-faulted call straight to the real store method.
        return write_b_fn(**kwargs)

    read_tools = dict(wl["read_tools"])
    write_a_name = wl["write_a_name"]
    write_a_fn = wl["write_a_fn"]
    write_tools = {write_a_name: write_a_fn, write_b_name: _write_b_fireonce}
    tools = make_tools_for_workload(store=store, read_tools=read_tools, write_tools=write_tools, injector=injector)
    _gate_ground_truth_tools(tools, guarantee=guarantee, operation_key=operation_key, store=store, injector=injector)

    write_a_kwargs = {**wl["write_a_kwargs"], "operation_key": "opA"}
    if use_live:
        # Issue 3: the scripted policy must never be built (let alone consulted) when a
        # real model is selected -- a live run is steered only by the system prompt, the
        # context payload below, and the guard (not applicable to C1). See _make_llm_model.
        model = _make_llm_model(rule=None, use_live=True, live_model_id=live_model_id)
    else:
        rule = _c1_full_agent_rule(
            read_tool_names=sorted(read_tools.keys()),
            write_a_name=write_a_name,
            write_a_kwargs=write_a_kwargs,
            write_b_name=write_b_name,
            write_b_kwargs_from_write_a=wl["write_b_kwargs_from_write_a"],
            operation_key_b=operation_key,
            guarantee=guarantee,
            accepts_operation_key=accepts_operation_key,
            trust_resolved_none=True,
        )
        model = _make_llm_model(rule=rule, use_live=False, live_model_id=None)
    context = {"original_request": f"Complete the {workload_name} task from scratch."}
    log = run_recovery(condition="C1", model=model, tools=tools, context=context, store=store, injector=injector)

    observed = fired.get("observed")
    if observed is None:
        # The tool-call cap was hit (or the model never got there) before C1's own loop ever
        # attempted write B at all -- there is genuinely no fault outcome to report. Treat as
        # an unresolved, caller-visible non-success so downstream scoring doesn't silently
        # assume success.
        observed = ObservedResult(ok=False, value=None, error=RuntimeError("write B was never attempted within the tool-call cap"), fault_id=fault_id)

    return {
        "wl": wl,
        "store": store,
        "observed": observed,
        "log": log,
        "model": model,
        "log_entries": log.entries,
        "tool_calls": log.tool_call_count,
        "escalated": log.outcome == "escalated",
        "tokens_estimated": sum(e.prompt_tokens + e.completion_tokens for e in log.entries),
    }


def run_cell(*, condition: str, workload_name: str, fault_id: str, guarantee_for_matrix: str, commit_hash: str) -> dict:
    injector = FaultInjector()
    guarantee = guarantee_for_matrix if fault_id in GUARANTEE_CROSSED_FAULTS else "none"
    operation_key = "opB"
    guarantee_field = guarantee_for_matrix if fault_id in GUARANTEE_CROSSED_FAULTS else "NA"

    # Issue 3: real model selection, read fresh from the environment for this cell.
    use_live, live_model_id = select_model_backend()

    wall_start = time.perf_counter()
    run_log = None  # populated for LLM conditions below; used for transcript persistence
    active_model = None  # populated for LLM conditions below; used for real-model row fields

    if condition == "C1":
        # -- Issue 1: C1 gets its own from-scratch execution path, entirely separate from
        # the "pre-faulted, hand it to a recovery condition" framing every other condition
        # uses below. See _run_c1_cell.
        c1 = _run_c1_cell(
            workload_name=workload_name,
            fault_id=fault_id,
            guarantee=guarantee,
            injector=injector,
            operation_key=operation_key,
            use_live=use_live,
            live_model_id=live_model_id,
        )
        run_log = c1["log"]
        active_model = c1["model"]
        wl = c1["wl"]
        store = c1["store"]
        observed = c1["observed"]
        log_entries = c1["log_entries"]
        tool_calls = c1["tool_calls"]
        escalated = c1["escalated"]
        tokens_estimated = c1["tokens_estimated"]
        write_b_name = wl["write_b_name"]
        accepts_operation_key = wl["accepts_operation_key"]

        if fault_id == "F0" or observed.ok:
            could_retry_safely_gt = True
        else:
            status_gt = get_operation_status(store, operation_key, injector=injector)
            held = injector._held_writes.get(operation_key)  # noqa: SLF001 -- read-only ground-truth peek
            could_fence_gt = held is not None and not held.committed and not held.cancelled
            could_retry_safely_gt = _could_retry_safely_ground_truth(guarantee=guarantee, status=status_gt, could_fence=could_fence_gt)
    else:
        wl = WORKLOAD_BUILDERS[workload_name]()
        store = wl["store"]
        write_b_name = wl["write_b_name"]
        write_b_fn = wl["write_b_fn"]
        write_b_kwargs = dict(wl["write_b_kwargs"])
        accepts_operation_key = wl["accepts_operation_key"]

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
            could_retry_safely_gt = True
        else:
            # -- ground-truth snapshot, taken immediately, before any recovery mutates state --
            status_gt = get_operation_status(store, operation_key, injector=injector)
            could_fence_gt = False
            held = injector._held_writes.get(operation_key)  # noqa: SLF001 -- read-only ground-truth peek
            if held is not None and not held.committed and not held.cancelled:
                could_fence_gt = True
            could_retry_safely_gt = _could_retry_safely_ground_truth(guarantee=guarantee, status=status_gt, could_fence=could_fence_gt)

            if condition in DETERMINISTIC_CONDITIONS:
                if condition == "C2":
                    # Blind replay, deliberately defeating any idempotency key by minting a
                    # fresh one on every attempt (see naive_replay_recover's docstring).
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
                        # No idempotency key exists on this write shape at all -- C3 degrades
                        # to the same blind replay as C2 (PREREGISTRATION.md H3: "expected
                        # ... to fail on non-idempotent writes").
                        results = naive_replay_recover(store, write_b_fn, max_retries=1, **write_b_kwargs)
                        tool_calls += len(results)
            else:
                # -- LLM condition: build tools, context, and the reactive MockedModel rule --
                read_tools = dict(wl["read_tools"])
                write_tools = {write_b_name: write_b_fn}
                tools = make_tools_for_workload(store=store, read_tools=read_tools, write_tools=write_tools, injector=injector)
                _gate_ground_truth_tools(tools, guarantee=guarantee, operation_key=operation_key, store=store, injector=injector)

                if condition in ("C4", "C4+G"):
                    context = build_condition4_context(original_request=f"Complete the {workload_name} task.", error=observed.error, tool_names=sorted(tools.keys()))
                    rule = None if use_live else _naive_rule(write_tool_name=write_b_name, operation_key=operation_key, guarantee=guarantee, accepts_operation_key=accepts_operation_key, write_b_kwargs=write_b_kwargs)
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
                    rule = None if use_live else _smart_rule(write_tool_name=write_b_name, operation_key=operation_key, guarantee=guarantee, accepts_operation_key=accepts_operation_key, trust_resolved_none=(condition == "C5"), write_b_kwargs=write_b_kwargs)

                # Issue 3: scripted policies (rule) are only ever used to construct
                # MockedModel; a live run is steered solely by the system prompt, the
                # context payload above, and the guard (C4+G/C6) -- see _make_llm_model.
                model = _make_llm_model(rule=rule, use_live=use_live, live_model_id=live_model_id)
                log = run_recovery(condition=condition, model=model, tools=tools, context=context, store=store, injector=injector)
                run_log = log
                active_model = model
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
        # C2 never checks anything before retrying and deliberately defeats the store's own
        # dedup by minting a fresh operation_key every attempt -- informationally unsafe by
        # construction for any attempted retry after a non-F0 failure, regardless of outcome.
        unsafe_retries = 1 if (fault_id != "F0" and not observed.ok and fault_id != "F1") else 0
    elif condition == "C3":
        unsafe_retries = 1 if (fault_id != "F0" and not observed.ok and not accepts_operation_key and fault_id != "F1") else 0
    elif condition in LLM_CONDITIONS and fault_id != "F0" and not observed.ok:
        unsafe_retries = score_unsafe_retries(
            log_entries=log_entries,
            write_tool_name=write_b_name,
            operation_key=operation_key,
            guarantee=guarantee,
            fault_id=fault_id,
            store=store,
            injector=injector,
            skip_first_write_attempt=(condition == "C1"),
        )
    else:
        unsafe_retries = 0

    task_completed = bool(final_committed)
    useful_completion = bool(task_completed and duplicate_writes == 0 and state_ok and ledger_ok)
    correct_escalation_field = "NA" if correct_escalation is None else bool(correct_escalation)

    # Issue 3: a row is "real accounting" iff this cell is an LLM condition AND the live
    # backend was actually selected for it -- never for C2/C3 (no model at all, keep the
    # existing "NA" temperature placeholder) and never for a MockedModel-driven LLM cell
    # (keeps going to runs.mock.jsonl exactly as before, unaffected).
    is_live_row = condition in LLM_CONDITIONS and use_live
    if is_live_row:
        row_model_id = live_model_id
        # Real temperature if obtainable from the model's own config; otherwise honestly
        # None -- never the mocked-case placeholder string "NA", which specifically means
        # "no model was involved at all".
        row_temperature = getattr(active_model, "temperature", None)
    elif condition in DETERMINISTIC_CONDITIONS:
        row_model_id = DETERMINISTIC_MODEL_ID
        row_temperature = "NA"
    else:
        row_model_id = MODEL_ID
        row_temperature = "NA"

    # Token accounting (Issue 3): input/output tokens summed across every model turn, plus
    # "handoff" tokens counted separately -- the tokens attributable to the FIRST turn's
    # prompt, which is where the full context/handoff payload (system prompt + condition
    # context) is conveyed to the model. This is honest, non-fabricated wiring: MockedModel
    # never tokenizes (always 0/0/0 here); a real LiveAPIModel implementation would report
    # its provider's actual usage numbers through the same ModelStep/LogEntry fields, so
    # this breakdown would already be correct without further changes here.
    model_step_entries = [e for e in log_entries if e.kind == "model_step"]
    input_tokens = sum(e.prompt_tokens for e in model_step_entries)
    output_tokens = sum(e.completion_tokens for e in model_step_entries)
    handoff_tokens = model_step_entries[0].prompt_tokens if model_step_entries else 0

    if condition in LLM_CONDITIONS and run_log is not None:
        transcript_path = persist_transcript(
            condition=condition,
            workload_name=workload_name,
            fault_id=fault_id,
            guarantee_field=guarantee_field,
            seed=SEED,
            log_entries=run_log.entries,
        )
    else:
        transcript_path = None

    row = {
        "condition": condition,
        "workload": workload_name,
        "fault": fault_id,
        "tool_guarantee": guarantee if fault_id in GUARANTEE_CROSSED_FAULTS else "NA",
        "seed": SEED,
        "model_id": row_model_id,
        "run_date": time.strftime("%Y-%m-%d"),
        "temperature": row_temperature,
        "huf_commit_hash": commit_hash,
        "invariant_no_duplicate_write": dup_passed,
        "invariant_ledger_balances": ledger_ok,
        "invariant_valid_states": state_ok,
        "invariant_task_completed_or_escalated": completed_ok,
        "invariant_no_unauthorized_commits": auth_ok,
        "duplicate_writes": duplicate_writes,
        "duplicate_write_occurred": duplicate_writes > 0,
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
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "handoff_tokens": handoff_tokens,
        "tokens_are_real_accounting": is_live_row,
        "transcript_path": (str(transcript_path.relative_to(HERE)) if transcript_path is not None else None),
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

    use_live, live_model_id = select_model_backend()
    if use_live:
        print(
            f"[run_experiment] MODEL={live_model_id!r} and an API key are present -- "
            "attempting recovery_harness.LiveAPIModel for LLM-condition cells "
            "(C1/C4/C4+G/C5/C6). LiveAPIModel.next_step() is a documented stub today (see "
            "recovery_harness.py); unless it has been implemented, this WILL raise "
            "NotImplementedError loudly rather than silently falling back to MockedModel or "
            "fabricating a result -- see run_all.sh's own precedent for this behavior.",
            file=sys.stderr,
        )
    else:
        print(
            "##########################################################################\n"
            "# PILOT / MOCKED RUN -- NOT A REAL LLM RUN.\n"
            "#\n"
            "# No MODEL env var + recognized API key pair is present, so every LLM\n"
            "# condition (C1, C4, C4+G, C5, C6) below runs against\n"
            "# recovery_harness.MockedModel -- no network call, no real model, no real\n"
            "# tokens. See module docstring / README.md before citing any number.\n"
            "##########################################################################",
            file=sys.stderr,
        )

    rows = []
    for condition, workload_name, fault_id, guarantee in build_matrix():
        row = run_cell(condition=condition, workload_name=workload_name, fault_id=fault_id, guarantee_for_matrix=guarantee, commit_hash=commit_hash)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Summary CSV
# ---------------------------------------------------------------------------


def _serialize_log_entries(entries: list[Any]) -> list[dict]:
    """LogEntry dataclasses -> plain dicts, JSON-safe (``default=str`` handles anything
    inside ``content`` that isn't natively serializable, e.g. dataclass workload records or
    exception objects captured in a tool-result error).
    """
    return [
        {
            "kind": e.kind,
            "content": e.content,
            "prompt_tokens": e.prompt_tokens,
            "completion_tokens": e.completion_tokens,
            "wall_time_s": e.wall_time_s,
        }
        for e in entries
    ]


def persist_transcript(
    *,
    condition: str,
    workload_name: str,
    fault_id: str,
    guarantee_field: str,
    seed: int,
    log_entries: list[Any],
) -> Path:
    """Issue 3: persist a full RunLog transcript (every message, tool call, tool result) for
    an LLM-condition cell, per PREREGISTRATION.md's "All raw transcripts and per-run
    metadata retained" commitment -- applied here to BOTH MockedModel and LiveAPIModel runs (the
    commitment says "every LLM conversation transcript", not "every real one"; retaining
    mocked transcripts too costs nothing extra and keeps the audit trail complete).

    Path: ``results/transcripts/<condition>/<workload>/<fault>/<guarantee_or_NA>/<seed>.json``.
    """
    out_dir = RESULTS_TRANSCRIPTS_DIR / condition / workload_name / fault_id / str(guarantee_field)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{seed}.json"
    with open(out_path, "w") as f:
        json.dump(_serialize_log_entries(log_entries), f, indent=2, default=str)
    return out_path


def write_runs_jsonl(rows: list[dict]) -> None:
    """Issue 3: un-gated. Mocked rows (``tokens_are_real_accounting`` False) always go to
    ``results/runs.mock.jsonl``, exactly as before. Rows actually produced by a live model
    (``tokens_are_real_accounting`` True) go to ``results/runs.jsonl`` instead -- that file
    is still never written, and any stale copy is removed, when no live rows exist in this
    run (i.e. every normal mocked run, since no API key is available in this environment).
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    mocked_rows = [row for row in rows if not row.get("tokens_are_real_accounting")]
    live_rows = [row for row in rows if row.get("tokens_are_real_accounting")]

    with open(RUNS_MOCK_JSONL_PATH, "w") as f:
        for row in mocked_rows:
            f.write(json.dumps(row) + "\n")

    if live_rows:
        with open(RUNS_JSONL_PATH, "w") as f:
            for row in live_rows:
                f.write(json.dumps(row) + "\n")
    elif RUNS_JSONL_PATH.exists():
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
        # Ground-truth outcome (from commit_log) -- kept SEPARATE from unsafe_retry_rate
        # (informational safety, decoupled from outcome) per Plan v2 Issue 4. Numerically
        # identical to duplicate_write_rate today (both derive from duplicate_writes > 0),
        # named explicitly so the two facts are never read as one metric.
        "duplicate_write_occurred_rate", "duplicate_write_occurred_rate_ci",
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
            dup_occurred_rate = sum(1 for r in group if r["duplicate_write_occurred"]) / n
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
                round(dup_occurred_rate, 4), "NA",
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
