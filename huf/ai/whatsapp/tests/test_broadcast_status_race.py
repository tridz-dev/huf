# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-STATUS-RACE: statuses that arrive before the sender commits the wamid are parked and applied later."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from huf.ai.whatsapp.broadcast import status as bs

BC = "WhatsApp Broadcast"
RC = "WhatsApp Broadcast Recipient"
PD = bs.PENDING
B = "ZZRACE-BC"
GW = "GW-RACE"
TS = 1761800000


def hook(wamid, status, ts=TS, gateway=GW, **extra):
	bs.apply_from_webhook({"id": wamid, "status": status, "timestamp": str(ts), **extra}, gateway)


class TestStatusRace(FrappeTestCase):
	def setUp(self):
		self.addCleanup(self._cleanup)
		self._cleanup()
		frappe.db.sql(f"insert into `tab{BC}` (name, gateway, status, template, creation, modified) values (%s, %s, 'Running', 'tpl', now(), now())", (B, GW))
		self._row("ZZRACE-R1", "sending")

	def _cleanup(self):
		frappe.db.rollback()
		frappe.db.delete(RC, {"broadcast": B})
		frappe.db.delete(BC, {"name": B})
		frappe.db.delete(PD, {"wamid": ["like", "wamid.race%"]})
		frappe.db.commit()

	def _row(self, name, status, wamid=None):
		frappe.db.sql(
			f"insert into `tab{RC}` (name, broadcast, recipient, status, wamid, attempts, creation, modified) values (%s, %s, '15550009999', %s, %s, 1, now(), now())",
			(name, B, status, wamid),
		)

	def _commit_wamid(self, wamid, status="sent"):
		"""What the sender's _write does: status sent + wamid + sent_at (site-local)."""
		frappe.db.sql(f"update `tab{RC}` set status=%s, wamid=%s, sent_at=%s where name='ZZRACE-R1'", (status, wamid, now_datetime()))

	def _st(self):
		return frappe.db.get_value(RC, "ZZRACE-R1", "status")

	def _pending(self, wamid):
		return frappe.get_all(PD, filters={"wamid": wamid}, fields=["status", "gateway"])

	def test_status_before_commit_is_parked_then_applied(self):
		hook("wamid.race.1", "delivered")
		hook("wamid.race.1", "read", TS + 5)
		self.assertEqual({p.status for p in self._pending("wamid.race.1")}, {"delivered", "read"})
		self.assertEqual(self._st(), "sending")
		self._commit_wamid("wamid.race.1")
		self.assertEqual(bs.apply_pending("wamid.race.1"), 2)
		self.assertEqual(self._st(), "read")
		self.assertEqual(self._pending("wamid.race.1"), [])
		counts = {k: int(frappe.db.get_value(BC, B, k) or 0) for k in ("sent", "delivered", "read")}
		self.assertEqual(counts["read"], 1)

	def test_send_path_applies_parked(self):
		from huf.ai.whatsapp.broadcast import send

		hook("wamid.race.2", "delivered")
		self._commit_wamid("wamid.race.2")
		frappe.db.commit()
		send._apply_parked("wamid.race.2")
		self.assertEqual(self._st(), "delivered")
		self.assertEqual(self._pending("wamid.race.2"), [])

	def test_duplicate_and_old_statuses_do_not_downgrade(self):
		hook("wamid.race.3", "delivered")
		hook("wamid.race.3", "delivered")
		self.assertEqual(len(self._pending("wamid.race.3")), 1, "same (wamid,status) parks once")
		self._commit_wamid("wamid.race.3")
		bs.apply_pending("wamid.race.3")
		self.assertEqual(self._st(), "delivered")
		hook("wamid.race.3", "sent")  # late, older status: row exists -> no-op, not parked
		hook("wamid.race.3", "delivered")
		self.assertEqual(self._st(), "delivered")
		self.assertEqual(self._pending("wamid.race.3"), [])
		# read arrives parked-late after delivered applied: still moves forward only
		hook("wamid.race.3", "read")
		hook("wamid.race.3", "delivered")
		self.assertEqual(self._st(), "read")

	def test_parked_read_does_not_get_downgraded_by_parked_sent(self):
		hook("wamid.race.4", "read")
		hook("wamid.race.4", "sent")
		self._commit_wamid("wamid.race.4")
		bs.apply_pending("wamid.race.4")
		self.assertEqual(self._st(), "read")

	def test_expiry_sweep(self):
		hook("wamid.race.5", "delivered")
		old = frappe.get_all(PD, filters={"wamid": "wamid.race.5"}, pluck="name")[0]
		frappe.db.set_value(PD, old, "received_at", now_datetime() - timedelta(hours=25))
		hook("wamid.race.6", "delivered")
		bs.sweep_pending()
		self.assertEqual(self._pending("wamid.race.5"), [], "expired")
		kept = self._pending("wamid.race.6")
		self.assertEqual(len(kept), 1, "fresh one stays")
		self.assertEqual(frappe.db.get_value(PD, {"wamid": "wamid.race.6"}, "attempts"), 1)
		self.assertEqual(self._st(), "sending")

	def test_sweep_applies_once_wamid_exists(self):
		hook("wamid.race.7", "read")
		self._commit_wamid("wamid.race.7")
		bs.sweep_pending()
		self.assertEqual(self._st(), "read")

	def test_other_gateway_wamid_stays_ignored(self):
		self._commit_wamid("wamid.race.8")
		hook("wamid.race.8", "delivered", gateway="GW-OTHER")
		self.assertEqual(self._st(), "sent")
		self.assertEqual(self._pending("wamid.race.8"), [], "a row exists for another gateway: never parked")
		# unknown wamid on a gateway with no live broadcast is not parked either
		hook("wamid.race.9", "delivered", gateway="GW-QUIET")
		self.assertEqual(self._pending("wamid.race.9"), [])
		# and a parked status of GW-OTHER never applies to GW's row
		with patch.object(bs, "_broadcast_active", return_value=True):
			hook("wamid.race.10", "read", gateway="GW-OTHER")
		self._commit_wamid("wamid.race.10")
		bs.apply_pending("wamid.race.10")
		self.assertEqual(self._st(), "sent")

	def test_webhook_time_columns_use_site_timezone(self):
		self._commit_wamid("wamid.race.11")
		from datetime import datetime, timezone

		ts = int(datetime.now(timezone.utc).timestamp())
		hook("wamid.race.11", "delivered", ts)
		row = frappe.db.get_value(RC, "ZZRACE-R1", ["sent_at", "delivered_at"], as_dict=True)
		self.assertLess(abs((row.delivered_at - row.sent_at).total_seconds()), 300, "columns agree (same tz)")
		self.assertLess(abs((row.delivered_at - now_datetime()).total_seconds()), 300)
		self.assertEqual(bs._when(ts), bs._when(str(ts)))
