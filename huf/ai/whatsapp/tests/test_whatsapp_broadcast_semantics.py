# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-G: send/status semantics on the real DB (M1 131050, M2 131049, fast-webhook race, unknown -> sent)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp import account_events
from huf.ai.whatsapp import broadcast_send as send
from huf.ai.whatsapp import broadcast_status as bs
from huf.ai.whatsapp import outbound_policy as policy

BC = "WhatsApp Broadcast"
RC = "WhatsApp Broadcast Recipient"
B = "ZZFIXG-BC"


class TestSemantics(FrappeTestCase):
	def setUp(self):
		self.rows = []
		self.addCleanup(self._cleanup)
		frappe.db.sql(
			f"insert into `tab{BC}` (name, gateway, status, template, creation, modified) values (%s, 'GW-G', 'Running', 'tpl', now(), now())", B
		)

	def _cleanup(self):
		frappe.db.rollback()
		for r in self.rows:
			frappe.db.delete(RC, {"name": r})
		frappe.db.delete(BC, {"name": B})
		frappe.db.commit()

	def _row(self, name, status, wamid=None, recipient="15550007777"):
		frappe.db.sql(
			f"insert into `tab{RC}` (name, broadcast, recipient, status, wamid, opaque_ref, attempts, creation, modified) "
			"values (%s, %s, %s, %s, %s, %s, 0, now(), now())",
			(name, B, recipient, status, wamid, name),
		)
		self.rows.append(name)
		return name

	def _get(self, name, *f):
		return frappe.db.get_value(RC, name, list(f), as_dict=True)

	def _send(self, name, post):
		with (
			patch.object(send, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}),
			patch.object(policy, "check_recipient", return_value=None),
			patch.object(bridge, "send_template", side_effect=post),
		):
			return send.send_one(name)

	# M1
	def test_131050_status_records_marketing_stop(self):
		self._row("ZZFIXG-R1", "sent", wamid="wamid.g1")
		self._row("ZZFIXG-R2", "queued")  # same contact, another pending row
		with patch.object(account_events, "record_user_preferences") as rec:
			self.assertTrue(bs.apply_status("wamid.g1", "failed", 1, [{"code": 131050, "title": "stopped"}], None, gateway="GW-G"))
		rec.assert_called_once_with("GW-G", [{"category": account_events.MARKETING, "value": "stop", "wa_id": "15550007777", "detail": "131050"}])
		self.assertEqual(self._get("ZZFIXG-R1", "status").status, "failed")

	def test_131050_real_stop_skips_other_pending_rows(self):
		self._row("ZZFIXG-R1", "sent", wamid="wamid.g1")
		self._row("ZZFIXG-R2", "queued")
		# the real consent insert needs a Gateway row; the helper's row-skipping half is what we verify here
		with patch.object(account_events, "_insert_consent", return_value=True):
			bs.apply_status("wamid.g1", "failed", 1, [{"code": 131050}], None, gateway="GW-G")
		r2 = self._get("ZZFIXG-R2", "status", "skip_reason")
		self.assertEqual((r2.status, r2.skip_reason), ("skipped", "opted_out"))

	# M2
	def test_131049_send_is_skipped_and_never_resent(self):
		self._row("ZZFIXG-R1", "queued")
		err = bridge.BridgeError({"success": False, "error": "send_failed", "graph_code": 131049, "message": "limit"})
		calls = []
		self.assertEqual(self._send("ZZFIXG-R1", err), "skipped")
		r = self._get("ZZFIXG-R1", "status", "skip_reason", "error_code", "next_attempt_at")
		self.assertEqual((r.status, r.skip_reason, int(r.error_code), r.next_attempt_at), ("skipped", "per_user_marketing_limit", 131049, None))
		self.assertEqual(self._send("ZZFIXG-R1", lambda *a, **k: calls.append(1) or {"wamid": "x"}), "lost_claim")
		self.assertEqual(calls, [])

	def test_131049_status_failure_is_skipped_with_reason(self):
		self._row("ZZFIXG-R1", "sent", wamid="wamid.g1")
		self.assertTrue(bs.apply_status("wamid.g1", "failed", 1, [{"code": 131049, "title": "limit"}], None, gateway="GW-G"))
		r = self._get("ZZFIXG-R1", "status", "skip_reason", "error_code")
		self.assertEqual((r.status, r.skip_reason, int(r.error_code)), ("skipped", "per_user_marketing_limit", 131049))
		self.assertFalse(bs.apply_status("wamid.g1", "delivered", 1, None, None, gateway="GW-G"))

	def test_131049_status_does_not_touch_delivered(self):
		self._row("ZZFIXG-R1", "delivered", wamid="wamid.g1")
		self.assertFalse(bs.apply_status("wamid.g1", "failed", 1, [{"code": 131049}], None, gateway="GW-G"))
		self.assertEqual(self._get("ZZFIXG-R1", "status").status, "delivered")

	# L1
	def test_webhook_before_runner_write_keeps_held_status_and_persists_wamid(self):
		self._row("ZZFIXG-R1", "queued")

		def post(*a, **k):
			# the delivered webhook lands (matched by opaque_ref) while the runner still holds `sending`
			self.assertTrue(bs.apply_status(None, "delivered", 5, None, "ZZFIXG-R1", gateway="GW-G"))
			frappe.db.commit()
			return {"wamid": "wamid.race", "message_status": "accepted"}

		self.assertEqual(self._send("ZZFIXG-R1", post), "sent")
		r = self._get("ZZFIXG-R1", "status", "wamid", "message_status", "sent_at")
		self.assertEqual((r.status, r.wamid, r.message_status), ("delivered", "wamid.race", "accepted"))
		self.assertIsNotNone(r.sent_at)

	def test_race_does_not_overwrite_a_different_existing_wamid(self):
		self._row("ZZFIXG-R1", "queued")

		def post(*a, **k):
			bs.apply_status("wamid.first", "sent", 5, None, "ZZFIXG-R1", gateway="GW-G")
			frappe.db.commit()
			return {"wamid": "wamid.first", "message_status": "accepted"}

		self._send("ZZFIXG-R1", post)
		self.assertEqual(self._get("ZZFIXG-R1", "wamid", "status").wamid, "wamid.first")

	# live-test regression: a successful send must be recorded as `sent` on the real DB. error_code is an Int NOT NULL
	# column, so writing None used to raise 1048 and every successful send ended up `unknown`.
	def test_successful_send_is_recorded_as_sent_with_real_columns(self):
		self._row("ZZFIXG-R1", "queued")
		out = self._send("ZZFIXG-R1", lambda *a, **k: {"wamid": "wamid.ok", "message_status": "accepted"})
		self.assertEqual(out, "sent")
		r = self._get("ZZFIXG-R1", "status", "wamid", "message_status", "sent_at", "error_code")
		self.assertEqual((r.status, r.wamid, r.message_status, r.error_code), ("sent", "wamid.ok", "accepted", 0))
		self.assertIsNotNone(r.sent_at)

	def test_failed_status_without_an_error_code_does_not_violate_not_null(self):
		self._row("ZZFIXG-R1", "sent", wamid="wamid.nc")
		self.assertTrue(bs.apply_status("wamid.nc", "failed", 5, [{"title": "no code"}], None, gateway="GW-G"))
		r = self._get("ZZFIXG-R1", "status", "error_code")
		self.assertEqual((r.status, r.error_code), ("failed", 0))

	# unknown -> sent
	def test_sent_webhook_resolves_unknown_without_enabling_resend(self):
		self._row("ZZFIXG-R1", "unknown", wamid="wamid.u")
		self.assertTrue(bs.apply_status("wamid.u", "sent", 5, None, None, gateway="GW-G"))
		self.assertEqual(self._get("ZZFIXG-R1", "status").status, "sent")
		self.assertFalse(send._claim("ZZFIXG-R1"))  # neither unknown nor sent is claimable
		self.assertEqual(self._get("ZZFIXG-R1", "status").status, "sent")

	def test_unknown_is_never_claimable(self):
		self._row("ZZFIXG-R1", "unknown")
		self.assertFalse(send._claim("ZZFIXG-R1"))

	# M6 (bridge owned): any exception after the POST attempt is unknown
	def test_exception_from_send_template_is_unknown(self):
		self._row("ZZFIXG-R1", "queued")
		self.assertEqual(self._send("ZZFIXG-R1", RuntimeError("after post")), "unknown")
		self.assertEqual(self._get("ZZFIXG-R1", "status").status, "unknown")
