"""ux30: a run parked on a code approval whose expires_on has passed reads as lapsed (display only)."""
import unittest
from datetime import timedelta

from frappe.utils import now_datetime

from huf.ai.flow.runs.shape import approval_lapsed


class TestApprovalLapsed(unittest.TestCase):
	def _w(self, delta, approval="APR-1"):
		return {"type": "code", "approval": approval, "timeout_at": (now_datetime() + delta).isoformat()}

	def test_past_deadline_is_lapsed(self):
		self.assertTrue(approval_lapsed("Waiting Code", self._w(timedelta(hours=-1))))

	def test_future_deadline_is_not(self):
		self.assertFalse(approval_lapsed("Waiting Code", self._w(timedelta(hours=1))))

	def test_not_an_approval_wait(self):
		self.assertFalse(approval_lapsed("Waiting Code", self._w(timedelta(hours=-1), approval=None)))
		self.assertFalse(approval_lapsed("Running", self._w(timedelta(hours=-1))))
		self.assertFalse(approval_lapsed("Waiting Code", {}))
		self.assertFalse(approval_lapsed("Waiting Code", {"approval": "A", "timeout_at": "junk"}))
