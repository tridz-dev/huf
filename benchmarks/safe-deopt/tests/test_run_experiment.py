# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Unit tests for benchmarks/safe-deopt/run_experiment.py (Plan v2, Issues 1 & 2).

Pure pytest -- no frappe, no bench. Mirrors the sys.path setup used by the other test
modules in this directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_SAFE_DEOPT_DIR = _HERE.parent.parent
_TESTS_DIR = _HERE.parent
if str(_SAFE_DEOPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SAFE_DEOPT_DIR))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import run_experiment as re_mod  # noqa: E402
from test_run_experiment_cli_flags import _IsolatedResultsDirMixin  # noqa: E402

GROUND_TRUTH_STATUS_TOOL_NAMES = ("get_operation_status", "check_status", "read_operation_status")


class TestIssue2ToolExposureGatedByGuarantee(_IsolatedResultsDirMixin, unittest.TestCase):
    """Issue 2: a `none`-guarantee cell's model tool list must not contain any
    ground-truth-status-reading tool, and `cancel_operation` (fenceable-only) must not
    leak into other guarantees either.
    """

    def _tools_for_cell(self, *, condition: str, workload_name: str, fault_id: str, guarantee: str) -> set[str]:
        captured: dict = {}
        orig_run_recovery = re_mod.run_recovery

        def _spy_run_recovery(**kwargs):
            captured["tools"] = set(kwargs["tools"].keys())
            return orig_run_recovery(**kwargs)

        re_mod.run_recovery = _spy_run_recovery
        try:
            re_mod.run_cell(condition=condition, workload_name=workload_name, fault_id=fault_id, guarantee_for_matrix=guarantee, commit_hash="test")
        finally:
            re_mod.run_recovery = orig_run_recovery
        return captured.get("tools", set())

    def test_none_guarantee_cell_has_no_ground_truth_status_tool(self):
        for condition in ("C1", "C4", "C5", "C6"):
            for workload_name in ("W1", "W2", "W2-nonidempotent"):
                tools = self._tools_for_cell(condition=condition, workload_name=workload_name, fault_id="F2", guarantee="none")
                for bad_name in GROUND_TRUTH_STATUS_TOOL_NAMES:
                    self.assertNotIn(
                        bad_name, tools, f"{condition}/{workload_name}/none must not expose {bad_name!r}, got {tools!r}"
                    )
                # `none` must also not get the fenceable-only cancel_operation tool.
                self.assertNotIn("cancel_operation", tools, f"{condition}/{workload_name}/none must not expose cancel_operation")

    def test_fenceable_guarantee_cell_exposes_cancel_operation_not_status(self):
        for condition in ("C1", "C4", "C5", "C6"):
            for workload_name in ("W1", "W2", "W2-nonidempotent"):
                tools = self._tools_for_cell(condition=condition, workload_name=workload_name, fault_id="F2", guarantee="fenceable")
                self.assertIn("cancel_operation", tools, f"{condition}/{workload_name}/fenceable must expose cancel_operation")
                for bad_name in GROUND_TRUTH_STATUS_TOOL_NAMES:
                    self.assertNotIn(
                        bad_name, tools, f"{condition}/{workload_name}/fenceable must not expose {bad_name!r}"
                    )

    def test_status_resolvable_guarantee_cell_exposes_status_tool_not_cancel(self):
        for condition in ("C1", "C4", "C5", "C6"):
            for workload_name in ("W1", "W2", "W2-nonidempotent"):
                tools = self._tools_for_cell(condition=condition, workload_name=workload_name, fault_id="F2", guarantee="status_resolvable")
                self.assertIn("get_operation_status", tools)
                self.assertNotIn("cancel_operation", tools)

    def test_none_guarantee_row_still_completes_or_escalates_safely(self):
        """The fallout fix: _smart_rule (and C1's rule) call get_operation_status even when
        it no longer exists for a `none`-guarantee cell -- this must resolve to a clean
        escalate, not a crash or a hang.
        """
        for condition in ("C1", "C4", "C5", "C6"):
            row = re_mod.run_cell(condition=condition, workload_name="W2", fault_id="F2", guarantee_for_matrix="none", commit_hash="test")
            self.assertTrue(row["escalated"] or row["task_completed"], f"{condition}: expected a clean outcome, got {row}")


class TestIssue1C1FullAgentBaseline(_IsolatedResultsDirMixin, unittest.TestCase):
    """Issue 1: C1 must perform the whole task from scratch, including write A and its own
    reads, in the SAME tool-calling loop -- not start from a pre-seeded state.
    """

    def test_c1_f0_control_actually_performs_every_action_itself(self):
        for workload_name in ("W1", "W2", "W2-nonidempotent"):
            row = re_mod.run_cell(condition="C1", workload_name=workload_name, fault_id="F0", guarantee_for_matrix="none", commit_hash="test")
            # F0 is the control (no fault): C1 must still have touched more than one tool
            # call, since it performs its own reads + write A + write B, not a single
            # pre-faulted attempt.
            self.assertGreater(row["tool_calls"], 1, f"{workload_name}: C1/F0 should reflect a real multi-step run, got {row}")
            self.assertTrue(row["task_completed"], f"{workload_name}: C1/F0 should complete the task, got {row}")

    def test_c1_cost_shape_differs_from_c5_for_same_cell(self):
        row_c1 = re_mod.run_cell(condition="C1", workload_name="W2", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
        row_c5 = re_mod.run_cell(condition="C5", workload_name="W2", fault_id="F2", guarantee_for_matrix="status_resolvable", commit_hash="test")
        self.assertGreater(row_c1["tool_calls"], row_c5["tool_calls"], "C1 must reflect more tool calls than C5 (it also does the reads + write A)")


class TestComputeBreakevenStillSane(_IsolatedResultsDirMixin, unittest.TestCase):
    def test_compute_breakeven_produces_finite_numbers_after_c1_cost_shape_change(self):
        rows = re_mod.run_all(transcripts_dir=re_mod.RESULTS_TRANSCRIPTS_DIR)
        breakeven = re_mod.compute_breakeven(rows)
        self.assertGreater(breakeven["per_run_full_agent_cost_seconds"], 0)
        self.assertGreaterEqual(breakeven["discovery_cost_seconds"], 0)
        for p_pct, entry in breakeven["breakeven_by_p_percent"].items():
            self.assertIn("n_star", entry)


if __name__ == "__main__":
    unittest.main()
