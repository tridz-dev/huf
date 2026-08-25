# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Tests for huf.ai.agent_run_analytics._accumulate_composition and
_load_segment_tokens.

`huf/ai/tests/test_agent_run_analytics.py` already covers DIMENSION_FIELDS
append-last compatibility (`_dimension_key`, `_bucket_start`, and the
"conversation appended last so stored keys stay decodable" contract) -- not
duplicated here.

_accumulate_composition:
  - a segment total becomes, and STAYS, None once any contributing run
    reports None for that segment (poisons the running sum permanently,
    even if a later run reports a real number for it)
  - numeric values (int or float) accumulate normally
  - non-numeric, non-None values are ignored rather than raising

_load_segment_tokens:
  - degrades to {} on: no snapshot, a JSON string that fails to parse, a
    non-dict snapshot, a dict snapshot with no segment_tokens key, and a
    segment_tokens value that itself isn't a dict
  - passes through an already-parsed dict snapshot's segment_tokens as-is
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.agent_run_analytics import _accumulate_composition, _load_segment_tokens  # noqa: E402


class TestAccumulateComposition(unittest.TestCase):
    def test_numeric_values_accumulate(self):
        totals = {}
        _accumulate_composition(totals, {"system": 10, "tools": 5})
        _accumulate_composition(totals, {"system": 20, "tools": 3})
        self.assertEqual(totals["system"], 30)
        self.assertEqual(totals["tools"], 8)

    def test_float_values_accumulate(self):
        totals = {}
        _accumulate_composition(totals, {"knowledge": 1.5})
        _accumulate_composition(totals, {"knowledge": 2.5})
        self.assertEqual(totals["knowledge"], 4.0)

    def test_none_poisons_the_segment_total(self):
        totals = {}
        _accumulate_composition(totals, {"history": 10})
        _accumulate_composition(totals, {"history": None})
        self.assertIsNone(totals["history"])

    def test_none_poisoning_is_permanent_even_after_later_numeric_runs(self):
        # Once a bucket's segment total is None, a subsequent run reporting
        # a real number for that segment must NOT silently "heal" it back
        # to a number -- the bucket already contains at least one run whose
        # true contribution is unknown, so the total must stay unknown.
        totals = {}
        _accumulate_composition(totals, {"tools": 10})
        _accumulate_composition(totals, {"tools": None})
        _accumulate_composition(totals, {"tools": 50})
        self.assertIsNone(totals["tools"])

    def test_first_run_reporting_none_for_a_fresh_segment_starts_it_at_none(self):
        totals = {}
        _accumulate_composition(totals, {"message": None})
        self.assertIsNone(totals["message"])
        _accumulate_composition(totals, {"message": 99})
        self.assertIsNone(totals["message"])

    def test_non_numeric_non_none_values_are_ignored_not_raised(self):
        totals = {}
        # Should not raise for a string, list, or dict value.
        _accumulate_composition(totals, {"system": "not a number"})
        _accumulate_composition(totals, {"tools": [1, 2, 3]})
        _accumulate_composition(totals, {"knowledge": {"nested": True}})
        self.assertNotIn("system", totals)
        self.assertNotIn("tools", totals)
        self.assertNotIn("knowledge", totals)

    def test_ignored_garbage_does_not_block_a_later_real_number(self):
        totals = {}
        _accumulate_composition(totals, {"history": "garbage"})
        _accumulate_composition(totals, {"history": 7})
        self.assertEqual(totals["history"], 7)

    def test_multiple_segments_tracked_independently(self):
        totals = {}
        _accumulate_composition(totals, {"system": 10, "tools": None, "message": 5})
        _accumulate_composition(totals, {"system": 10, "tools": 100, "message": None})
        self.assertEqual(totals["system"], 20)
        self.assertIsNone(totals["tools"])
        self.assertIsNone(totals["message"])

    def test_empty_segment_tokens_is_a_no_op(self):
        totals = {"system": 10}
        _accumulate_composition(totals, {})
        self.assertEqual(totals, {"system": 10})


class TestLoadSegmentTokens(unittest.TestCase):
    def test_none_snapshot_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens(None), {})

    def test_empty_string_snapshot_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens(""), {})

    def test_bad_json_string_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens("{not valid json"), {})

    def test_valid_json_string_with_segment_tokens_is_parsed(self):
        snapshot = '{"segment_tokens": {"system": 10, "tools": 5}}'
        self.assertEqual(_load_segment_tokens(snapshot), {"system": 10, "tools": 5})

    def test_already_parsed_dict_snapshot_passes_through(self):
        snapshot = {"segment_tokens": {"history": 3}}
        self.assertEqual(_load_segment_tokens(snapshot), {"history": 3})

    def test_non_dict_snapshot_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens(["not", "a", "dict"]), {})
        self.assertEqual(_load_segment_tokens(42), {})

    def test_dict_snapshot_missing_segment_tokens_key_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens({"other_key": 1}), {})

    def test_segment_tokens_value_not_a_dict_returns_empty_dict(self):
        self.assertEqual(_load_segment_tokens({"segment_tokens": "not a dict"}), {})
        self.assertEqual(_load_segment_tokens({"segment_tokens": [1, 2]}), {})
        self.assertEqual(_load_segment_tokens({"segment_tokens": None}), {})


if __name__ == "__main__":
    unittest.main()
