# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-C: gateway-scoped status matching (M2), atomic counter deltas (C5), RR-stale update (C6).

Runs against the real DB. Tests use throwaway doc names and clean up after themselves.
"""

from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.whatsapp.broadcast import status as bs

BC = "WhatsApp Broadcast"
RC = "WhatsApp Broadcast Recipient"
COUNTERS = bs._COUNTED


class TestStatusFixes(FrappeTestCase):
	def setUp(self):
		self.bcs, self.rows = [], []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.rollback()
		for r in self.rows:
			frappe.db.delete(RC, {"name": r})
		for b in self.bcs:
			frappe.db.delete(BC, {"name": b})
		frappe.db.commit()

	def _bc(self, name, gateway):
		frappe.db.sql(f"insert into `tab{BC}` (name, gateway, status, creation, modified) values (%s, %s, 'Running', now(), now())", (name, gateway))
		self.bcs.append(name)
		return name

	def _row(self, name, bc, status, wamid=None):
		frappe.db.sql(
			f"insert into `tab{RC}` (name, broadcast, recipient, status, wamid, creation, modified) values (%s, %s, %s, %s, %s, now(), now())",
			(name, bc, "15550001111", status, wamid),
		)
		self.rows.append(name)
		return name

	def _counters(self, bc):
		return {k: int(frappe.db.get_value(BC, bc, k) or 0) for k in COUNTERS}

	def test_cross_gateway_forged_status_ignored(self):
		bc = self._bc("ZZFIXC-BC-A", "GW-A")
		self._row("ZZFIXC-R-A1", bc, "sent", wamid="wamid.fixc.a1")
		# GW-B forges an opaque_ref and a wamid pointing at GW-A's row
		self.assertFalse(bs.apply_status(None, "failed", 1, [{"code": 135000}], "ZZFIXC-R-A1", gateway="GW-B"))
		self.assertFalse(bs.apply_status("wamid.fixc.a1", "read", 1, None, None, gateway="GW-B"))
		self.assertEqual(frappe.db.get_value(RC, "ZZFIXC-R-A1", "status"), "sent")
		self.assertTrue(bs.apply_status("wamid.fixc.a1", "delivered", 1, None, None, gateway="GW-A"))
		self.assertEqual(frappe.db.get_value(RC, "ZZFIXC-R-A1", "status"), "delivered")

	def test_counters_after_transitions_equal_recount(self):
		bc = self._bc("ZZFIXC-BC-B", "GW-A")
		for i in range(4):
			self._row(f"ZZFIXC-R-B{i}", bc, "sent", wamid=f"wamid.fixc.b{i}")
		self._row("ZZFIXC-R-B4", bc, "sending")
		frappe.get_doc(BC, bc).recount()
		seq = [("wamid.fixc.b0", "delivered"), ("wamid.fixc.b0", "read"), ("wamid.fixc.b1", "read"), ("wamid.fixc.b1", "delivered"),
			("wamid.fixc.b2", "failed"), ("wamid.fixc.b2", "failed"), ("wamid.fixc.b3", "delivered"), (None, "sent")]
		for wamid, st in seq:
			bs.apply_status(wamid, st, 1, [{"code": 131047}], "ZZFIXC-R-B4" if wamid is None else None, gateway="GW-A")
		delta = self._counters(bc)
		frappe.get_doc(BC, bc).recount()
		self.assertEqual(delta, self._counters(bc))
		self.assertEqual((delta["read"], delta["delivered"], delta["failed"], delta["sent"]), (2, 1, 1, 1))

	def test_no_recount_on_hot_path(self):
		bc = self._bc("ZZFIXC-BC-C", "GW-A")
		self._row("ZZFIXC-R-C0", bc, "sent", wamid="wamid.fixc.c0")
		from unittest.mock import patch

		with patch.object(bs, "_recount") as rc:
			self.assertTrue(bs.apply_status("wamid.fixc.c0", "delivered", 1, None, None, gateway="GW-A"))
		rc.assert_not_called()

	def test_stale_snapshot_status_not_dropped(self):
		bc = self._bc("ZZFIXC-BC-D", "GW-A")
		self._row("ZZFIXC-R-D0", bc, "sending")
		real = bs._find_row

		def stale_find(*a, **k):
			row = real(*a, **k)
			# another transaction advanced the row after our snapshot read
			frappe.db.sql(f"update `tab{RC}` set status='sent' where name='ZZFIXC-R-D0'")
			return row  # still says 'sending'

		from unittest.mock import patch

		with patch.object(bs, "_find_row", stale_find):
			self.assertTrue(bs.apply_status("wamid.fixc.d0", "delivered", 1, None, "ZZFIXC-R-D0", gateway="GW-A"))
		self.assertEqual(frappe.db.get_value(RC, "ZZFIXC-R-D0", "status"), "delivered")
