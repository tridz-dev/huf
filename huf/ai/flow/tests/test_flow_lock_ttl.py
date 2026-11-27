"""Run lock TTL + heartbeat, recovery after a killed worker, and the wake sweeper lock."""

import time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.flow import engine
from huf.ai.flow.runs import park


class TestRunLockTTL(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.name = f"_test-lock-{frappe.generate_hash(length=8)}"
		self.key = engine._run_lock_key(self.name)

	def tearDown(self):
		engine._release_run_lock(self.name)
		frappe.db.delete("Agent Flow Run", {"name": self.name})
		frappe.db.commit()

	def _short_lock(self):
		"""A 1 s TTL refreshed every 0.2 s, so expiry can be observed."""
		return patch.multiple(engine, RUN_LOCK_TTL_SECONDS=1, RUN_LOCK_HEARTBEAT_SECONDS=0.2)

	def _held(self) -> bool:
		return bool(frappe.cache().get(self.key))

	def _kill_worker(self):
		"""What a killed process leaves behind: the key, with nothing refreshing or releasing it."""
		engine._stop_run_lock_heartbeat(self.key)

	def test_ttl_is_step_time_plus_margin(self):
		self.assertEqual(engine.RUN_LOCK_TTL_SECONDS, engine.RUN_LOCK_STEP_SECONDS + engine.RUN_LOCK_MARGIN_SECONDS)
		self.assertEqual(engine.RUN_LOCK_TTL_SECONDS, 120)
		self.assertTrue(engine._acquire_run_lock(self.name))
		self.assertTrue(0 < frappe.cache().ttl(self.key) <= 120)

	def test_a_step_longer_than_the_ttl_keeps_the_lock(self):
		with self._short_lock():
			self.assertTrue(engine._acquire_run_lock(self.name))
			time.sleep(2)
			self.assertTrue(self._held())
			self.assertFalse(engine._acquire_run_lock(self.name))
			engine._release_run_lock(self.name)
		self.assertFalse(self._held())
		self.assertNotIn(self.key, engine._run_lock_heartbeats)

	def test_killed_worker_lock_expires_and_the_sweeper_recovers_the_run(self):
		frappe.db.bulk_insert(
			"Agent Flow Run",
			["name", "status", "modified"],
			[(self.name, "Running", add_to_date(now_datetime(), minutes=-45))],
		)
		frappe.db.commit()
		with self._short_lock():
			self.assertTrue(engine._acquire_run_lock(self.name))
			self.assertNotIn(self.name, engine.sweep_stale_runs())  # a live worker holds it
			self._kill_worker()
			time.sleep(1.5)
		self.assertFalse(self._held(), "stuck lock")
		self.assertIn(self.name, engine.sweep_stale_runs())
		self.assertEqual(frappe.db.get_value("Agent Flow Run", self.name, "status"), "Failed")


class TestWakeSweeperLock(IntegrationTestCase):
	def setUp(self):
		self.key = frappe.cache().make_key(park.WAKE_LOCK_KEY)
		frappe.cache().delete(self.key)
		self.addCleanup(frappe.cache().delete, self.key)

	def test_lock_fits_between_the_budget_and_the_tick(self):
		self.assertEqual(park.WAKE_LOCK_TTL_SECONDS, 55)
		self.assertLess(park.WAKE_BUDGET_SECONDS, park.WAKE_LOCK_TTL_SECONDS)

	def test_an_overlapping_tick_does_nothing(self):
		seen = []

		def drain(now, limit):
			seen.append(frappe.cache().ttl(self.key))
			self.assertEqual(park.wake_due_waits(), [])  # the overlapping tick
			return ["run"]

		with patch.object(park, "_drain_due_waits", side_effect=drain):
			self.assertEqual(park.wake_due_waits(), ["run"])
		self.assertEqual(len(seen), 1)
		self.assertTrue(0 < seen[0] <= 55)
		self.assertFalse(frappe.cache().get(self.key))

	def test_lock_is_released_when_the_sweep_raises(self):
		with patch.object(park, "_drain_due_waits", side_effect=RuntimeError), self.assertRaises(RuntimeError):
			park.wake_due_waits()
		self.assertFalse(frappe.cache().get(self.key))
