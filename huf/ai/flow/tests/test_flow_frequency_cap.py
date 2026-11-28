"""Frequency cap: the store, its pruning and the guard chain's cap step."""

import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.channels.outbound import guard, guard_steps
from huf.ai.flow.policy import frequency_cap as cap

DAY = 86400
WEEK = 7 * DAY
NOW = 1_800_000_000.0


class TestFlowFrequencyCap(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.member = f"_test-cap-{frappe.generate_hash(length=10)}"
		clock = patch.object(cap.time, "time", return_value=NOW)
		self.clock = clock.start()
		self.addCleanup(clock.stop)

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete(cap.DOCTYPE, {"member_key": ["like", f"{self.member}%"]})
		frappe.db.commit()

	def test_send_over_the_limit_is_refused_and_not_counted(self):
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 0)
		self.assertEqual([cap.incr(self.member, "whatsapp", DAY, limit=3) for _ in range(3)], [1, 2, 3])
		self.assertIsNone(cap.incr(self.member, "whatsapp", DAY, limit=3))
		self.assertIsNone(cap.incr(self.member, "whatsapp", DAY, limit=3))
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 3)

	def test_zero_limit_refuses_the_first_send(self):
		self.assertIsNone(cap.incr(self.member, "whatsapp", DAY, limit=0))
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 0)

	def test_without_limit_every_send_is_counted(self):
		self.assertEqual([cap.incr(self.member, "email", DAY) for _ in range(3)], [1, 2, 3])

	def test_one_row_per_member_channel_and_window(self):
		cap.incr(self.member, "whatsapp", DAY)
		cap.incr(self.member, "whatsapp", DAY)
		cap.incr(self.member, "email", DAY)
		cap.incr(f"{self.member}-other", "whatsapp", DAY)
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 2)
		self.assertEqual(cap.check(self.member, "email", DAY), 1)
		self.assertEqual(frappe.db.count(cap.DOCTYPE, {"member_key": self.member}), 2)

	def test_day_and_week_windows_count_separately(self):
		# a moment where both windows start together, so only the length tells the rows apart
		self.clock.return_value = float(int(NOW) // WEEK * WEEK)
		self.assertEqual(cap.incr(self.member, "whatsapp", DAY, limit=1), 1)
		self.assertEqual(cap.check(self.member, "whatsapp", WEEK), 0)
		self.assertEqual([cap.incr(self.member, "whatsapp", WEEK, limit=2) for _ in range(3)], [1, 2, None])
		self.assertIsNone(cap.incr(self.member, "whatsapp", DAY, limit=1))
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 1)
		self.assertEqual(cap.check(self.member, "whatsapp", WEEK), 2)
		self.assertEqual(frappe.db.count(cap.DOCTYPE, {"member_key": self.member}), 2)

	def test_a_rollback_after_the_claim_keeps_the_count(self):
		cap.incr(self.member, "whatsapp", DAY, limit=1)
		frappe.db.rollback()
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 1)
		self.assertIsNone(cap.incr(self.member, "whatsapp", DAY, limit=1))

	def test_next_window_starts_at_zero(self):
		cap.incr(self.member, "whatsapp", DAY, limit=1)
		self.clock.return_value = NOW + DAY
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 0)
		self.assertEqual(cap.incr(self.member, "whatsapp", DAY, limit=1), 1)

	def test_database_rejects_a_second_row_for_the_same_key(self):
		cap.incr(self.member, "whatsapp", DAY)
		row = frappe.db.get_value(
			cap.DOCTYPE, {"member_key": self.member}, ["window_seconds", "window_start"], as_dict=True
		)
		with self.assertRaises(Exception) as raised:
			frappe.db.sql(
				f"insert into {cap.TABLE} (name, member_key, channel, window_seconds, window_start) values (%s, %s, %s, %s, %s)",
				(frappe.generate_hash(), self.member, "whatsapp", row.window_seconds, row.window_start),
			)
		self.assertTrue(frappe.db.is_duplicate_entry(raised.exception))

	def test_bad_input_raises_without_naming_the_member(self):
		secret = "15550100999"
		for args in (
			("", "whatsapp", DAY),
			(secret, "", DAY),
			(secret * 20, "whatsapp", DAY),
			(secret, "whatsapp", 0),
			(secret, "whatsapp", "1d"),
		):
			for call in (cap.incr, cap.check):
				with self.assertRaises(ValueError) as raised:
					call(*args)
				self.assertNotIn(secret, str(raised.exception))
		with self.assertRaises(ValueError):
			cap.incr(secret, "whatsapp", DAY, limit=-1)

	def _race(self, limit):
		"""20 connections, each with an open snapshot, claim one send at the same moment."""
		site, member, workers = frappe.local.site, self.member, 20
		barrier = threading.Barrier(workers)
		results, errors = [], []

		def send():
			try:
				frappe.init(site=site)
				frappe.connect()
				cap.check(member, "whatsapp", DAY)  # the sender has already read in this transaction
				barrier.wait(timeout=30)
				results.append(cap.incr(member, "whatsapp", DAY, limit=limit))
			except Exception as exc:
				errors.append(type(exc).__name__ + ": " + str(exc))
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=send) for _ in range(workers)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=60)
		frappe.db.rollback()
		self.assertEqual(errors, [])
		self.assertEqual(len(results), workers)
		return results

	def test_parallel_sends_at_one_below_the_cap_allow_exactly_one(self):
		for _ in range(4):
			cap.incr(self.member, "whatsapp", DAY, limit=5)
		results = self._race(limit=5)
		self.assertEqual([r for r in results if r is not None], [5])
		self.assertEqual(cap.check(self.member, "whatsapp", DAY), 5)

	def test_parallel_first_sends_create_one_row_and_respect_the_cap(self):
		results = self._race(limit=3)
		self.assertEqual(sorted(r for r in results if r is not None), [1, 2, 3])
		self.assertEqual(frappe.db.count(cap.DOCTYPE, {"member_key": self.member}), 1)

	def test_purge_removes_only_long_ended_windows_in_batches(self):
		for member in ("old-a", "old-b", "old-c"):
			cap.incr(f"{self.member}-{member}", "whatsapp", DAY)
		cap.incr(self.member, "whatsapp", 366 * DAY)  # starts long ago, still open
		self.clock.return_value = NOW + DAY  # just ended: inside the grace period
		cap.incr(self.member, "email", DAY)
		cap.purge_expired(batch_size=2)
		self.assertEqual(self._rows(), 5)
		self.clock.return_value = NOW + 2 * DAY
		self.assertGreaterEqual(cap.purge_expired(batch_size=2), 3)
		self.assertEqual(self._rows(), 2)
		self.assertIn(
			"huf.ai.flow.policy.frequency_cap.purge_expired", frappe.get_hooks("scheduler_events")["daily"]
		)

	def _rows(self):
		return frappe.db.count(cap.DOCTYPE, {"member_key": ["like", f"{self.member}%"]})


