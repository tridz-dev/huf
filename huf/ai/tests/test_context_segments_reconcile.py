# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for huf.ai.context_segments.reconcile_composition -- the unknown
propagation rules documented in its docstring:

  - any `None` in `segment_tokens` -> the whole comparison is `None`
  - `tool_exchange_tokens is None` -> `None` (unknown must never be summed as 0)
  - `tool_exchange_tokens == 0` -> DOES reconcile (a single-round run
    genuinely has no tool exchange -- 0 is a real measurement, not unknown)
  - falsy `provider_prompt_tokens` (0 or None) -> `None` (nothing to compare against)
  - within tolerance -> `within_tolerance` True; beyond -> False (and a warning is logged)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.context_segments import reconcile_composition  # noqa: E402


class TestReconcileCompositionUnknownPropagation(unittest.TestCase):
    def test_any_none_segment_makes_the_whole_comparison_none(self):
        segments = {"system": 10, "tools": None, "knowledge": 0, "history": 5, "message": 3}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100)
        self.assertIsNone(result)

    def test_all_segments_counted_but_tool_exchange_none_is_still_none(self):
        # Unknown tool_exchange_tokens must not be silently treated as 0 --
        # summing it as 0 would understate `counted` and report a spurious
        # divergence that is purely an artefact of the failed count.
        segments = {"system": 10, "tools": 5, "knowledge": 0, "history": 5, "message": 3}
        result = reconcile_composition(segments, tool_exchange_tokens=None, provider_prompt_tokens=100)
        self.assertIsNone(result)

    def test_tool_exchange_tokens_zero_does_reconcile(self):
        # 0 is a real measurement (a single-round run has no tool exchange
        # at all), not an unknown -- must NOT be treated the same as None.
        segments = {"system": 40, "tools": 20, "knowledge": 0, "history": 30, "message": 10}
        # sum(segments) = 100, + tool_exchange_tokens(0) = 100 == reported
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100)
        self.assertIsNotNone(result)
        self.assertEqual(result["counted"], 100)
        self.assertTrue(result["within_tolerance"])

    def test_falsy_provider_prompt_tokens_zero_returns_none(self):
        segments = {"system": 10, "tools": 5, "knowledge": 0, "history": 5, "message": 3}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=0)
        self.assertIsNone(result)

    def test_falsy_provider_prompt_tokens_none_returns_none(self):
        segments = {"system": 10, "tools": 5, "knowledge": 0, "history": 5, "message": 3}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=None)
        self.assertIsNone(result)

    def test_empty_or_non_dict_segment_tokens_returns_none(self):
        self.assertIsNone(reconcile_composition({}, tool_exchange_tokens=0, provider_prompt_tokens=100))
        self.assertIsNone(reconcile_composition(None, tool_exchange_tokens=0, provider_prompt_tokens=100))

    def test_within_tolerance_true_when_delta_is_small(self):
        # sum(segments) = 95, tool_exchange = 0 -> counted = 95, reported = 100
        # delta_ratio = 5/100 = 0.05, well within the default 0.15 tolerance
        segments = {"system": 40, "tools": 20, "knowledge": 0, "history": 25, "message": 10}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100)
        self.assertTrue(result["within_tolerance"])
        self.assertEqual(result["counted"], 95)
        self.assertEqual(result["reported"], 100)
        self.assertAlmostEqual(result["delta_ratio"], 0.05)

    def test_beyond_tolerance_false_and_warning_logged(self):
        # sum(segments) = 50, tool_exchange = 0 -> counted = 50 vs reported = 100
        # delta_ratio = 0.5, well beyond the default 0.15 tolerance
        segments = {"system": 20, "tools": 10, "knowledge": 0, "history": 15, "message": 5}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100)
        self.assertFalse(result["within_tolerance"])
        self.assertAlmostEqual(result["delta_ratio"], 0.5)

        import frappe

        self.assertTrue(frappe.logger.called or frappe.logger("huf").warning.called)

    def test_within_tolerance_boundary_is_inclusive(self):
        # delta_ratio exactly equal to tolerance (0.15) must count as within
        # tolerance -- the docstring says "delta_ratio <= tolerance".
        segments = {"system": 85}
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100, tolerance=0.15)
        self.assertEqual(result["delta_ratio"], 0.15)
        self.assertTrue(result["within_tolerance"])

    def test_custom_tolerance_is_respected(self):
        segments = {"system": 90}
        # delta_ratio = 0.10; with a tight 0.05 tolerance this should fail.
        result = reconcile_composition(segments, tool_exchange_tokens=0, provider_prompt_tokens=100, tolerance=0.05)
        self.assertFalse(result["within_tolerance"])


if __name__ == "__main__":
    unittest.main()
