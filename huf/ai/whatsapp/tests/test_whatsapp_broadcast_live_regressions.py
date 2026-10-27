# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-J: regressions found by the live API run (bugs 2, 3, 4). Graph/network is never touched."""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.whatsapp import account_events as ae
from huf.ai.whatsapp.broadcast import send as bs
from huf.ai.whatsapp.broadcast import api as mgmt

GW = "GW-LIVEREG-TEST"
B, R = "WhatsApp Broadcast", "WhatsApp Broadcast Recipient"


class TestFallbackTimestamp(unittest.TestCase):
	def test_missing_meta_timestamp_is_utc_epoch(self):
		captured = {}
		doc = MagicMock()

		def fake_get_doc(d):
			captured.update(d)
			return doc

		with patch.object(frappe, "get_doc", side_effect=fake_get_doc), patch.object(frappe.db, "exists", return_value=False):
			ae._insert_consent("GW", "919000000001", "marketing_messages", "stop", "x", None)
		self.assertLess(abs(captured["meta_timestamp"] - time.time()), 5)

	def test_naive_site_time_is_not_used(self):
		# a site timezone far from UTC must not skew the fallback
		fake_now = MagicMock()
		fake_now.timestamp.return_value = time.time() + 19800
		with patch.object(frappe, "get_doc", return_value=MagicMock()) as gd, \
			patch.object(frappe.db, "exists", return_value=False), \
			patch.object(frappe.utils, "now_datetime", return_value=fake_now):
			ae._insert_consent("GW", "919000000001", "marketing_messages", "stop", "x", None)
		self.assertLess(abs(gd.call_args[0][0]["meta_timestamp"] - time.time()), 5)


class TestDeleteGuards(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		frappe.flags.in_broadcast_api = False
		self.addCleanup(lambda: setattr(frappe.flags, "in_broadcast_api", False))

	def _clean(self):
		names = frappe.get_all(B, filters={"gateway": GW}, pluck="name")
		if names:
			frappe.db.delete(R, {"broadcast": ["in", names]})
			frappe.db.delete(B, {"name": ["in", names]})
		frappe.db.commit()

	def _make(self, status="Draft", rows=(("queued", "1"),)):
		frappe.flags.in_broadcast_api = True
		try:
			d = frappe.get_doc({"doctype": B, "title": "t", "gateway": GW, "status": status, "template": "tpl",
								"template_name": "tpl", "whatsapp_account": "ACC"})
			d.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
			names = []
			for st, rec in rows:
				r = frappe.get_doc({"doctype": R, "broadcast": d.name, "recipient": "91900000000" + rec, "status": st})
				r.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
				names.append(r.name)
		finally:
			frappe.flags.in_broadcast_api = False
		return d.name, names

	def test_recipient_delete_without_flag_rejected(self):
		_, names = self._make()
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(R, names[0], ignore_permissions=True)
		self.assertTrue(frappe.db.exists(R, names[0]))

	def test_recipient_delete_when_not_draft_rejected_even_with_flag(self):
		_, names = self._make(status="Running", rows=(("sent", "1"),))
		frappe.flags.in_broadcast_api = True
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(R, names[0], ignore_permissions=True)
		self.assertTrue(frappe.db.exists(R, names[0]))

	def test_broadcast_delete_non_draft_rejected(self):
		for status in ("Running", "Paused", "Completed", "Cancelled"):
			with self.subTest(status=status):
				name, names = self._make(status=status, rows=(("queued", "2"),))
				with self.assertRaises(frappe.PermissionError):
					frappe.delete_doc(B, name, ignore_permissions=True)
				self.assertTrue(frappe.db.exists(B, name))
				self.assertTrue(frappe.db.exists(R, names[0]))

	def test_broadcast_delete_draft_with_sent_rows_rejected(self):
		name, names = self._make(rows=(("sent", "3"), ("queued", "4")))
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(B, name, ignore_permissions=True)
		self.assertTrue(frappe.db.exists(B, name))
		self.assertEqual(len(frappe.get_all(R, filters={"broadcast": name})), 2)

	def test_draft_delete_cascades_recipients(self):
		name, names = self._make(rows=(("queued", "5"), ("skipped", "6")))
		frappe.delete_doc(B, name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists(B, name))
		self.assertFalse(frappe.db.exists(R, names[0]))
		self.assertFalse(frappe.db.exists(R, names[1]))
		self.assertFalse(frappe.flags.in_broadcast_api)


class TestDeadlocks(unittest.TestCase):
	def test_claim_deadlock_returns_lost_claim_and_never_posts(self):
		with patch.object(bs, "_load", return_value={"status": "queued", "broadcast": "B"}), \
			patch.object(bs.frappe.db, "sql", side_effect=frappe.QueryDeadlockError("1020")), \
			patch.object(bs.frappe.db, "rollback") as rb, \
			patch.object(bs, "_load_broadcast") as lb:
			self.assertEqual(bs.send_one("ROW-1"), "lost_claim")
		rb.assert_called()
		lb.assert_not_called()  # never got past the claim, so no POST path

	def _call(self, side_effect):
		row = {"status": "Draft", "consent_attested": 0}
		with patch.object(mgmt, "_require_broadcast_write", return_value=row), \
			patch.object(mgmt, "_broadcast_audit"), \
			patch.object(mgmt.time, "sleep") as sl, \
			patch.object(frappe.db, "rollback") as rb, \
			patch("huf.ai.whatsapp.broadcast.recipients.prepare", side_effect=side_effect) as prep:
			out = mgmt.add_broadcast_recipients.__wrapped__("B", ["919000000001"]) if hasattr(
				mgmt.add_broadcast_recipients, "__wrapped__") else mgmt.add_broadcast_recipients("B", ["919000000001"])
		return out, prep, sl, rb

	def test_add_retries_then_succeeds(self):
		out, prep, sl, rb = self._call([frappe.QueryDeadlockError("1213"), {"added": 1, "skipped_total": 0, "invalid_total": 0}])
		self.assertTrue(out.get("success"), out)
		self.assertEqual(prep.call_count, 2)
		self.assertEqual(rb.call_count, 1)

	def test_add_gives_up_with_busy_retry(self):
		out, prep, sl, rb = self._call(frappe.QueryDeadlockError("1213"))
		self.assertEqual(out.get("error"), "busy_retry")
		self.assertEqual(prep.call_count, 3)
		self.assertFalse(frappe.flags.in_broadcast_api)
