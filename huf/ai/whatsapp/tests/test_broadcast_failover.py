# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""HUFCRM-04b: cross-channel failover from a failed WhatsApp broadcast row."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.whatsapp.broadcast import failover
from huf.ai.whatsapp.broadcast import status as bs

BC = "WhatsApp Broadcast"
RC = "WhatsApp Broadcast Recipient"
B = "ZZFO-BC"
GW = "GW-FO"
R = "ZZFO-R1"
TS = 1761800000
UNDELIVERABLE = [{"code": 131026, "title": "Undeliverable"}]


def _consent(allowed=("sms", "email")):
	return lambda ch, to, purpose="marketing": (True, "ok") if ch in allowed else (False, "no_opt_in")


class TestFailover(FrappeTestCase):
	def setUp(self):
		self.addCleanup(self._cleanup)
		self._cleanup()
		frappe.db.sql(f"insert into `tab{BC}` (name, gateway, status, template, creation, modified) values (%s, %s, 'Running', 'tpl', now(), now())", (B, GW))
		self.sms = MagicMock(return_value={"ok": True, "id": "SM1", "status": "queued", "error": None})
		self.email = MagicMock(return_value={"ok": True, "id": "COM1", "status": "sent", "error": None})
		self.senders = {"sms": self.sms, "email": self.email}

	def _cleanup(self):
		frappe.db.rollback()
		frappe.db.delete(RC, {"broadcast": B})
		frappe.db.delete(BC, {"name": B})
		frappe.db.commit()

	def _row(self, channels='["sms","email"]', body="Fallback text", kind="", status="sent", email="a@example.com"):
		frappe.db.sql(
			f"insert into `tab{RC}` (name, broadcast, recipient, status, wamid, attempts, fallback_channels, fallback_body, fallback_body_kind, fallback_email, creation, modified)"
			" values (%s, %s, '15550009999', %s, 'wamid.fo1', 1, %s, %s, %s, %s, now(), now())",
			(R, B, status, channels, body, kind, email),
		)

	def _fail(self, errors=UNDELIVERABLE, status="failed", allowed=("sms", "email")):
		"""Apply the webhook status (enqueue patched), then run each queued job directly like a worker would."""
		with patch("frappe.enqueue") as enq:
			applied = bs.apply_status("wamid.fo1", status, TS, errors, gateway=GW)
		frappe.db.commit()  # enqueue_after_commit: the worker only ever sees committed rows (it rolls back on early exit)
		with patch("huf.ai.channels.channel_consent.has_consent", _consent(allowed)), patch.dict(failover.__dict__, {"_send_sms": self.sms, "_send_email": self.email}):
			for call in enq.call_args_list:
				failover.run_failover_job(call.kwargs["recipient_name"])
		self.enqueued = enq
		return applied

	def _doc(self):
		d = frappe.db.get_value(RC, R, ["status", "channel_delivered", "fallback_attempts"], as_dict=True)
		return d, json.loads(d.fallback_attempts or "[]")

	def test_chain_sms_fails_then_email(self):
		self._row()
		self.sms.return_value = {"ok": False, "id": None, "status": "failed", "error": "boom"}
		self._fail()
		d, att = self._doc()
		self.assertEqual([(a["channel"], a["status"]) for a in att], [("sms", "failed"), ("email", "sent")])
		self.assertEqual(d.channel_delivered, "email")
		self.assertEqual(d.status, "failed")

	def test_sms_success_stops_chain(self):
		self._row()
		self._fail()
		d, att = self._doc()
		self.assertEqual(d.channel_delivered, "sms")
		self.assertEqual(len(att), 1)
		self.email.assert_not_called()

	def test_consent_skip(self):
		self._row()
		self._fail(allowed=("email",))
		d, att = self._doc()
		self.assertEqual(att[0]["status"], "skipped")
		self.assertEqual(att[0]["reason"], "no_opt_in")
		self.assertEqual(d.channel_delivered, "email")
		self.sms.assert_not_called()

	def test_duplicate_webhook_fires_once(self):
		self._row()
		self._fail()
		self.assertEqual(self.enqueued.call_count, 1)
		self._fail()
		self.assertEqual(self.enqueued.call_count, 0)  # duplicate webhook: status did not advance, nothing queued
		self.assertEqual(self.sms.call_count, 1)
		# a duplicate job is also blocked by the claim
		with patch("huf.ai.channels.channel_consent.has_consent", _consent()), patch.dict(failover.__dict__, {"_send_sms": self.sms}):
			self.assertFalse(failover.run_failover_job(R))
		self.assertEqual(self.sms.call_count, 1)

	def test_late_delivered_audited_only(self):
		self._row()
		self._fail()
		bs.apply_status("wamid.fo1", "delivered", TS + 5, gateway=GW)
		d, att = self._doc()
		self.assertEqual(d.status, "delivered")
		self.assertEqual(d.channel_delivered, "sms")
		self.assertEqual(att[-1]["status"], "delivered_late")
		self.assertEqual(self.sms.call_count, 1)
		self.email.assert_not_called()

	def test_normal_delivery_records_whatsapp(self):
		self._row()
		bs.apply_status("wamid.fo1", "delivered", TS, gateway=GW)
		self.assertEqual(self._doc()[0].channel_delivered, "whatsapp")

	def test_apply_status_does_not_commit_or_call_providers(self):
		self._row()
		with patch("frappe.enqueue") as enq, patch.object(frappe.db, "commit") as commit, patch.dict(
			failover.__dict__, {"_send_sms": self.sms, "_send_email": self.email}
		):
			bs.apply_status("wamid.fo1", "failed", TS, UNDELIVERABLE, gateway=GW)
		commit.assert_not_called()
		self.sms.assert_not_called()
		self.email.assert_not_called()
		self.assertEqual(enq.call_count, 1)
		kw = enq.call_args.kwargs
		self.assertEqual((kw["queue"], kw["enqueue_after_commit"], kw["recipient_name"]), ("short", True, R))
		self.assertTrue(kw["deduplicate"])
		self.assertEqual(self._doc()[1], [])

	def test_otp_email_refused(self):
		self._row(channels='["email"]', kind="otp")
		self._fail()
		_, att = self._doc()
		self.assertEqual(att[0]["status"], "refused")
		self.email.assert_not_called()

	def test_no_fallback_without_body(self):
		self._row(body="")
		self._fail()
		self.assertEqual(self._doc()[1], [])
		self.sms.assert_not_called()

	def test_non_retry_safe_and_user_stop_never_fail_over(self):
		self._row()
		self._fail(errors=[{"code": 131050, "title": "stop"}])
		self.assertEqual(self._doc()[1], [])
		self.sms.assert_not_called()

	def test_parse_channels(self):
		self.assertEqual(failover.parse_channels('["SMS","sms","push","email"]'), ["sms", "email"])
		self.assertEqual(failover.parse_channels("not json"), [])


class TestFailoverClaimOrder(TestFailover):
	"""The claim is committed before any provider call and replaced by the result afterwards."""

	def test_claim_visible_before_send_and_replaced_after(self):
		self._row()
		seen = {}

		def sms(gw, to, body):
			seen["during"] = json.loads(frappe.db.get_value(RC, R, "fallback_attempts") or "[]")
			return {"ok": True, "id": "SM1", "status": "queued", "error": None}

		self.sms = MagicMock(side_effect=sms)
		self.senders = {"sms": self.sms}
		self._fail()
		self.assertEqual([a["status"] for a in seen["during"]], ["attempting"])
		_d, attempts = self._doc()
		self.assertNotIn("attempting", [a["status"] for a in attempts])
		self.assertEqual(attempts[0]["channel"], "sms")

	def test_late_wa_delivered_during_attempt_is_kept(self):
		self._row()

		def sms(gw, to, body):
			failover.note_wa_delivered(R, "delivered")
			return {"ok": True, "id": "SM1", "status": "queued", "error": None}

		self.sms = MagicMock(side_effect=sms)
		self._fail()
		_d, attempts = self._doc()
		self.assertEqual([a["channel"] for a in attempts], ["sms", "whatsapp"])
