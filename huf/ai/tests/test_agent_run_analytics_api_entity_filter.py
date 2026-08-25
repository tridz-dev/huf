# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unit tests for `_filter_rows_by_entity`, the pure helper extracted from
`get_execution_analytics` (P7-T1's `entity` param) so the filtering logic
that used to be inlined as

    if entity:
        rows = [row for row in rows if row.get(dimension) == entity]

can be exercised without a live bench. `get_execution_analytics` itself is a
`frappe.whitelist`-decorated function doing real `frappe.db.get_all` /
`frappe.db.exists` calls, which is not mockable via the standalone
`_stub_env` pattern -- so this file follows the same extraction approach as
`test_agent_run_analytics_api_derived_rates.py` did for `_add_derived_rates`:
test the extracted pure function directly, manually computing the expected
filtered/aggregated result and comparing against the helper's output.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stub_env  # noqa: E402

_stub_env.install()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from huf.ai.agent_run_analytics_api import _filter_rows_by_entity  # noqa: E402


def _rows():
    return [
        {"bucket_start": "2026-08-20 00:00:00", "provider": "openai", "run_count": 5},
        {"bucket_start": "2026-08-20 01:00:00", "provider": "anthropic", "run_count": 3},
        {"bucket_start": "2026-08-20 02:00:00", "provider": "openai", "run_count": 2},
        {"bucket_start": "2026-08-20 03:00:00", "provider": "google", "run_count": 1},
    ]


class TestFilterRowsByEntity(unittest.TestCase):
    def test_entity_filter_matches_only_matching_rows(self):
        rows = _rows()
        result = _filter_rows_by_entity(rows, "provider", "openai")
        # Manual filter, same semantics as the pre-extraction inline code.
        expected = [row for row in rows if row.get("provider") == "openai"]
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(row["provider"] == "openai" for row in result))

    def test_entity_none_leaves_rows_unfiltered(self):
        rows = _rows()
        result = _filter_rows_by_entity(rows, "provider", None)
        self.assertEqual(result, rows)
        self.assertIs(result, rows)  # passthrough, not a filtered copy

    def test_entity_empty_string_leaves_rows_unfiltered(self):
        rows = _rows()
        result = _filter_rows_by_entity(rows, "provider", "")
        self.assertEqual(result, rows)
        self.assertIs(result, rows)

    def test_entity_matching_nothing_returns_empty_list(self):
        rows = _rows()
        result = _filter_rows_by_entity(rows, "provider", "does-not-exist")
        self.assertEqual(result, [])

    def test_entity_filter_on_different_dimension(self):
        rows = [
            {"agent": "agent-a", "run_count": 4},
            {"agent": "agent-b", "run_count": 6},
            {"agent": "agent-a", "run_count": 1},
        ]
        result = _filter_rows_by_entity(rows, "agent", "agent-a")
        self.assertEqual(len(result), 2)
        self.assertEqual(sum(row["run_count"] for row in result), 5)

    def test_dimension_value_validation_unaffected(self):
        # _filter_rows_by_entity has no opinion on which dimension names are
        # valid -- that check (`dimension not in DIMENSION_FIELDS`) lives
        # earlier in get_execution_analytics and is unchanged by this
        # extraction; this test just confirms the helper doesn't itself
        # raise or reject unknown dimension names (it can't validate them,
        # it only reads `row.get(dimension)`), which is the same behaviour
        # the inline code had.
        rows = _rows()
        result = _filter_rows_by_entity(rows, "not_a_real_dimension", "openai")
        self.assertEqual(result, [])  # no row has this key equal to "openai"


if __name__ == "__main__":
    unittest.main()
