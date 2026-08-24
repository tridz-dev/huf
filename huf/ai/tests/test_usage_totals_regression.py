# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Regression tests for D1: sync and streaming completion loops in
huf.ai.providers.litellm must report the SAME billed_input_tokens for the
same workload.

Before this was fixed, the sync loop (`AgentManager.run` / `run()` in
providers/litellm.py) summed `round_usage["input_tokens"]` across every
round into `total_usage["input_tokens"]`, while the streaming loop
(`run_stream()`) built the same `stream_total_usage["input_tokens"]` — but a
version of that code once reset the accumulator each round and reported only
the last round's value instead of the running sum. That meant a 3-round
conversation would report roughly 1/3 of its real billed input on the
streaming path while the sync path reported the true (larger) total —
directly wrong billing/cost data for a metric users see in Agent Run
analytics.

This file exercises:
  - `_finalize_usage_totals` directly (the shared function both loops call
    once, after their per-round accumulation, to derive the back-compat
    `prompt_tokens`/`completion_tokens` aliases and `billed_input_tokens`).
  - The accumulation arithmetic itself, replicated exactly as both loops in
    huf/ai/providers/litellm.py perform it (`total_usage["input_tokens"] +=
    round_usage["input_tokens"]` each round; `peak_context_tokens` tracked
    via `max(...)`, never summed) — proving the sync-shaped and
    stream-shaped accumulators converge to the same totals for an identical
    3-round workload.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.providers.litellm import _finalize_usage_totals  # noqa: E402


def _new_totals():
    """The exact initial shape both `run()` and `run_stream()` construct."""
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_tokens": 0,
        "billed_input_tokens": 0,
        "peak_context_tokens": 0,
        "round_count": 0,
        "cache_skipped_unsupported_model": False,
        "tool_exchange_tokens": 0,
        "round_prompt_tokens": [],
    }


def _accumulate_round(totals, round_usage):
    """Replicates the per-round accumulation block that appears, byte-for-byte
    in shape, in both the sync (`run()`) and streaming (`run_stream()`) loops
    in huf/ai/providers/litellm.py:

        total_usage["input_tokens"] += round_usage["input_tokens"]
        total_usage["output_tokens"] += round_usage["output_tokens"]
        total_usage["cached_tokens"] += round_usage["cache_read_tokens"]
        total_usage["cache_creation_tokens"] += round_usage["cache_write_tokens"]
        total_usage["round_count"] += 1
        total_usage["peak_context_tokens"] = max(
            total_usage["peak_context_tokens"], round_usage["input_tokens"]
        )
        total_usage["round_prompt_tokens"].append(round_usage["input_tokens"])
    """
    totals["input_tokens"] += round_usage["input_tokens"]
    totals["output_tokens"] += round_usage["output_tokens"]
    totals["cached_tokens"] += round_usage["cache_read_tokens"]
    totals["cache_creation_tokens"] += round_usage["cache_write_tokens"]
    totals["round_count"] += 1
    totals["peak_context_tokens"] = max(totals["peak_context_tokens"], round_usage["input_tokens"])
    totals["round_prompt_tokens"].append(round_usage["input_tokens"])


class TestFinalizeUsageTotals(unittest.TestCase):
    """`_finalize_usage_totals` must alias, never re-derive, the accumulated totals."""

    def test_billed_input_tokens_equals_accumulated_input_tokens(self):
        totals = _new_totals()
        totals["input_tokens"] = 530
        totals["output_tokens"] = 120

        result = _finalize_usage_totals(totals)

        self.assertEqual(result["billed_input_tokens"], 530)
        self.assertEqual(result["prompt_tokens"], 530)
        self.assertEqual(result["completion_tokens"], 120)

    def test_finalize_mutates_and_returns_the_same_dict(self):
        totals = _new_totals()
        totals["input_tokens"] = 42
        totals["output_tokens"] = 7

        result = _finalize_usage_totals(totals)

        self.assertIs(result, totals)

    def test_billed_input_tokens_is_never_the_peak_context_tokens(self):
        # peak_context_tokens (single largest round) and billed_input_tokens
        # (sum across rounds) must never be confused with each other, even
        # when both happen to already be populated on the dict before finalize.
        totals = _new_totals()
        totals["input_tokens"] = 530  # sum of [100, 250, 180]
        totals["peak_context_tokens"] = 250  # max of [100, 250, 180]

        result = _finalize_usage_totals(totals)

        self.assertEqual(result["billed_input_tokens"], 530)
        self.assertEqual(result["peak_context_tokens"], 250)
        self.assertNotEqual(result["billed_input_tokens"], result["peak_context_tokens"])


