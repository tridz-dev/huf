"""Frequency cap store: counting, the atomic limit, cross-flow keys and input checks."""

import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.policy import frequency_cap as cap

DAY = 86400
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
		row = frappe.db.get_value(cap.DOCTYPE, {"member_key": self.member}, ["window_start"], as_dict=True)
		with self.assertRaises(Exception) as raised:
			frappe.db.sql(
				f"insert into {cap.TABLE} (name, member_key, channel, window_start) values (%s, %s, %s, %s)",
				(frappe.generate_hash(), self.member, "whatsapp", row.window_start),
			)
		self.assertTrue(frappe.db.is_duplicate_entry(raised.exception))

	def test_bad_input_raises_without_naming_the_member(self):
		secret = "15550100999"
		for args in (("", "whatsapp", DAY), (secret, "", DAY), (secret * 20, "whatsapp", DAY), (secret, "whatsapp", 0), (secret, "whatsapp", "1d")):
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
