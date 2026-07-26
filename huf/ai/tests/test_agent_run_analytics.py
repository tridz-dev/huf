from datetime import datetime

from frappe.tests import UnitTestCase

from huf.ai.agent_run_analytics import _bucket_start, _dimension_key


class TestAgentRunAnalytics(UnitTestCase):
    def test_hour_and_day_buckets_are_deterministic(self):
        value = datetime(2026, 7, 26, 14, 37, 9)
        self.assertEqual(_bucket_start(value, "hour"), datetime(2026, 7, 26, 14, 0))
        self.assertEqual(_bucket_start(value, "day"), datetime(2026, 7, 26, 0, 0))

    def test_dimension_key_preserves_missing_dimensions(self):
        self.assertEqual(
            _dimension_key({"agent": "Support", "provider": None, "model": "gemini", "run_kind": None}),
            "Support|__none__|gemini|__none__",
        )
