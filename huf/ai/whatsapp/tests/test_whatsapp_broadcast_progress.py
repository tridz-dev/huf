# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Realtime progress events: document room, throttle, force, never raises."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.whatsapp.broadcast import progress as pg

ROW = {"status": "Running", "total": 10, "queued": 4, "sending": 0, "sent": 3, "delivered": 2, "read": 0, "failed": 1,
	"deferred": 0, "unknown": 0, "skipped": 0, "pause_reason": None}


class TestProgress(unittest.TestCase):
	def setUp(self):
		p = patch.object(pg, "frappe")
		self.frappe = p.start()
		self.addCleanup(p.stop)
		self.frappe.local.site = "s"
		self.cache = MagicMock()
		self.cache.get.return_value = None
		self.frappe.cache.return_value = self.cache
		self.frappe.db.get_value.return_value = dict(ROW)

	def test_publishes_to_the_document_room(self):
		self.assertTrue(pg.publish("B1"))
		args, kwargs = self.frappe.publish_realtime.call_args
		self.assertEqual(args[0], "wa_broadcast_progress")
		self.assertEqual(args[1]["broadcast"], "B1")
		self.assertEqual(args[1]["sent"], 3)
		self.assertEqual((kwargs["doctype"], kwargs["docname"], kwargs["after_commit"]), ("WhatsApp Broadcast", "B1", True))

	def test_throttled_unless_forced(self):
		with patch.object(pg.time, "time", return_value=100.0):
			self.cache.get.return_value = 99.0
			self.assertFalse(pg.publish("B1"))
			self.frappe.publish_realtime.assert_not_called()
			self.assertTrue(pg.publish("B1", force=True))
		self.cache.get.return_value = 90.0
		with patch.object(pg.time, "time", return_value=100.0):
			self.assertTrue(pg.publish("B1"))

	def test_missing_broadcast_or_errors_never_raise(self):
		self.frappe.db.get_value.return_value = None
		self.assertFalse(pg.publish("B1"))
		self.frappe.publish_realtime.side_effect = RuntimeError("redis down")
		self.frappe.db.get_value.return_value = dict(ROW)
		self.assertFalse(pg.publish("B1", force=True))


if __name__ == "__main__":
	unittest.main()
