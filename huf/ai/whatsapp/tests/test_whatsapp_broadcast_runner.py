# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-5: WhatsApp Broadcast runner (state transitions, pacing, stale handling, auto-pause).

``broadcast_send.send_one`` and ``broadcast_limits`` are mocked; rows and broadcasts are real.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp import broadcast_runner as runner

GW = "GW-RUNNER-TEST"
GW2 = "GW-RUNNER-TEST-2"
USER = "Administrator"
B, R = "WhatsApp Broadcast", "WhatsApp Broadcast Recipient"


def _preview(**over):
	base = {"recipients": 3, "queued": 3, "skipped": 0, "category": "UTILITY", "template_status": "APPROVED",
			"within_limit": True, "remaining_24h": 1000, "warnings": [], "blocking": []}
	base.update(over)
	return base


class _Base(unittest.TestCase):
	def setUp(self):
		self._clean()
		self.addCleanup(self._clean)
		self.addCleanup(patch.stopall)
		self.enqueue = patch.object(runner, "_enqueue_tick").start()
		self.preview = patch.object(runner.broadcast_limits, "preview", return_value=_preview()).start()
		patch.object(runner.broadcast_limits, "get_messaging_limit", return_value={"mps": 1000}).start()
		patch.object(runner, "_gateway_write_ok", return_value=True).start()
		self.sleep = patch.object(runner, "_sleep").start()
		frappe.flags.broadcast_pause = None

	def _clean(self):
		names = frappe.get_all(B, filters={"gateway": ["in", [GW, GW2]]}, pluck="name")
		if names:
			frappe.db.delete(R, {"broadcast": ["in", names]})
			frappe.db.delete(B, {"name": ["in", names]})
		frappe.db.commit()

	def make(self, n=3, gateway=GW, status="Draft", attested=1, **over):
		doc = frappe.get_doc({"doctype": B, "title": "t", "gateway": gateway, "status": status,
							  "consent_attested": attested, "template": "tpl", "template_name": "tpl",
							  "whatsapp_account": "ACC", "started_by": USER if status != "Draft" else None, **over})
		doc.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		for i in range(n):
			self.row(doc.name, f"1555000{i:04d}")
		frappe.db.commit()
		return doc.name

	def row(self, bcast, num, status="queued", **over):
		d = frappe.get_doc({"doctype": R, "broadcast": bcast, "recipient": num, "status": status, **over})
		d.insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)
		return d.name

	def st(self, name, field="status"):
		return frappe.db.get_value(B, name, field)

	def row_status(self, name):
		return frappe.db.get_value(R, name, "status")

	def statuses(self, bcast):
		return sorted(frappe.get_all(R, filters={"broadcast": bcast}, pluck="status"))

	def fake_send(self, status="sent", message_status="accepted"):
		def _send(name):
			frappe.db.set_value(R, name, {"status": status, "message_status": message_status, "sent_at": now_datetime()})
			return status
		return patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()


class TestStart(_Base):
	def test_draft_to_running_enqueues_tick(self):
		b = self.make()
		res = runner.start(b, USER)
		self.assertEqual(res["status"], "Running")
		doc = frappe.get_doc(B, b)
		self.assertEqual((doc.status, doc.started_by), ("Running", USER))
		self.assertIsNotNone(doc.started_at)
		self.enqueue.assert_called_once_with(b)

	def test_refuses_without_consent(self):
		b = self.make(attested=0)
		with self.assertRaises(frappe.ValidationError):
			runner.start(b, USER)
		self.assertEqual(self.st(b, "status"), "Draft")

	def test_refuses_wrong_status(self):
		b = self.make(status="Completed")
		with self.assertRaises(frappe.ValidationError):
			runner.start(b, USER)

	def test_refuses_blocking_preview(self):
		self.preview.return_value = _preview(blocking=["template not APPROVED"])
		b = self.make()
		with self.assertRaises(frappe.ValidationError):
			runner.start(b, USER)
		self.enqueue.assert_not_called()

	def test_refuses_nothing_queued(self):
		self.preview.return_value = _preview(queued=0)
		with self.assertRaises(frappe.ValidationError):
			runner.start(self.make(n=0), USER)

	def test_refuses_without_gateway_write(self):
		runner._gateway_write_ok.return_value = False
		with self.assertRaises(frappe.PermissionError):
			runner.start(self.make(), USER)

	def test_one_running_per_gateway(self):
		a, b = self.make(), self.make()
		runner.start(a, USER)
		with self.assertRaises(frappe.ValidationError):
			runner.start(b, USER)
		self.assertEqual(self.st(b, "status"), "Draft")

	def test_other_gateway_is_independent(self):
		runner.start(self.make(), USER)
		runner.start(self.make(gateway=GW2), USER)


