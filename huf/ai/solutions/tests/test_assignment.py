from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from huf.ai.solutions import assignment as a
from huf.ai.solutions.tests._fixtures import make_gateway, make_solution


class TestAssignment(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.gw = make_gateway().name
		self.s1 = make_solution().name
		self.s2 = make_solution().name
		self.now = now_datetime()

	def tearDown(self):
		frappe.db.rollback()

	def _count(self, contact="c1"):
		return frappe.db.count("Conversation Assignment", {"gateway": self.gw, "contact": contact})

	def test_missing_row_is_safe(self):
		self.assertIsNone(a.get_pin(self.gw, "nobody"))
		self.assertIsNone(a.current_solution(self.gw, "nobody"))
		a.clear_pin(self.gw, "nobody")
		a.clear_triage_pending(self.gw, "nobody")
		self.assertEqual(self._count("nobody"), 0)

	def test_set_and_get_pin(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", ttl_hours=2, now=self.now)
		pin = a.get_pin(self.gw, "c1", now=self.now)
		self.assertEqual(pin["solution"], self.s1)
		self.assertEqual(pin["set_by"], "rule")
		self.assertAlmostEqual((pin["expires_at"] - self.now).total_seconds(), 7200, delta=1)
		self.assertEqual(a.current_solution(self.gw, "c1", now=self.now), self.s1)

	def test_upsert_keeps_single_row_and_idempotent(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", now=self.now)
		a.set_pin(self.gw, "c1", self.s1, "rule", now=self.now)
		a.set_pin(self.gw, "c1", self.s2, "handoff", now=self.now)
		self.assertEqual(self._count(), 1)
		pin = a.get_pin(self.gw, "c1", now=self.now)
		self.assertEqual((pin["solution"], pin["set_by"]), (self.s2, "handoff"))

	def test_expired_pin_none_but_row_stays(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", ttl_hours=1, now=self.now)
		later = self.now + timedelta(hours=2)
		self.assertIsNone(a.get_pin(self.gw, "c1", now=later))
		self.assertIsNone(a.current_solution(self.gw, "c1", now=later))
		self.assertEqual(self._count(), 1)

	def test_unique_per_gateway_contact(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", now=self.now)
		dup = frappe.get_doc(
			{"doctype": "Conversation Assignment", "gateway": self.gw, "contact": "c1", "solution": self.s2}
		)
		with self.assertRaises(frappe.UniqueValidationError):
			dup.insert(ignore_permissions=True)

	def test_triage_pending_roundtrip(self):
		until = self.now + timedelta(minutes=30)
		a.mark_triage_pending(self.gw, "c1", until)
		a.mark_triage_pending(self.gw, "c1", until)
		self.assertEqual(self._count(), 1)
		self.assertIsNotNone(a.get_triage_pending(self.gw, "c1", now=self.now))
		self.assertIsNone(a.get_pin(self.gw, "c1", now=self.now))
		a.clear_triage_pending(self.gw, "c1")
		a.clear_triage_pending(self.gw, "c1")
		self.assertIsNone(a.get_triage_pending(self.gw, "c1", now=self.now))

	def test_set_pin_clears_pending_and_pending_on_existing_pin(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", now=self.now)
		a.mark_triage_pending(self.gw, "c1", self.now + timedelta(minutes=30))
		self.assertIsNotNone(a.get_pin(self.gw, "c1", now=self.now)["triage_pending_until"])
		a.set_pin(self.gw, "c1", self.s2, "triage", now=self.now)
		self.assertIsNone(a.get_triage_pending(self.gw, "c1", now=self.now))

	def test_clear_pin_keeps_row(self):
		a.set_pin(self.gw, "c1", self.s1, "rule", now=self.now)
		a.clear_pin(self.gw, "c1")
		a.clear_pin(self.gw, "c1")
		self.assertIsNone(a.current_solution(self.gw, "c1", now=self.now))
		self.assertEqual(self._count(), 1)
