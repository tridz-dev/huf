# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for Plan v3 Issue C's new ``blocked_retries`` metric: the count of retries the
real ``ReplayGuard`` actually rejected (a ``conditions.ReplayRejected`` was raised and
caught), reported as its own column distinct from ``unsafe_retries``.

Pure pytest -- no frappe, no bench. Mirrors the sys.path setup used by the other test
modules in this directory.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))

from conditions import ReplayRejected, guarantee_aware_resume_recover  # noqa: E402
from faults import FaultInjector  # noqa: E402
from recovery_harness import (  # noqa: E402
    LogEntry,
    MockedModel,
    ModelStep,
    ToolCallRequest,
    make_tools_for_workload,
    run_recovery,
)
from run_experiment import (  # noqa: E402
    build_w1,
    build_w2,
    score_blocked_retries_from_log,
    score_blocked_retries_from_results,
)


def _tool_result(tool_name: str, *, ok: bool, dispatched: bool, guard_rejected: bool = False, result=None, error=None) -> LogEntry:
    content = {"tool_name": tool_name, "ok": ok, "dispatched": dispatched, "guard_rejected": guard_rejected}
    if ok:
        content["result"] = result
    else:
        content["error"] = error
    return LogEntry(kind="tool_result", content=content)


class TestScoreBlockedRetriesFromLog(unittest.TestCase):
    """Pure scorer tests against fabricated LogEntry lists -- no harness/model involved."""

    def test_counts_only_guard_rejected_entries_for_the_write_tool(self):
        entries = [
            _tool_result("submit_allocation", ok=False, dispatched=False, guard_rejected=True, error="rejected"),
            _tool_result("get_operation_status", ok=True, dispatched=False, guard_rejected=False, result="NOT_COMMITTED"),
            _tool_result("submit_allocation", ok=True, dispatched=True, guard_rejected=False, result="ok"),
        ]
        self.assertEqual(score_blocked_retries_from_log(entries, "submit_allocation"), 1)

    def test_never_dispatched_but_not_guard_rejected_does_not_count(self):
        """A "no such tool" or "no operation_key" refusal is dispatched=False but
        guard_rejected=False -- it must NOT be counted as a blocked retry (that is exactly
        the distinction the guard-rejection metric exists to preserve).
        """
        entries = [
            _tool_result("submit_allocation", ok=False, dispatched=False, guard_rejected=False, error="no such tool 'submit_allocation'"),
        ]
        self.assertEqual(score_blocked_retries_from_log(entries, "submit_allocation"), 0)

    def test_zero_when_no_entries_for_that_tool(self):
        entries = [_tool_result("escalate", ok=True, dispatched=True, result="done")]
        self.assertEqual(score_blocked_retries_from_log(entries, "submit_allocation"), 0)

    def test_counts_multiple_rejections(self):
        entries = [
            _tool_result("submit_allocation", ok=False, dispatched=False, guard_rejected=True, error="rejected 1"),
            _tool_result("submit_allocation", ok=False, dispatched=False, guard_rejected=True, error="rejected 2"),
        ]
        self.assertEqual(score_blocked_retries_from_log(entries, "submit_allocation"), 2)


class TestScoreBlockedRetriesFromResults(unittest.TestCase):
    """C3's non-idempotent path (``guarantee_aware_resume_recover``) never raises
    ``ReplayRejected`` -- it captures each rejection as a list entry. Verify the scorer
    counts those captures directly.
    """

    def test_counts_captured_rejections(self):
        results = [
            ReplayRejected(operation_key="opB", tool_guarantee="none", reason="no guarantee"),
            "not-a-rejection",
        ]
        self.assertEqual(score_blocked_retries_from_results(results), 1)

    def test_zero_when_nothing_rejected(self):
        results = ["ok-result-1", "ok-result-2"]
        self.assertEqual(score_blocked_retries_from_results(results), 0)