class TestGuardCapStep(IntegrationTestCase):
	"""The cap step as the guard chain runs it: last, after the app hooks."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.member = f"_test-cap-{frappe.generate_hash(length=10)}"
		self.registry = {}
		self.app_hooks = []
		get_hooks, get_attr = frappe.get_hooks, frappe.get_attr

		def hooks(name=None, *args, **kwargs):
			if name == guard_steps.CAP_HOOK:
				return [path for path in self.registry if path.startswith("cap.")]
			return get_hooks(name, *args, **kwargs)

		for patcher in (
			patch.object(cap.time, "time", return_value=NOW),
			patch.object(guard, "BUILTIN_STEPS", []),
			patch.object(guard, "_hook_paths", side_effect=lambda: self.app_hooks),
			patch.object(frappe, "get_hooks", side_effect=hooks),
			patch.object(frappe, "get_attr", side_effect=lambda p: self.registry.get(p) or get_attr(p)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete(cap.DOCTYPE, {"member_key": ["like", f"{self.member}%"]})
		frappe.db.commit()

	def resolver(self, *answers):
		self.registry = {f"cap.{i}": lambda request, a=answer: a for i, answer in enumerate(answers)}

	def send(self, live=True, **over):
		request = {"member_key": self.member, "channel": "whatsapp", "flow_id": "f1", "live": live, **over}
		return guard.evaluate(request)

	def count(self, channel="whatsapp", window=DAY):
		return cap.check(self.member, channel, window)

	def assertBlocked(self, result, reason="freq_cap"):
		self.assertEqual(result, guard.GuardResult(False, reason, "frequency_cap"))

	def test_no_resolver_or_no_value_is_no_cap(self):
		self.assertTrue(self.send().allowed)
		self.resolver(None, [])
		self.assertTrue(self.send().allowed)
		self.assertEqual(self.count(), 0)

	def test_send_over_the_cap_is_blocked_across_flows(self):
		self.resolver({"limit": 2, "window_seconds": DAY})
		self.assertTrue(self.send(flow_id="f1").allowed)
		self.assertTrue(self.send(flow_id="f2").allowed)
		self.assertBlocked(self.send(flow_id="f3"))
		self.assertEqual(self.count(), 2)

	def test_all_caps_apply_shortest_window_first(self):
		self.resolver({"limit": 5, "window_seconds": WEEK}, [{"limit": 1, "window_seconds": DAY}])
		self.assertTrue(self.send().allowed)
		self.assertBlocked(self.send())
		self.assertEqual((self.count(), self.count(window=WEEK)), (1, 1))

	def test_a_later_window_refusing_keeps_the_earlier_count(self):
		self.resolver([{"limit": 0, "window_seconds": WEEK}, {"limit": 5, "window_seconds": DAY}])
		self.assertBlocked(self.send())
		self.assertEqual((self.count(), self.count(window=WEEK)), (1, 0))

	def test_caps_on_one_counter_count_once_at_the_lowest_limit(self):
		self.resolver({"limit": 9, "window_seconds": DAY}, {"limit": 2, "window_seconds": DAY})
		self.assertTrue(self.send().allowed)
		self.assertEqual(self.count(), 1)
		self.assertTrue(self.send().allowed)
		self.assertBlocked(self.send())

	def test_bucket_replaces_the_channel(self):
		self.resolver({"limit": 1, "window_seconds": DAY, "bucket": "whatsapp:marketing"})
		self.assertTrue(self.send().allowed)
		self.assertEqual((self.count(), self.count("whatsapp:marketing")), (0, 1))

	def test_preview_never_counts_but_shows_a_full_cap(self):
		self.resolver({"limit": 1, "window_seconds": DAY})
		for live in (False, None, 1):
			self.assertTrue(self.send(live=live).allowed)
		self.assertEqual(self.count(), 0)
		self.assertTrue(self.send().allowed)
		self.assertBlocked(self.send(live=False))

	def test_resolver_or_store_error_and_invalid_caps_block(self):
		def broken(request):
			raise RuntimeError(request["member_key"])

		self.registry = {"cap.0": broken}
		self.assertBlocked(self.send(), "hook_error")
		good = {"limit": 1, "window_seconds": DAY}
		for bad in (
			{},
			False,
			"1/day",
			{"limit": -1, "window_seconds": DAY},
			{"limit": True, "window_seconds": DAY},
			{"limit": 1, "window_seconds": 0},
			{"limit": 1, "window_seconds": 31622401},
			{**good, "bucket": ""},
			{**good, "bucket": None},
			{**good, "window": 1},
			[good, {"limit": 1}],
		):
			with self.subTest(bad=bad):
				self.resolver(bad)
				self.assertBlocked(self.send(), "hook_error")
		self.assertEqual(self.count(), 0)
		self.resolver(good)
		self.assertBlocked(self.send(member_key=None), "hook_error")
		for live, name in ((True, "incr"), (False, "check")):
			with patch.object(cap, name, side_effect=RuntimeError):
				self.assertBlocked(self.send(live=live), "hook_error")

	def test_slow_resolver_times_out_and_counts_nothing(self):
		release = threading.Event()
		self.addCleanup(release.set)
		self.registry = {"cap.0": lambda request: release.wait(5) and None}
		result = guard.evaluate({"member_key": self.member, "live": True}, timeout=0.05)
		self.assertBlocked(result, "hook_timeout")

	def test_runs_after_app_hooks_and_a_blocked_send_spends_nothing(self):
		seen = []
		self.resolver({"limit": 1, "window_seconds": DAY})
		self.registry["app.block"] = lambda request: (
			seen.append(self.count()) or {"allow": False, "reason": "blocked_by_hook"}
		)
		self.app_hooks = ["app.block"]
		self.assertEqual(self.send().reason, "blocked_by_hook")
		self.assertEqual((seen, self.count()), ([0], 0))

	def test_parallel_guarded_sends_at_one_below_the_cap_allow_exactly_one(self):
		for _ in range(4):
			cap.incr(self.member, "whatsapp", DAY, limit=5)
		site, member, workers = frappe.local.site, self.member, 20
		barrier = threading.Barrier(workers)
		results = []

		def send():
			try:
				frappe.init(site=site)
				frappe.connect()
				barrier.wait(timeout=30)
				request = {"member_key": member, "channel": "whatsapp", "live": True}
				results.append(guard_steps.apply_caps(request, [(DAY, "whatsapp", 5)]))
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=send) for _ in range(workers)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=60)
		frappe.db.rollback()
		self.assertEqual(len(results), workers)
		self.assertEqual(results.count({"allow": True}), 1)
		self.assertEqual(results.count({"allow": False, "reason": "freq_cap"}), workers - 1)
		self.assertEqual(self.count(), 5)
