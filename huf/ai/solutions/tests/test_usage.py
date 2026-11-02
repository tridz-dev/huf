import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe

from huf.ai.solutions import usage

GW = "GW-USAGE"
NOW = datetime(2026, 10, 24, 12, 0, 0)


def _key(solution, claimed_at, status="Sent", gateway=GW):
	doc = frappe.get_doc({
		"doctype": "WhatsApp Send Key", "key_hash": frappe.generate_hash(length=40), "gateway": gateway,
		"status": status, "claimed_at": claimed_at, "solution": solution or None,
	})
	doc.insert(ignore_permissions=True, ignore_links=True)
	return doc


class TestUsage(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)

	def _clean(self):
		for gateway in (GW, GW + "-2"):
			frappe.db.delete("WhatsApp Send Key", {"gateway": gateway})
		frappe.db.commit()

	def test_grouping_and_unassigned_bucket(self):
		for _ in range(3):
			_key("sol-a", NOW - timedelta(hours=1))
		_key("sol-b", NOW - timedelta(hours=2))
		_key("", NOW - timedelta(hours=2))
		_key("sol-a", NOW - timedelta(hours=1), gateway=GW + "-2")
		self.assertEqual(usage.sends_24h_by_solution(GW, now=NOW), {"sol-a": 3, "sol-b": 1, "": 1})

	def test_window_boundaries(self):
		_key("sol-a", NOW - timedelta(hours=24))  # exactly on the edge: inside
		_key("sol-a", NOW - timedelta(hours=24, seconds=1))  # outside
		_key("sol-a", NOW + timedelta(seconds=0))  # now: inside
		self.assertEqual(usage.sends_24h_by_solution(GW, now=NOW), {"sol-a": 2})

	def test_failed_or_other_statuses_do_not_count(self):
		_key("sol-a", NOW - timedelta(hours=1), status="Pending")
		_key("sol-a", NOW - timedelta(hours=1), status="Sent")
		self.assertEqual(usage.sends_24h_by_solution(GW, now=NOW), {"sol-a": 2})

	def test_empty(self):
		self.assertEqual(usage.sends_24h_by_solution(GW, now=NOW), {})
		self.assertEqual(usage.sends_24h_by_solution("", now=NOW), {})

	def test_usage_pct(self):
		for _ in range(5):
			_key("sol-a", NOW - timedelta(hours=1))
		with patch.object(usage, "_now", return_value=NOW), patch.object(usage, "ceiling_for_gateway", return_value=(200, "gateway_cap")):
			self.assertEqual(usage.usage_pct("sol-a", GW), 2.5)
			self.assertEqual(usage.usage_pct("sol-none", GW), 0.0)
		with patch.object(usage, "_now", return_value=NOW), patch.object(usage, "ceiling_for_gateway", return_value=(None, "none")):
			self.assertIsNone(usage.usage_pct("sol-a", GW))

	def test_blame_largest_share(self):
		for _ in range(3):
			_key("sol-a", NOW - timedelta(hours=1))
		_key("sol-b", NOW - timedelta(hours=1))
		self.assertEqual(usage.blame(GW, now=NOW), {"solution": "sol-a", "share_pct": 75.0})

	def test_blame_share_includes_unassigned_in_total(self):
		_key("sol-a", NOW - timedelta(hours=1))
		_key("", NOW - timedelta(hours=1))
		_key("", NOW - timedelta(hours=1))
		_key("", NOW - timedelta(hours=1))
		self.assertEqual(usage.blame(GW, now=NOW), {"solution": "sol-a", "share_pct": 25.0})

	def test_blame_tie_is_deterministic_by_name(self):
		_key("sol-b", NOW - timedelta(hours=1))
		_key("sol-a", NOW - timedelta(hours=1))
		self.assertEqual(usage.blame(GW, now=NOW), {"solution": "sol-a", "share_pct": 50.0})

	def test_blame_none_when_empty_or_only_unassigned(self):
		self.assertIsNone(usage.blame(GW, now=NOW))
		_key("", NOW - timedelta(hours=1))
		self.assertIsNone(usage.blame(GW, now=NOW))
