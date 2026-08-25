"""
Tests for the live automation scheduler entrypoint, run_due_automations.

Covers:
- No-op when automation_runtime_is_new() is False (legacy runtime active).
- No-op when the Automation Trigger DocType does not exist.
- A due trigger fires run_automation with the automation name, now=True,
  and a trigger_context of type "schedule".
- The per-trigger cache lock short-circuits a second fire.
- The stale-batch re-check: a fresh next_execution read in the future
  prevents execution even if the trigger was due in the initial batch.
- next_execution is claimed (advanced) before run_automation executes,
  and the advanced value matches the trigger's interval.
- A trigger that raises is swallowed, logged via frappe.log_error, and
  does not stop the remaining triggers in the batch from firing.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_automation_scheduler
"""
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from huf.ai import automation_scheduler


class TestRunDueAutomations(unittest.TestCase):
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=False)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_no_op_under_legacy_runtime(self, mock_run_automation, mock_frappe, mock_runtime_is_new):
        automation_scheduler.run_due_automations()

        mock_frappe.db.exists.assert_not_called()
        mock_frappe.get_all.assert_not_called()
        mock_run_automation.assert_not_called()

    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_no_op_when_doctype_missing(self, mock_run_automation, mock_frappe, mock_runtime_is_new):
        mock_frappe.db.exists.return_value = False

        automation_scheduler.run_due_automations()

        mock_frappe.get_all.assert_not_called()
        mock_run_automation.assert_not_called()

    @patch("huf.ai.automation_scheduler.now_datetime")
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_due_trigger_fires(self, mock_run_automation, mock_frappe, mock_runtime_is_new, mock_now_datetime):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_now_datetime.return_value = now

        mock_frappe.db.exists.return_value = True
        trigger = {
            "name": "AT-001",
            "automation": "My Automation",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": now,
            "last_execution": None,
        }
        mock_frappe.get_all.return_value = [trigger]

        cache = MagicMock()
        cache.get_value.return_value = None
        mock_frappe.cache.return_value = cache
        mock_frappe.db.get_value.return_value = now

        automation_scheduler.run_due_automations()

        mock_run_automation.assert_called_once()
        args, kwargs = mock_run_automation.call_args
        self.assertEqual(args[0], "My Automation")
        self.assertTrue(kwargs.get("now"))
        self.assertEqual(kwargs.get("trigger_context", {}).get("type"), "schedule")

    @patch("huf.ai.automation_scheduler.now_datetime")
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_cache_lock_short_circuits_second_fire(
        self, mock_run_automation, mock_frappe, mock_runtime_is_new, mock_now_datetime
    ):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_now_datetime.return_value = now

        mock_frappe.db.exists.return_value = True
        trigger = {
            "name": "AT-001",
            "automation": "My Automation",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": now,
            "last_execution": None,
        }
        mock_frappe.get_all.return_value = [trigger]

        cache = MagicMock()
        cache.get_value.return_value = "already-locked"
        mock_frappe.cache.return_value = cache

        automation_scheduler.run_due_automations()

        mock_frappe.db.get_value.assert_not_called()
        mock_run_automation.assert_not_called()

    @patch("huf.ai.automation_scheduler.now_datetime")
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_stale_batch_recheck_prevents_execution(
        self, mock_run_automation, mock_frappe, mock_runtime_is_new, mock_now_datetime
    ):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_now_datetime.return_value = now

        mock_frappe.db.exists.return_value = True
        trigger = {
            "name": "AT-001",
            "automation": "My Automation",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": now,
            "last_execution": None,
        }
        mock_frappe.get_all.return_value = [trigger]

        cache = MagicMock()
        cache.get_value.return_value = None
        mock_frappe.cache.return_value = cache
        # Fresh read under the lock shows next_execution has already moved
        # into the future (another tick beat us to it).
        mock_frappe.db.get_value.return_value = now + timedelta(hours=1)

        automation_scheduler.run_due_automations()

        mock_run_automation.assert_not_called()

    @patch("huf.ai.automation_scheduler.add_to_date")
    @patch("huf.ai.automation_scheduler.now_datetime")
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_next_execution_claimed_before_execution(
        self, mock_run_automation, mock_frappe, mock_runtime_is_new, mock_now_datetime, mock_add_to_date
    ):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_now_datetime.return_value = now
        advanced = now + timedelta(hours=2)
        mock_add_to_date.return_value = advanced

        mock_frappe.db.exists.return_value = True
        trigger = {
            "name": "AT-001",
            "automation": "My Automation",
            "scheduled_interval": "Hourly",
            "interval_count": 2,
            "next_execution": now,
            "last_execution": None,
        }
        mock_frappe.get_all.return_value = [trigger]

        cache = MagicMock()
        cache.get_value.return_value = None
        mock_frappe.cache.return_value = cache
        mock_frappe.db.get_value.return_value = now

        call_order = []
        mock_frappe.db.set_value.side_effect = lambda *a, **kw: call_order.append("set_value")
        mock_run_automation.side_effect = lambda *a, **kw: call_order.append("run_automation")

        automation_scheduler.run_due_automations()

        mock_add_to_date.assert_called_once_with(now, hours=2, days=0, weeks=0, months=0, years=0)

        set_value_calls = [
            c for c in mock_frappe.db.set_value.call_args_list
            if c.args[:2] == ("Automation Trigger", "AT-001") and "next_execution" in c.args[2]
        ]
        self.assertEqual(len(set_value_calls), 1)
        self.assertEqual(set_value_calls[0].args[2]["next_execution"], advanced)

        self.assertIn("set_value", call_order)
        self.assertIn("run_automation", call_order)
        self.assertLess(call_order.index("set_value"), call_order.index("run_automation"))

    @patch("huf.ai.automation_scheduler.now_datetime")
    @patch("huf.ai.automation_scheduler.automation_runtime_is_new", return_value=True)
    @patch("huf.ai.automation_scheduler.frappe")
    @patch("huf.ai.automation_scheduler.run_automation")
    def test_raising_trigger_is_swallowed_and_does_not_block_batch(
        self, mock_run_automation, mock_frappe, mock_runtime_is_new, mock_now_datetime
    ):
        now = datetime(2026, 1, 1, 12, 0, 0)
        mock_now_datetime.return_value = now

        mock_frappe.db.exists.return_value = True
        trigger_a = {
            "name": "AT-A",
            "automation": "Automation A",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": now,
            "last_execution": None,
        }
        trigger_b = {
            "name": "AT-B",
            "automation": "Automation B",
            "scheduled_interval": "Hourly",
            "interval_count": 1,
            "next_execution": now,
            "last_execution": None,
        }
        mock_frappe.get_all.return_value = [trigger_a, trigger_b]

        cache = MagicMock()
        cache.get_value.return_value = None
        mock_frappe.cache.return_value = cache
        mock_frappe.db.get_value.return_value = now

        def run_side_effect(automation_name, **kwargs):
            if automation_name == "Automation A":
                raise RuntimeError("boom")
            return None

        mock_run_automation.side_effect = run_side_effect

        automation_scheduler.run_due_automations()

        self.assertEqual(mock_run_automation.call_count, 2)
        called_names = [c.args[0] for c in mock_run_automation.call_args_list]
        self.assertIn("Automation A", called_names)
        self.assertIn("Automation B", called_names)
        mock_frappe.log_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
