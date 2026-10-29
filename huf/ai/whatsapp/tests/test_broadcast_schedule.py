# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""BE-SCHED: scheduled broadcasts (schedule/unschedule, cron start, stop flag) and retry of failed recipients."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import schedule
from huf.ai.whatsapp.broadcast.checks.start_gate import StartRefused
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import B, GW, R, USER, _Base


class TestSchedule(_Base):
	def _set(self, name, **vals):
		frappe.db.set_value(B, name, vals)
		frappe.db.commit()

	def _due(self, **over):
		name = self.make(status="Scheduled", **over)
		self._set(name, scheduled_at=add_to_date(now_datetime(), minutes=-1), scheduled_by=USER)
		return name

	def test_schedule_and_unschedule(self):
		name = self.make()
		when = add_to_date(now_datetime(), hours=2)
		out = schedule.schedule(name, when, USER)
		self.assertEqual(out["status"], "Scheduled")
		self.assertEqual(frappe.db.get_value(B, name, "scheduled_by"), USER)
		schedule.unschedule(name)
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Draft")
		self.assertIsNone(frappe.db.get_value(B, name, "scheduled_at"))

	def test_schedule_refusals(self):
		name = self.make()
		with self.assertRaises(StartRefused):
			schedule.schedule(name, add_to_date(now_datetime(), hours=-1), USER)
		with self.assertRaises(StartRefused):
			schedule.unschedule(name)  # Draft is not scheduled
		running = self.make(status="Running")
		with self.assertRaises(StartRefused):
			schedule.schedule(running, add_to_date(now_datetime(), hours=1), USER)

	def test_due_starts_through_runner(self):
		name = self._due()
		out = schedule.start_due()
		self.assertEqual(out["started"], [name])
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Running")
		self.enqueue.assert_called()

	def test_not_due_untouched(self):
		name = self.make(status="Scheduled")
		self._set(name, scheduled_at=add_to_date(now_datetime(), hours=3), scheduled_by=USER)
		self.assertEqual(schedule.start_due()["started"], [])
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Scheduled")

	def test_emergency_stop_blocks(self):
		name = self._due()
		with patch.dict(frappe.local.conf, {schedule.STOP_FLAG: 1}):
			out = schedule.start_due()
		self.assertEqual(out["started"], [])
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Scheduled")

	def test_refused_start_returns_to_draft(self):
		name = self._due(attested=0)  # consent not attested: same refusal as a manual start
		self.assertEqual(schedule.start_due()["started"], [])
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Draft")
		self.assertEqual(frappe.db.get_value(B, name, "pause_reason"), "consent_not_attested")

	def test_hold_scheduled_kill_switch(self):
		name = self._due()
		self.assertEqual(schedule.hold_scheduled(GW), [name])
		self.assertEqual(frappe.db.get_value(B, name, "status"), "Draft")

	def test_retry_skips_non_retryable(self):
		name = self.make(n=0, status="Completed")
		self.row(name, "15550009001", "failed", error_code=130429)  # rate limited: retryable
		self.row(name, "15550009005", "failed", error_code=131026)  # permanent
		self.row(name, "15550009002", "failed", error_code=0)  # policy refusal, no Graph code
		self.row(name, "15550009003", "skipped", skip_reason="opted_out")
		self.row(name, "15550009004", "unknown")
		frappe.db.commit()
		with patch("huf.ai.whatsapp.broadcast.recipients._policy_reason", return_value=None):
			out = schedule.retry_failed(name)
		self.assertEqual(out["added"], 1)
		rows = frappe.get_all(R, filters={"broadcast": out["broadcast"]}, pluck="recipient")
		self.assertEqual(rows, ["15550009001"])
		self.assertEqual(frappe.db.get_value(B, out["broadcast"], "status"), "Draft")
		self.assertEqual(frappe.db.get_value(B, out["broadcast"], "consent_attested"), 0)

	def test_is_retryable_rules(self):
		self.assertFalse(schedule.is_retryable({"status": "skipped", "error_code": 130429}))
		self.assertFalse(schedule.is_retryable({"status": "failed", "error_code": 0}))
		self.assertFalse(schedule.is_retryable({"status": "unknown", "error_code": 131000}))
		self.assertFalse(schedule.is_retryable({"status": "failed", "error_code": 131050}))  # marketing stop
		self.assertTrue(schedule.is_retryable({"status": "failed", "error_code": 130429}))