class TestPauseResumeCancel(_Base):
	def test_pause_and_resume(self):
		b = self.make()
		runner.start(b, USER)
		self.assertTrue(runner.pause(b, "manual"))
		doc = frappe.get_doc(B, b)
		self.assertEqual((doc.status, doc.pause_reason), ("Paused", "manual"))
		self.assertFalse(runner.pause(b))  # already paused
		runner.resume(b)
		doc.reload()
		self.assertEqual((doc.status, doc.pause_reason), ("Running", None))
		self.assertEqual(self.enqueue.call_count, 2)

	def test_resume_requires_paused(self):
		with self.assertRaises(frappe.ValidationError):
			runner.resume(self.make())

	def test_cancel_marks_queued_and_deferred_skipped(self):
		b = self.make(n=2)
		self.row(b, "15551110001", "deferred")
		sent = self.row(b, "15551110002", "sent")
		sending = self.row(b, "15551110003", "sending")
		runner.start(b, USER)
		runner.cancel(b)
		self.assertEqual(self.st(b, "status"), "Cancelled")
		self.assertEqual(self.row_status(sent), "sent")
		self.assertEqual(self.row_status(sending), "sending")
		skipped = frappe.get_all(R, filters={"broadcast": b, "status": "skipped"}, fields=["skip_reason"])
		self.assertEqual(len(skipped), 3)
		self.assertTrue(all(s.skip_reason == "cancelled" for s in skipped))
		self.assertEqual(frappe.db.get_value(B, b, "skipped"), 3)

	def test_pause_all_and_pause_for_template(self):
		a = self.make()
		runner.start(a, USER)
		b = self.make(gateway=GW2)
		runner.start(b, USER)
		self.assertEqual(runner.pause_all(GW, "kill"), [a])
		self.assertEqual(self.st(b, "status"), "Running")
		self.assertEqual(runner.pause_for_template("ACC", "tpl", "paused"), [b])
		self.assertEqual(self.st(b, "pause_reason"), "template:paused")
		self.assertEqual(runner.pause_for_template("ACC", "other", "x"), [])


