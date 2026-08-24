# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) tests proving `huf/ai/automation_scheduler.py`'s
due-trigger decision is deterministic and reproducible under a controllable
fake clock - per project rule: "Automation/scheduler tests must not sleep for
real time. Introduce a testable clock/time abstraction where required. Test:
current time -> advance -> due automation -> scheduler decision."

No `time.sleep()` anywhere in this file. "Now" is entirely driven by
`huf.ai.tests.clock_helpers.FakeClock`, patched into `automation_scheduler`'s
own `now_datetime`/`add_to_date` names via `patch_clock` (see that module's
docstring for why a name-patch, not a product-code clock dependency, is the
right seam here).

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/tests/test_automation_scheduler_clock.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

# huf/ai/tests/conftest.py stubs sys.modules['frappe'] with a MagicMock when
# frappe isn't importable (no bench available). Do the same defensively here
# so this file can also be run outside that conftest's collection scope -
# same pattern as test_factories.py / test_test_provider.py.
if "frappe" not in sys.modules:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	sys.modules["frappe"] = frappe_mock
if "frappe.utils" not in sys.modules:
	utils_mock = MagicMock()
	sys.modules["frappe.utils"] = utils_mock
	sys.modules["frappe"].utils = utils_mock

from huf.ai import automation_scheduler  # noqa: E402
from huf.ai.tests.clock_helpers import FakeClock, patch_clock  # noqa: E402


def _due_trigger(name="AT-0001", automation="AUTO-0001", next_execution=None,
				  scheduled_interval="Daily", interval_count=1):
	return {
		"name": name,
		"automation": automation,
		"scheduled_interval": scheduled_interval,
		"interval_count": interval_count,
		"next_execution": next_execution,
		"last_execution": None,
	}


class FireDueTriggerClockTestCase(unittest.TestCase):
	"""Exercises `_fire_due_trigger` - the actual due-check + fire logic -
	directly, under a fake clock, with only `frappe.cache`/`frappe.db`/
	`run_automation` mocked (per the repo's existing "mock the external
	dependency, assert on call shape" Layer A pattern)."""

	def setUp(self):
		# frappe.cache().get_value(...) -> None means "not locked"; set_value
		# is a no-op we can assert on if needed.
		self.fake_cache = MagicMock()
		self.fake_cache.get_value.return_value = None

		self.patchers = [
			patch.object(automation_scheduler.frappe, "cache", return_value=self.fake_cache),
			patch.object(automation_scheduler.frappe.db, "get_value"),
			patch.object(automation_scheduler.frappe.db, "set_value"),
			patch.object(automation_scheduler.frappe.db, "commit"),
			patch.object(automation_scheduler, "run_automation"),
		]
		for p in self.patchers:
			p.start()
			self.addCleanup(p.stop)

	def test_trigger_with_past_next_execution_is_due_and_fires(self):
		"""current time -> due automation -> scheduler decision (fires)."""
		with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
			now = clock.now_datetime()
			past_next_execution = clock.advance(hours=-1)  # 11:00, in the past relative to `now`
			clock.set(now)  # restore "now" to 12:00 after using advance() to compute the fixture

			trigger = _due_trigger(next_execution=past_next_execution)
			automation_scheduler.frappe.db.get_value.return_value = past_next_execution

			automation_scheduler._fire_due_trigger(trigger, now)

			automation_scheduler.run_automation.assert_called_once()
			_, kwargs = automation_scheduler.run_automation.call_args
			self.assertEqual(kwargs["trigger_name"], "AT-0001")
			self.assertTrue(kwargs["now"])

	def test_trigger_with_future_next_execution_is_not_due_and_does_not_fire(self):
		"""current time -> NOT due -> scheduler decision (skips)."""
		with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
			now = clock.now_datetime()
			future_next_execution = clock.advance(hours=1)  # 13:00, in the future
			clock.set(now)

			trigger = _due_trigger(next_execution=future_next_execution)
			automation_scheduler.frappe.db.get_value.return_value = future_next_execution

			automation_scheduler._fire_due_trigger(trigger, now)

			automation_scheduler.run_automation.assert_not_called()

	def test_advancing_the_clock_flips_a_not_yet_due_trigger_to_due(self):
		"""The exact scenario the project spec calls for: set a fixed "now",
		verify not-due, advance the fake clock forward (no real sleep), and
		verify the same trigger now registers as due."""
		with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
			next_execution = clock.set("2026-01-01 12:30:00")  # 30 min ahead of "now"
			clock.set("2026-01-01 12:00:00")

			trigger = _due_trigger(next_execution=next_execution)
			automation_scheduler.frappe.db.get_value.return_value = next_execution

			# Not due yet at 12:00.
			automation_scheduler._fire_due_trigger(trigger, clock.now_datetime())
			automation_scheduler.run_automation.assert_not_called()

			# Advance the fake clock forward past next_execution - deterministic,
			# no time.sleep() involved.
			new_now = clock.advance(minutes=31)
			self.assertEqual(new_now, __import__("datetime").datetime(2026, 1, 1, 12, 31, 0))

			# Same trigger, same next_execution, later "now" -> now due.
			automation_scheduler._fire_due_trigger(trigger, clock.now_datetime())
			automation_scheduler.run_automation.assert_called_once()

	def test_add_to_date_resolves_against_the_fake_clock_not_wall_clock(self):
		"""`_fire_due_trigger` computes the next `next_execution` via
		`add_to_date(now, ...)`. Prove that also routes through the fake
		clock's arithmetic, not the real wall clock, so the provisional
		next-execution written back is reproducible."""
		with patch_clock(automation_scheduler, initial="2026-01-01 12:00:00") as clock:
			now = clock.now_datetime()
			trigger = _due_trigger(
				next_execution=now, scheduled_interval="Daily", interval_count=2,
			)
			automation_scheduler.frappe.db.get_value.return_value = now

			automation_scheduler._fire_due_trigger(trigger, now)

			automation_scheduler.run_automation.assert_called_once()
			# First set_value call advances next_execution by 2 days (interval_count=2,
			# scheduled_interval="Daily") relative to the fake "now", not real time.
			first_call = automation_scheduler.frappe.db.set_value.call_args_list[0]
			args, _ = first_call
			self.assertEqual(args[0], "Automation Trigger")
			self.assertEqual(args[1], "AT-0001")
			provisional_next = args[2]["next_execution"]
			import datetime
			self.assertEqual(provisional_next, now + datetime.timedelta(days=2))


if __name__ == "__main__":
	unittest.main(verbosity=2)