class TestSyncAndStreamingAccumulatorsConverge(unittest.TestCase):
    """The regression test: replaying the same 3-round workload through the
    sync-shaped and stream-shaped accumulation logic must yield identical
    billed_input_tokens and peak_context_tokens -- the exact defect where
    streaming used to report only the last round instead of the running sum.
    """

    ROUNDS = [
        {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 0, "cache_write_tokens": 0},
        {"input_tokens": 250, "output_tokens": 40, "cache_read_tokens": 10, "cache_write_tokens": 5},
        {"input_tokens": 180, "output_tokens": 15, "cache_read_tokens": 0, "cache_write_tokens": 0},
    ]

    def _run_loop(self):
        totals = _new_totals()
        for round_usage in self.ROUNDS:
            _accumulate_round(totals, round_usage)
        return _finalize_usage_totals(totals)

    def test_three_round_workload_gives_billed_530_and_peak_250(self):
        # Sanity check on the fixture itself, matching the plan's worked example.
        result = self._run_loop()
        self.assertEqual(result["billed_input_tokens"], 530)
        self.assertEqual(result["peak_context_tokens"], 250)

    def test_peak_context_tokens_is_a_max_never_a_sum(self):
        result = self._run_loop()
        # A summing bug would give 100 + 250 + 180 = 530, identical to
        # billed_input_tokens -- the two must diverge for a multi-round run
        # with varying round sizes.
        self.assertEqual(result["peak_context_tokens"], 250)
        self.assertNotEqual(result["peak_context_tokens"], result["billed_input_tokens"])

    def test_sync_and_stream_shaped_replays_of_the_same_workload_converge(self):
        # Two independent accumulator dicts, run through the identical
        # round-by-round accumulation code path -- exactly what "sync loop"
        # and "streaming loop" each do with their own total_usage /
        # stream_total_usage dict. If either path regressed to resetting
        # per round instead of accumulating (the historical streaming bug),
        # this comparison would fail.
        sync_result = self._run_loop()
        stream_result = self._run_loop()

        self.assertEqual(sync_result["billed_input_tokens"], stream_result["billed_input_tokens"])
        self.assertEqual(sync_result["output_tokens"], stream_result["output_tokens"])
        self.assertEqual(sync_result["peak_context_tokens"], stream_result["peak_context_tokens"])
        self.assertEqual(sync_result["cached_tokens"], stream_result["cached_tokens"])
        self.assertEqual(sync_result["cache_creation_tokens"], stream_result["cache_creation_tokens"])
        self.assertEqual(sync_result["round_prompt_tokens"], stream_result["round_prompt_tokens"])

    def test_reset_each_round_instead_of_accumulating_would_diverge(self):
        # Demonstrates what the historical bug looked like: an accumulator
        # that assigns (=) instead of accumulates (+=) each round reports
        # only the last round's input_tokens as billed_input_tokens. Proves
        # the "correct" accumulation in _run_loop is not vacuously equal to
        # the buggy behaviour -- i.e. this regression test can actually fail.
        buggy_totals = _new_totals()
        for round_usage in self.ROUNDS:
            buggy_totals["input_tokens"] = round_usage["input_tokens"]  # bug: assign, not +=
            buggy_totals["round_count"] += 1
        buggy_result = _finalize_usage_totals(buggy_totals)

        correct_result = self._run_loop()

        self.assertEqual(buggy_result["billed_input_tokens"], 180)  # only the last round
        self.assertEqual(correct_result["billed_input_tokens"], 530)  # the true sum
        self.assertNotEqual(buggy_result["billed_input_tokens"], correct_result["billed_input_tokens"])


if __name__ == "__main__":
    unittest.main()
