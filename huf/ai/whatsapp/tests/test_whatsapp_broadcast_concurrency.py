# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-F: several Running broadcasts per gateway share its speed and its 24h contact budget."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import limits as bl, runner, status as bs
from huf.ai.whatsapp.broadcast.checks import gateway_bucket as gb
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import GW, R, USER, B, _Base

REAL_PREVIEW = bl.preview
RATE = 10


class _Clock:
	"""Simulated clock: the bucket reads ``now`` and its sleeps advance it."""

	def __init__(self, start=1000.0):
		self.t = start

	def now(self):
		return self.t

	def sleep(self, seconds):
		self.t += max(seconds, 0)


class _BucketCase(_Base):
	def setUp(self):
		super().setUp()
		self.clock = _Clock()
		patch.object(gb, "_now", self.clock.now).start()
		patch.object(gb, "_sleep", self.clock.sleep).start()
		patch.object(gb, "gateway_rate", return_value=RATE).start()
		gb.reset(GW)
		self.addCleanup(gb.reset, GW)

	def gaps_ok(self, times):
		times = sorted(times)
		for a, b in zip(times, times[1:]):
			self.assertGreaterEqual(b - a, 1.0 / RATE - 1e-6, (a, b))


class TestSharedSpeed(_BucketCase):
	def test_two_callers_never_exceed_gateway_rate_and_alternate(self):
		stamps = {"A": [], "B": []}
		for _ in range(30):
			for who in ("A", "B"):  # one reservation each per turn, like two live ticks
				gb.pace(GW)
				stamps[who].append(self.clock.now())
		self.gaps_ok(stamps["A"] + stamps["B"])
		elapsed = self.clock.now() - 1000.0
		self.assertLessEqual(60 / elapsed, RATE + 1)  # sum rate stays at the gateway rate
		self.assertEqual(len(stamps["A"]), len(stamps["B"]))  # none starved
		# neither side runs ahead: sorted order alternates A/B
		order = sorted([(t, "A") for t in stamps["A"]] + [(t, "B") for t in stamps["B"]])
		self.assertTrue(all(order[i][1] != order[i + 1][1] for i in range(len(order) - 1)))

	def test_two_runner_ticks_share_the_gateway_rate(self):
		patch.object(runner.broadcast_limits, "get_messaging_limit", return_value={"mps": 1000}).start()
		a = self.make(n=20, status="Running")
		b = self.make(n=20, status="Running")
		sent = []

		def _send(name):
			sent.append(self.clock.now())
			frappe.db.set_value(R, name, {"status": "sent", "message_status": "accepted", "sent_at": now_datetime()})
			return "sent"

		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		self.addCleanup(lambda: [frappe.cache().delete(runner._lock_key(x)) for x in (a, b)])
		with limit_override(one_active_per_gateway=False):
			self.assertEqual(runner.tick(a)["result"], "completed")
			self.assertEqual(runner.tick(b)["result"], "completed")
		self.assertEqual(len(sent), 40)
		self.gaps_ok(sent)
		self.assertLessEqual(len(sent) / (sent[-1] - sent[0] + 1.0 / RATE), RATE + 0.01)

	def test_bucket_failure_falls_back_to_per_tick_pacing(self):
		cache = frappe.cache()
		a = self.make(n=3, status="Running")
		self.addCleanup(lambda: frappe.cache().delete(runner._lock_key(a)))
		self.assertTrue(gb.pace(GW))
		with patch.object(type(cache), "eval", side_effect=RuntimeError("redis down"), create=True):
			self.assertIsNone(gb.reserve(GW, RATE))
			self.assertFalse(gb.pace(GW))
			before = self.clock.now()
			self.fake_send()
			self.assertEqual(runner.tick(a)["result"], "completed")
			self.assertEqual(self.clock.now(), before)  # the bucket never slept
		self.assertTrue(any(c.args and c.args[0] > 0 for c in self.sleep.call_args_list))  # old pacing ran


