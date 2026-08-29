# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Regression test for a real bug found live-testing /analytics with actual
rollup data: series/breakdowns rows never had success_rate/average_duration_ms/
cache_ratio at all (not null -- entirely absent, since those three keys were
only ever added to the top-level `summary` dict, after the per-bucket and
per-dimension dicts had already been seeded from summary's keys). The
frontend's `=== null` guards don't catch `undefined`, so the first real
breakdown row crashed the whole page with "Cannot read properties of
undefined (reading 'toFixed')".

_add_derived_rates is the extracted fix: called on summary AND on every
series bucket AND every breakdown row, so all three always end up as
`number | null`, matching what ExecutionAnalyticsSummary (shared by all
three shapes on the frontend) declares.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.agent_run_analytics_api import _add_derived_rates  # noqa: E402


def _row(**overrides):
    row = {
        "run_count": 0,
        "success_count": 0,
        "input_tokens": 0,
        "cached_tokens": 0,
        "duration_ms_sum": 0,
        "duration_count": 0,
    }
    row.update(overrides)
    return row


class TestAddDerivedRates(unittest.TestCase):
    def test_keys_always_present_even_with_zero_denominators(self):
        row = _row()
        _add_derived_rates(row)
        # Never absent (undefined) -- always a real key, value None or a number.
        self.assertIn("success_rate", row)
        self.assertIn("average_duration_ms", row)
        self.assertIn("cache_ratio", row)
        self.assertIsNone(row["success_rate"])
        self.assertIsNone(row["average_duration_ms"])
        self.assertIsNone(row["cache_ratio"])

    def test_computes_real_ratios(self):
        row = _row(run_count=4, success_count=3, input_tokens=1000, cached_tokens=250,
                    duration_ms_sum=6000, duration_count=4)
        _add_derived_rates(row)
        self.assertAlmostEqual(row["success_rate"], 75.0)
        self.assertAlmostEqual(row["average_duration_ms"], 1500.0)
        self.assertAlmostEqual(row["cache_ratio"], 25.0)

    def test_matches_summary_shape_on_a_breakdown_style_dict(self):
        # Simulates what breakdown_by_dimension.setdefault(...) produces:
        # only the base numeric keys, no derived keys yet, plus one extra
        # "dimension" key that isn't part of the ratio computation at all.
        breakdown_row = {"dimension": "google", **_row(run_count=2, success_count=2,
                                                         input_tokens=500, cached_tokens=100,
                                                         duration_ms_sum=3000, duration_count=2)}
        _add_derived_rates(breakdown_row)
        self.assertEqual(breakdown_row["dimension"], "google")
        self.assertAlmostEqual(breakdown_row["success_rate"], 100.0)
        self.assertAlmostEqual(breakdown_row["average_duration_ms"], 1500.0)
        self.assertAlmostEqual(breakdown_row["cache_ratio"], 20.0)


if __name__ == "__main__":
    unittest.main()