class TestGuardActuallyRejectsAndIsCounted(unittest.TestCase):
    """End-to-end: drive the REAL ``ReplayGuard`` (via ``run_recovery`` with a guard-active
    condition, C6) through a scripted model that deliberately attempts an unverified retry
    -- the guard must reject it, the tool-result entry must carry ``guard_rejected=True``,
    and ``score_blocked_retries_from_log`` must see exactly one blocked retry.
    """

    def test_c6_guard_rejects_unverified_retry_under_none_guarantee(self):
        wl = build_w2(unsafe=False)
        store = wl["store"]
        write_b_name = wl["write_b_name"]
        injector = FaultInjector()
        operation_key = "opB"

        tools = make_tools_for_workload(
            store=store,
            read_tools=dict(wl["read_tools"]),
            write_tools={write_b_name: wl["write_b_fn"]},
            injector=injector,
        )

        # A deliberately UNSAFE scripted model: it never checks status or fences, it just
        # immediately (re-)attempts the write under tool_guarantee="none" -- exactly the
        # attempt rule 4 of ReplayGuard.attempt_write's admission rule must reject
        # unconditionally. This simulates "a model attempted a retry the guard actually
        # blocked", which is precisely what blocked_retries must capture.
        script = [
            ModelStep(
                tool_call=ToolCallRequest(
                    write_b_name,
                    {"tool_guarantee": "none", "operation_key": operation_key, "allocation": wl["write_b_kwargs"].get("allocation", "ALLOC-1")},
                )
            ),
            ModelStep(final_text="could not safely recover", tool_call=ToolCallRequest("escalate", {"reason": "guard rejected retry"})),
        ]
        model = MockedModel(script=script)

        log = run_recovery(
            condition="C6",
            model=model,
            tools=tools,
            context={"note": "test context"},
            store=store,
            injector=injector,
        )

        blocked = score_blocked_retries_from_log(log.entries, write_b_name)
        self.assertEqual(blocked, 1, f"expected exactly one guard-rejected retry, got entries: {[e.content for e in log.entries if e.kind == 'tool_result']}")

        # And the underlying write must genuinely never have been dispatched to the store.
        rejected_entries = [
            e for e in log.entries
            if e.kind == "tool_result" and isinstance(e.content, dict) and e.content.get("tool_name") == write_b_name
        ]
        self.assertEqual(len(rejected_entries), 1)
        self.assertFalse(rejected_entries[0].content["ok"])
        self.assertFalse(rejected_entries[0].content["dispatched"])
        self.assertTrue(rejected_entries[0].content["guard_rejected"])

    def test_c3_nonidempotent_guard_aware_recover_rejects_under_none_guarantee(self):
        """C3's deterministic guarantee-aware path (Issue E) on the non-idempotent write
        shape: under tool_guarantee="none" there is nothing to mechanically exercise, so
        every attempt must come back as a captured ReplayRejected -- this is exactly the
        case ``score_blocked_retries_from_results`` must surface as blocked_retries > 0.
        """
        wl = build_w2(unsafe=True)
        store = wl["store"]
        injector = FaultInjector()

        results = guarantee_aware_resume_recover(
            store,
            wl["write_b_fn"],
            max_retries=1,
            operation_key="opB",
            tool_guarantee="none",
            injector=injector,
            accepts_operation_key=False,
            **wl["write_b_kwargs"],
        )

        self.assertTrue(all(isinstance(r, ReplayRejected) for r in results), results)
        self.assertGreaterEqual(score_blocked_retries_from_results(results), 1)


class TestFinalStateInvariantsAreSeparateColumns(unittest.TestCase):
    """Issue C also asks to confirm final-state invariant violations are surfaced as their
    OWN columns (per-invariant), not folded into a single aggregate boolean. Verify
    ``run_cell``'s row carries every individual ``invariant_*`` field independently.
    """

    def test_row_has_one_column_per_invariant_not_a_single_blended_flag(self):
        import run_experiment as re_mod

        row = re_mod.run_cell(condition="C2", workload_name="W1", fault_id="F0", guarantee_for_matrix="none", commit_hash="test")
        expected_invariant_columns = {
            "invariant_no_duplicate_write",
            "invariant_ledger_balances",
            "invariant_valid_states",
            "invariant_task_completed_or_escalated",
            "invariant_no_unauthorized_commits",
        }
        self.assertTrue(expected_invariant_columns.issubset(row.keys()), row.keys())
        for col in expected_invariant_columns:
            self.assertIn(row[col], (True, False), f"{col} must be an individually-readable boolean, got {row[col]!r}")


if __name__ == "__main__":
    unittest.main()
