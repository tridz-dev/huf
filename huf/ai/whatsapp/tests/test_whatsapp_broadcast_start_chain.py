# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-A2: runner.start warning acknowledgement, locked consent/one-active checks, over-budget deferral.

Real DB rows (like test_whatsapp_broadcast_runner); ``limits.preview`` is mocked to inject warnings.
"""

from __future__ import annotations

import unittest

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import runner
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import GW, GW2, USER, B, R, _Base, _preview


def _w(code, key=None):
	return {"code": code, "message": code, "limit_key": key}


class TestAcknowledgement(_Base):
	def test_unacknowledged_warning_refuses_and_reports_the_warnings(self):
		self.preview.return_value = _preview(warnings=[_w("quality_red", "quality_rating")])
		b = self.make()
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(b, USER)
		self.assertEqual(cm.exception.code, "warnings_changed")
		self.assertEqual([w["code"] for w in cm.exception.extra["warnings"]], ["quality_red"])
		self.assertEqual(self.st(b), "Draft")
		self.enqueue.assert_not_called()

	def test_matching_acknowledgement_starts(self):
		self.preview.return_value = _preview(warnings=[_w("quality_red"), _w("quality_yellow")])
		b = self.make()
		runner.start(b, USER, ["quality_yellow", "quality_red"])
		self.assertEqual(self.st(b), "Running")

	def test_new_warning_since_review_refuses(self):
		self.preview.return_value = _preview(warnings=[_w("quality_red"), _w("over_budget")])
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(self.make(), USER, ["quality_red"])
		self.assertEqual(cm.exception.code, "warnings_changed")

	def test_stale_acknowledgement_for_vanished_warning_refuses(self):
		self.preview.return_value = _preview(warnings=[])
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(self.make(), USER, ["over_budget"])
		self.assertEqual(cm.exception.code, "warnings_changed")
		self.assertEqual(cm.exception.extra["warnings"], [])

	def test_blocking_still_blocks_even_if_acknowledged(self):
		self.preview.return_value = _preview(blocking=[_w("template_not_approved")], warnings=[_w("quality_red")])
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(self.make(), USER, ["quality_red"])
		self.assertEqual(cm.exception.code, "template_not_approved")

	def test_resume_needs_no_acknowledgement(self):
		self.preview.return_value = _preview(warnings=[_w("quality_red")])
		b = self.make(status="Paused")
		runner.resume(b)
		self.assertEqual(self.st(b), "Running")


class TestLockedChecks(_Base):
	def test_consent_enforced_in_runner_even_if_preview_is_silent(self):
		b = self.make(attested=0)
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(b, USER)
		self.assertEqual(cm.exception.code, "consent_not_attested")

	def test_consent_ignored_in_preview_blocking_defers_to_runner_check(self):
		self.preview.return_value = _preview(blocking=[_w("consent_not_attested")])
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(self.make(attested=0), USER)
		self.assertEqual(cm.exception.code, "consent_not_attested")

	def test_consent_setting_off_allows_unattested_start(self):
		b = self.make(attested=0)
		with limit_override(require_consent_attestation=False):
			runner.start(b, USER)
		self.assertEqual(self.st(b), "Running")

	def test_one_active_refused_with_code(self):
		runner.start(self.make(), USER)
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(self.make(), USER)
		self.assertEqual(cm.exception.code, "another_broadcast_running")

	def test_one_active_setting_off_allows_two_running(self):
		a, b = self.make(), self.make()
		runner.start(a, USER)
		with limit_override(one_active_per_gateway=False):
			runner.start(b, USER, [])
		self.assertEqual((self.st(a), self.st(b)), ("Running", "Running"))

	def test_one_active_off_warning_must_be_acknowledged(self):
		a, b = self.make(), self.make()
		runner.start(a, USER)
		self.preview.return_value = _preview(warnings=[_w("other_broadcast_running", "one_active_per_gateway")])
		with limit_override(one_active_per_gateway=False):
			with self.assertRaises(runner.StartRefused):
				runner.start(b, USER)
			runner.start(b, USER, ["other_broadcast_running"])
		self.assertEqual(self.st(b), "Running")


class TestOverBudgetDeferral(_Base):
	def setUp(self):
		super().setUp()
		self.preview.return_value = _preview(
			queued=5, recipients=5, remaining_24h=2, within_limit=False, warnings=[_w("over_budget", "messaging_tier_24h")]
		)

	def _rows(self, b):
		return frappe.get_all(R, filters={"broadcast": b}, fields=["name", "status", "next_attempt_at"], order_by="creation, name")

	def test_rows_beyond_budget_wait_for_the_next_window_and_stay_queued(self):
		b = self.make(n=5)
		res = runner.start(b, USER, ["over_budget"])
		self.assertEqual(res["deferred_over_budget"], 3)
		rows = self._rows(b)
		self.assertEqual({r.status for r in rows}, {"queued"})
		now = now_datetime()
		held = [r for r in rows if r.next_attempt_at]
		self.assertEqual(len(held), 3)
		for r in held:
			self.assertGreater(r.next_attempt_at, add_to_date(now, hours=23, minutes=50))
			self.assertLess(r.next_attempt_at, add_to_date(now, hours=24, minutes=5))
		self.assertEqual([r.next_attempt_at for r in rows[:2]], [None, None])  # first two go now

	def test_runner_does_not_send_held_rows_before_their_time(self):
		b = self.make(n=5)
		runner.start(b, USER, ["over_budget"])
		frappe.db.set_value(B, b, "status", "Running")
		send = self.fake_send()
		res = runner.tick(b)
		self.assertEqual(send.call_count, 2)
		self.assertEqual(res["result"], "idle")  # no busy loop re-enqueue for held rows
		self.assertEqual(self.statuses(b), ["queued"] * 3 + ["sent"] * 2)
		self.assertEqual(self.st(b), "Running")  # not completed while rows wait
		self.assertEqual(self.enqueue.call_count, 1)  # only the start enqueue

	def test_held_rows_send_once_their_window_opens(self):
		b = self.make(n=5)
		runner.start(b, USER, ["over_budget"])
		runner.tick(b) if False else None
		frappe.db.sql(f"update `tab{R}` set next_attempt_at=%s where broadcast=%s and next_attempt_at is not null",
			(add_to_date(now_datetime(), seconds=-5), b))
		send = self.fake_send()
		runner.tick(b)
		self.assertEqual(send.call_count, 5)
		self.assertEqual(self.st(b), "Completed")

	def test_no_deferral_when_over_budget_not_acknowledged_as_a_warning(self):
		self.preview.return_value = _preview(queued=5, remaining_24h=2, warnings=[])
		b = self.make(n=5)
		res = runner.start(b, USER, [])
		self.assertEqual(res["deferred_over_budget"], 0)
		self.assertTrue(all(r.next_attempt_at is None for r in self._rows(b)))

	def test_deferred_count_zero_without_budget_number(self):
		self.preview.return_value = _preview(queued=5, remaining_24h=None, warnings=[_w("over_budget")])
		b = self.make(n=5)
		self.assertEqual(runner.start(b, USER, ["over_budget"])["deferred_over_budget"], 0)


if __name__ == "__main__":
	unittest.main()
