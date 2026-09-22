# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for `real_procedure_integration.py` -- the tool_invoker-boundary fault
adapter, tested against a hand-rolled fake `tool_invoker` and the REAL
`huf.ai.graph.procedure_runtime.execute_procedure` / `huf.ai.graph.fallback.
build_mid_run_fallback` (both importable without a live bench: they are frappe-free
modules, per their own docstrings). This is the part of Issue D that can be verified
without the `safe-deopt-verify` bench; the bench-only half is documented separately in
`benchmarks/safe-deopt/results/huf_integration_report.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faults import FaultInjector  # noqa: E402
from real_procedure_integration import (  # noqa: E402
    TOOL_READ_TARGET,
    TOOL_WRITE_A,
    TOOL_WRITE_B,
    build_two_write_procedure_graph,
    make_classifier,
    run_authority_denial_case,
    run_fault_case,
    wrap_tool_invoker_with_fault,
)

pytest.importorskip("huf.ai.graph.procedure_runtime", reason="huf package must be importable")

from huf.ai.graph.procedure_runtime import ProcedureOutcome, ToolInvocation  # noqa: E402


def _site_available() -> bool:
    """True iff a real Frappe site is initialized (frappe.cache() usable).

    A write-classified tool.call node's idempotency reservation
    (huf.ai.graph.idempotency.reserve_idempotency_key) calls frappe.cache(), which is
    None outside a bootstrapped site (frappe.init(site=...) + frappe.connect()). This
    means any test that drives execute_procedure through an actual write node
    genuinely needs a live Frappe site, not just an importable `huf` package -- the
    frappe-free/testable-without-a-bench claim in this module's docstring applies to
    the ADAPTER's own logic (graph construction, tool_id routing, ObservedResult
    translation), not to a full write-node run through execute_procedure. Tests that
    need a real run are skipped here and are instead exercised for real against the
    safe-deopt-verify bench (see benchmarks/safe-deopt/results/huf_integration_report.md).
    """

    try:
        import frappe

        return frappe.cache() is not None
    except Exception:  # noqa: BLE001 -- any failure means "no usable site here"
        return False


requires_live_site = pytest.mark.skipif(
    not _site_available(),
    reason=(
        "execute_procedure's write-node idempotency reservation calls frappe.cache(), "
        "which needs a bootstrapped Frappe site -- not available outside a live bench. "
        "See huf_integration_report.md for the real-bench run of this exact case."
    ),
)


class FakeStore:
    """A minimal, frappe-free fake standing in for real Frappe writes -- tracks calls so
    tests can assert on whether the "real write" landed, mirroring how a real
    `frappe.get_doc(...).insert()` would land in the database (or not) depending on
    whether the fault's `real_write_fn` was ever called.
    """

    def __init__(self) -> None:
        self.reads: list[dict] = []
        self.write_a_calls: list[dict] = []
        self.write_b_calls: list[dict] = []

    def real_invoker(self, tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == TOOL_READ_TARGET:
            self.reads.append(args)
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"found": True})
        if tool_id == TOOL_WRITE_A:
            self.write_a_calls.append(args)
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"created": True})
        if tool_id == TOOL_WRITE_B:
            self.write_b_calls.append(args)
            return ToolInvocation(tool_id=tool_id, args=args, success=True, result={"updated": True})
        return ToolInvocation(tool_id=tool_id, args=args, success=False, error=f"unknown tool {tool_id}")


def test_graph_shape_has_two_writes_and_declares_recovery():
    graph = build_two_write_procedure_graph(procedure_name="p1", target_identity="rec-1")
    node_by_id = {n["id"]: n for n in graph["nodes"]}
    assert node_by_id["write_a"]["config"]["recovery"] == "resume"
    assert node_by_id["write_b"]["config"]["recovery"] == "resume"
    assert "operation_key" in node_by_id["write_a"]["config"]["input"]
    assert "operation_key" in node_by_id["write_b"]["config"]["input"]
    # Distinct operation_keys per write node (D5: never shared across nodes).
    assert (
        node_by_id["write_a"]["config"]["input"]["operation_key"]
        != node_by_id["write_b"]["config"]["input"]["operation_key"]
    )


def test_f0_style_passthrough_when_tool_id_does_not_match_target():
    """A tool_id that isn't the fault's target passes straight through untouched."""
    store = FakeStore()
    injector = FaultInjector()
    wrapped = wrap_tool_invoker_with_fault(
        store.real_invoker,
        target_tool_id=TOOL_WRITE_B,
        injector=injector,
        fault_id="F1",
        guarantee_level="none",
    )
    result = wrapped(TOOL_READ_TARGET, {"target_identity": "rec-1"})
    assert result.success is True
    assert store.reads == [{"target_identity": "rec-1"}]


@requires_live_site
def test_f1_clean_rejection_never_calls_real_write():
    store = FakeStore()
    result = run_fault_case(
        procedure_name="p1",
        target_identity="rec-1",
        real_invoker=store.real_invoker,
        fault_id="F1",
    )
    assert result["outcome_status"] == ProcedureOutcome.FAILED
    assert store.write_b_calls == []  # F1: rejected before dispatch, never lands
    assert store.write_a_calls  # write A already committed before write B's fault fires
    payload = result["fallback_payload"]
    assert payload is not None
    assert "write_b" == payload["failed_step"]
    committed_node_ids = {w["node_id"] for w in payload["committed_writes"]}
    assert "write_a" in committed_node_ids


@requires_live_site
def test_f3_uncommitted_timeout_never_calls_real_write():
    store = FakeStore()
    result = run_fault_case(
        procedure_name="p1",
        target_identity="rec-2",
        real_invoker=store.real_invoker,
        fault_id="F3",
        guarantee_level="status_resolvable",
    )
    assert result["outcome_status"] == ProcedureOutcome.FAILED
    assert store.write_b_calls == []  # F3: real write never dispatched
    payload = result["fallback_payload"]
    assert payload["failed_step"] == "write_b"


@requires_live_site
def test_f5_lost_result_commits_but_caller_sees_no_evidence():
    store = FakeStore()
    result = run_fault_case(
        procedure_name="p1",
        target_identity="rec-3",
        real_invoker=store.real_invoker,
        fault_id="F5",
    )
    # F5 in faults.py surfaces ok=True with value=None -- execute_procedure's tool.call
    # handler treats a successful invocation as a succeeded node, so the run overall
    # SUCCEEDS even though the caller received no evidence of what happened.
    assert result["outcome_status"] == ProcedureOutcome.SUCCESS
    assert store.write_b_calls  # the real write DID land
    # The tool_invocation record shows success with a None result -- exactly the
    # "committed but response lost" shape the task calls for.
    write_b_invocations = [t for t in result["tool_invocations"] if t["tool_id"] == TOOL_WRITE_B]
    assert write_b_invocations[0]["success"] is True
    assert write_b_invocations[0]["result"] is None


def test_f7_late_commit_holds_real_write_until_read():
    store = FakeStore()
    injector = FaultInjector()
    wrapped = wrap_tool_invoker_with_fault(
        store.real_invoker,
        target_tool_id=TOOL_WRITE_B,
        injector=injector,
        fault_id="F7",
        guarantee_level="fenceable",
    )
    result = wrapped(TOOL_WRITE_B, {"target_identity": "rec-4", "operation_key": "op-4"})
    assert result.success is False  # caller told timeout
    assert store.write_b_calls == []  # not yet -- held

    # Triggering a read for that operation_key lands the held write (F7 semantics).
    injector.wrap_read("op-4", lambda: {"pre": "state"})
    assert len(store.write_b_calls) == 1  # now it landed


@requires_live_site
def test_authority_denial_through_real_tool_invoker_closure():
    """The permission check must be embedded in the tool_invoker CLOSURE, per the brief --
    this fake invoker plays the role a real `frappe.has_permission`-checking closure
    would, denying write_b for a lower-privileged acting user.
    """

    store = FakeStore()

    def low_priv_invoker(tool_id: str, args: dict) -> ToolInvocation:
        if tool_id == "write_b_privileged_status_update":
            return ToolInvocation(
                tool_id=tool_id,
                args=args,
                success=False,
                error="PermissionError: acting user lacks 'write' on this operation",
            )
        return store.real_invoker(tool_id, args)

    result = run_authority_denial_case(
        procedure_name="p1", target_identity="rec-5", real_invoker=low_priv_invoker
    )
    assert result["outcome_status"] == ProcedureOutcome.FAILED
    assert "PermissionError" in (result["outcome_error"] or "")
    assert store.write_b_calls == []  # denied before any real write for that tool
    payload = result["fallback_payload"]
    assert payload["failed_step"] == "write_b"


def test_classifier_marks_writes_correctly():
    classify = make_classifier()
    assert classify(TOOL_READ_TARGET).ptype == "read"
    assert classify(TOOL_WRITE_A).ptype == "create"
    assert classify(TOOL_WRITE_B).ptype == "write"
