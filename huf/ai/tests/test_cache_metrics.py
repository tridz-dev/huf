from frappe.tests import UnitTestCase

from huf.ai.cache_metrics import compute_run_metrics


class TestCacheMetrics(UnitTestCase):
    def test_metrics_are_null_when_usage_snapshot_missing(self):
        run = {"usage_snapshot": None, "cost": None}
        metrics = compute_run_metrics(run)
        self.assertIsNone(metrics["cache_read_share"])
        self.assertIsNone(metrics["effective_input_multiplier"])
        self.assertIsNone(metrics["wasted_writes_tokens"])
        self.assertEqual(metrics["prefix_stability"], "unavailable")

    def test_cache_read_share_and_multiplier(self):
        run = {
            "usage_snapshot": '{"input_tokens": 1000, "cache_read_tokens": 600, "cache_creation_tokens": 0}',
            "cost": 0.002,
        }
        metrics = compute_run_metrics(run)
        self.assertAlmostEqual(metrics["cache_read_share"], 0.6)
        # 600 * 0.1 + 0 * 1.25 + 400 * 1.0 = 460 -> 460/1000 = 0.46
        self.assertAlmostEqual(metrics["effective_input_multiplier"], 0.46)

    def test_prefix_stability_compares_against_previous_run(self):
        current = {
            "usage_snapshot": '{"prefix_breakpoints": [{"marker": "instructions", "prefix_hash": "abc123"}]}',
        }
        same = {
            "usage_snapshot": '{"prefix_breakpoints": [{"marker": "instructions", "prefix_hash": "abc123"}]}',
        }
        changed = {
            "usage_snapshot": '{"prefix_breakpoints": [{"marker": "instructions", "prefix_hash": "zzz999"}]}',
        }
        self.assertEqual(compute_run_metrics(current, same)["prefix_stability"], "stable")
        self.assertEqual(compute_run_metrics(current, changed)["prefix_stability"], "changed")
        self.assertEqual(compute_run_metrics(current, {"usage_snapshot": None})["prefix_stability"], "unknown")