class TestTick(_Base):
	def setUp(self):
		super().setUp()
		self.addCleanup(lambda: frappe.cache().delete(runner._lock_key(self.b)) if getattr(self, "b", None) else None)

	def running(self, **kw):
		self.b = self.make(status="Running", **kw)
		return self.b

	def test_sends_all_and_completes(self):
		b = self.running()
		send = self.fake_send()
		res = runner.tick(b)
		self.assertEqual(res["result"], "completed")
		self.assertEqual(send.call_count, 3)
		doc = frappe.get_doc(B, b)
		self.assertEqual((doc.status, doc.sent), ("Completed", 3))
		self.assertIsNotNone(doc.finished_at)

	def test_ramp_first_batch_is_20_then_grows(self):
		b = self.running(n=70)
		self.fake_send()
		sizes = []
		orig = runner._due_rows
		patch.object(runner, "_due_rows", side_effect=lambda bc, n: (sizes.append(n), orig(bc, n))[1]).start()
		runner.tick(b)
		self.assertEqual(sizes[:3], [20, 20, 40])

	def test_not_running_is_a_noop(self):
		b = self.make(status="Paused")
		send = self.fake_send()
		self.assertTrue(runner.tick(b)["result"].startswith("not_running"))
		send.assert_not_called()

	def test_single_flight_lock(self):
		b = self.running()
		send = self.fake_send()
		frappe.cache().set(runner._lock_key(b), 1, ex=60)
		self.assertEqual(runner.tick(b)["result"], "locked")
		send.assert_not_called()

	def test_permission_loss_pauses(self):
		b = self.running()
		runner._gateway_write_ok.return_value = False
		send = self.fake_send()
		self.assertEqual(runner.tick(b)["result"], "paused")
		self.assertEqual(self.st(b, "pause_reason"), "permission_lost")
		send.assert_not_called()

	def test_deferred_future_rows_not_busy_looped(self):
		b = self.running(n=0)
		future = self.row(b, "15552220001", "deferred", next_attempt_at=add_to_date(now_datetime(), hours=24))
		send = self.fake_send()
		res = runner.tick(b)
		self.assertEqual(res["result"], "idle")
		send.assert_not_called()
		self.enqueue.assert_not_called()
		self.assertEqual(self.row_status(future), "deferred")
		self.assertEqual(self.st(b, "status"), "Running")  # not completed while deferred rows remain

	def test_due_deferred_rows_are_sent(self):
		b = self.running(n=0)
		self.row(b, "15552220002", "deferred", next_attempt_at=add_to_date(now_datetime(), minutes=-1))
		send = self.fake_send()
		runner.tick(b)
		self.assertEqual(send.call_count, 1)

	def test_sending_and_unknown_rows_never_sent_and_block_nothing_but_sending(self):
		b = self.running(n=0)
		self.row(b, "15553330001", "unknown")
		sending = self.row(b, "15553330002", "sending")
		send = self.fake_send()
		res = runner.tick(b)
		send.assert_not_called()
		self.assertEqual(res["result"], "idle")  # in-flight sending row: not complete yet
		frappe.db.set_value(R, sending, "status", "sent")
		self.assertEqual(runner.tick(b)["result"], "completed")

	def test_auto_pause_on_pause_signal(self):
		b = self.running(n=5)

		def _send(name):
			frappe.db.set_value(R, name, "status", "failed")
			frappe.flags.broadcast_pause = "135000"
			return "failed"

		send = patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		res = runner.tick(b)
		self.assertEqual(res["result"], "paused")
		self.assertEqual(send.call_count, 1)
		self.assertEqual((self.st(b, "status"), self.st(b, "pause_reason")), ("Paused", "135000"))
		self.assertEqual(self.statuses(b).count("queued"), 4)

	def test_stops_when_paused_mid_tick(self):
		b = self.running(n=5)
		calls = []

		def _send(name):
			calls.append(name)
			frappe.db.set_value(R, name, "status", "sent")
			runner.pause(b, "manual")
			return "sent"

		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		self.assertEqual(runner.tick(b)["result"], "stopped")
		self.assertEqual(len(calls), 1)

	def test_cancelled_mid_tick_stops(self):
		b = self.running(n=5)

		def _send(name):
			frappe.db.set_value(R, name, "status", "sent")
			runner.cancel(b)
			return "sent"

		send = patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		runner.tick(b)
		self.assertEqual(send.call_count, 1)
		self.assertEqual(self.statuses(b).count("skipped"), 4)

	def test_held_ratio_throttles(self):
		b = self.running(n=3)
		for i in range(12):
			self.row(b, f"1555444{i:04d}", "sent", message_status=runner.HELD_STATUS, sent_at=now_datetime())
		self.assertGreater(runner._held_ratio(b)[0], 0.3)
		self.fake_send()
		runner.tick(b)
		waits = [c.args[0] for c in self.sleep.call_args_list if c.args and c.args[0] > 0]
		self.assertTrue(waits)
		self.assertTrue(all(w <= 1.0 / (1000 // 4) for w in waits))  # paced at mps//4, not mps

	def test_held_ratio_below_sample_does_not_throttle(self):
		b = self.running(n=1)
		self.row(b, "15556660001", "sent", message_status=runner.HELD_STATUS, sent_at=now_datetime())
		ratio, n = runner._held_ratio(b)
		self.assertLess(n, runner.MIN_HELD_SAMPLE)

	def test_budget_exhausted_reenqueues_continuation(self):
		b = self.running(n=5)
		self.fake_send()
		with patch.object(runner, "TICK_BUDGET_SECONDS", -1):
			res = runner.tick(b)
		self.assertEqual(res["result"], "continued")
		self.enqueue.assert_called_once_with(b, continuation=True)


class TestResumeStale(_Base):
	def test_stale_sending_becomes_unknown_fresh_untouched(self):
		b = self.make(n=0, status="Running")
		old = self.row(b, "15557770001", "sending")
		new = self.row(b, "15557770002", "sending")
		frappe.db.set_value(R, old, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		res = runner.resume_stale()
		self.assertEqual(self.row_status(old), "unknown")
		self.assertEqual(self.row_status(new), "sending")
		self.assertEqual(res["stale_to_unknown"], 1)
		self.assertEqual(frappe.db.get_value(B, b, "unknown"), 1)

	def test_never_resends_stale_rows(self):
		b = self.make(n=0, status="Running")
		old = self.row(b, "15557770003", "sending")
		frappe.db.set_value(R, old, "modified", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		send = self.fake_send()
		runner.resume_stale()
		runner.tick(b)
		send.assert_not_called()

	def test_running_without_live_tick_is_re_enqueued(self):
		b = self.make(status="Running")
		self.assertIn(b, runner.resume_stale()["revived"])
		self.enqueue.assert_called_with(b)

	def test_running_with_live_tick_not_re_enqueued(self):
		b = self.make(status="Running")
		frappe.cache().set(runner._lock_key(b), 1, ex=60)
		self.addCleanup(frappe.cache().delete, runner._lock_key(b))
		self.assertNotIn(b, runner.resume_stale()["revived"])

	def test_finished_running_broadcast_is_completed(self):
		b = self.make(n=0, status="Running")
		self.row(b, "15557770004", "sent")
		runner.resume_stale()
		self.assertEqual(self.st(b, "status"), "Completed")