class TestSharedBudget(_Base):
	def setUp(self):
		super().setUp()
		self.preview.side_effect = REAL_PREVIEW
		patch.object(bl, "get_messaging_limit", return_value={"tier": "TIER_250", "max_unique_24h": 10, "quality": None, "mps": 1000}).start()
		patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}).start()

	def draft(self, numbers):
		b = self.make(n=0)
		for n in numbers:
			self.row(b, n)
		frappe.db.commit()
		return b

	def test_reserved_counts_other_running_queued_rows_once(self):
		a = self.make(n=4, status="Running")
		b = self.draft(["15559990001", "15559990002"])
		self.assertEqual(bl._used_24h(GW, b, [a]), 4)
		self.row(b, "15550000000")  # same person as one of A's rows
		self.assertEqual(bl._used_24h(GW, b, [a]), 4)
		self.assertEqual(bl._used_24h(GW), 0)  # without others only started sends count

	def test_two_concurrent_starts_cannot_both_claim_the_budget(self):
		a = self.draft([f"1555111{i:04d}" for i in range(8)])
		b = self.draft([f"1555222{i:04d}" for i in range(8)])
		with limit_override(one_active_per_gateway=False):
			self.assertEqual(runner.start(a, USER, [])["status"], "Running")
			self.assertEqual(REAL_PREVIEW(b, locked=True)["remaining_24h"], 2)
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [])
			self.assertEqual(cm.exception.code, "warnings_changed")
			codes = {w["code"] for w in cm.exception.extra["warnings"]}
			self.assertEqual(codes, {"over_budget", "other_broadcast_running"})
			res = runner.start(b, USER, sorted(codes))
		self.assertEqual(res["deferred_over_budget"], 6)
		held = frappe.db.count(R, {"broadcast": b, "status": "queued", "next_attempt_at": [">", now_datetime()]})
		self.assertEqual(held, 6)

	def test_held_rows_of_a_running_broadcast_reserve_nothing(self):
		a = self.make(n=3, status="Running")
		frappe.db.sql(f"update `tab{R}` set next_attempt_at=%s where broadcast=%s", (add_to_date(now_datetime(), hours=5), a))
		self.assertEqual(bl._used_24h(GW, "other", [a]), 0)


class TestConcurrencyLimits(_Base):
	def test_max_caps_running_broadcasts(self):
		ids = [self.make(n=1) for _ in range(3)]
		with limit_override(one_active_per_gateway=False, concurrent_broadcast_max=2):
			runner.start(ids[0], USER, [])
			self.preview.return_value["warnings"] = [{"code": "other_broadcast_running", "message": "x", "limit_key": None}]
			runner.start(ids[1], USER, ["other_broadcast_running"])
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(ids[2], USER, ["other_broadcast_running"])
		self.assertEqual(cm.exception.code, "another_broadcast_running")
		self.assertEqual(self.st(ids[2]), "Draft")

	def test_blank_max_is_unlimited_and_one_active_means_one(self):
		with limit_override(one_active_per_gateway=False, concurrent_broadcast_max=None):
			self.assertIsNone(runner.policy.concurrency_cap())
		with limit_override(one_active_per_gateway=True, concurrent_broadcast_max=5):
			self.assertEqual(runner.policy.concurrency_cap(), 1)

	def test_kill_switch_pauses_every_running_broadcast(self):
		a, b = self.make(status="Running"), self.make(status="Running")
		self.assertEqual(sorted(runner.pause_all(GW, "kill_switch")), sorted([a, b]))
		for x in (a, b):
			self.assertEqual(self.st(x), "Paused")
			self.assertEqual(runner.tick(x)["result"], "not_running:Paused")

	def test_stop_reply_skips_the_contact_in_both(self):
		a, b = self.make(n=2, status="Running"), self.make(n=2, status="Running")
		self.assertEqual(bs.apply_user_stop(GW, "15550000000"), 2)
		for x in (a, b):
			rows = frappe.get_all(R, filters={"broadcast": x, "recipient": "15550000000"}, fields=["status", "skip_reason"])
			self.assertEqual([(r.status, r.skip_reason) for r in rows], [("skipped", "opted_out")])
			self.assertEqual(frappe.db.count(R, {"broadcast": x, "status": "queued"}), 1)
