# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Duration coverage for huf.ai.agent_conversation_analytics_api.

The conversation analytics response originally summed tokens/cost across
every run but never surfaced duration, even though Agent Run.start_time/
end_time were always being fetched by the scheduled rollup for exactly this
purpose (agent_run_analytics.py's duration_ms_sum/duration_count). This file
covers the fix: _run_duration_ms's guard, _compute_totals's cumulative sum
(matching the rollup's field names), and _compute_current's per-turn
snapshot (never summed into totals, same discipline as peak_context_tokens).
"""

import sys
import os
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.agent_conversation_analytics_api import (  # noqa: E402
    _compute_current,
    _compute_totals,
    _run_duration_ms,
)


def _row(start=None, end=None, **overrides):
    row = {
        "name": "run-1",
        "sequence": 1,
        "run_kind": "agent",
        "status": "Success",
        "start_time": start,
        "end_time": end,
        "billed_input_tokens": 100,
        "input_tokens": 100,
        "output_tokens": 20,
        "cost": 0.01,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "peak_context_tokens": None,
        "model_context_window": None,
        "usage_snapshot": None,
    }
    row.update(overrides)
    return row


class TestRunDurationMs(unittest.TestCase):
    def test_none_when_start_missing(self):
        self.assertIsNone(_run_duration_ms(_row(start=None, end=datetime(2026, 1, 1, 0, 0, 5))))

    def test_none_when_end_missing(self):
        self.assertIsNone(_run_duration_ms(_row(start=datetime(2026, 1, 1, 0, 0, 0), end=None)))

    def test_computes_milliseconds_when_both_present(self):
        start = datetime(2026, 1, 1, 0, 0, 0)
        end = start + timedelta(seconds=2, milliseconds=500)
        self.assertAlmostEqual(_run_duration_ms(_row(start=start, end=end)), 2500.0)

    def test_negative_duration_treated_as_unmeasured(self):
        start = datetime(2026, 1, 1, 0, 0, 5)
        end = datetime(2026, 1, 1, 0, 0, 0)  # end before start -- clock skew / bad data
        self.assertIsNone(_run_duration_ms(_row(start=start, end=end)))


class TestComputeTotalsDuration(unittest.TestCase):
    def test_sums_only_measured_runs(self):
        start = datetime(2026, 1, 1, 0, 0, 0)
        rows = [
            _row(start=start, end=start + timedelta(seconds=1)),  # 1000ms
            _row(start=start, end=start + timedelta(seconds=3)),  # 3000ms
            _row(start=None, end=None),  # unmeasured -- must not count
        ]
        totals, _ = _compute_totals(rows)
        self.assertEqual(totals["duration_ms_sum"], 4000.0)
        self.assertEqual(totals["duration_count"], 2)

    def test_zero_when_nothing_measured(self):
        totals, _ = _compute_totals([_row(start=None, end=None)])
        self.assertEqual(totals["duration_ms_sum"], 0)
        self.assertEqual(totals["duration_count"], 0)

    def test_empty_conversation(self):
        totals, _ = _compute_totals([])
        self.assertEqual(totals["duration_ms_sum"], 0)
        self.assertEqual(totals["duration_count"], 0)


class TestComputeCurrentDuration(unittest.TestCase):
    def test_latest_run_duration_is_its_own_not_a_sum(self):
        start = datetime(2026, 1, 1, 0, 0, 0)
        latest_row = _row(start=start, end=start + timedelta(seconds=4, milliseconds=200))
        current = _compute_current(latest_row)
        self.assertAlmostEqual(current["duration_ms"], 4200.0)

    def test_none_when_latest_run_unmeasured(self):
        current = _compute_current(_row(start=None, end=None))
        self.assertIsNone(current["duration_ms"])

    def test_none_when_no_runs(self):
        self.assertIsNone(_compute_current(None))


if __name__ == "__main__":
    unittest.main()
