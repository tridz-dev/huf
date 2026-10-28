# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-I: fixes from the Opus re-review (start snapshot race, gateway bucket, resume, fallback pacing)."""

from __future__ import annotations

import threading
from unittest.mock import patch

import frappe

from huf.ai.whatsapp.broadcast import limits as bl, policy, progress, runner
from huf.ai.whatsapp.broadcast.checks import gateway_bucket as gb, start_gate
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import _preview, GW, R, USER, B, _Base

REAL_PREVIEW = bl.preview


def in_second_connection(fn):
	"""Run ``fn`` on its own thread with its own database connection and commit; re-raise its error."""
	site, sites_path = frappe.local.site, frappe.local.sites_path
	errors: list[BaseException] = []

	def work():
		try:
			frappe.init(site=site, sites_path=sites_path)
			frappe.connect()
			frappe.set_user("Administrator")
			fn()
			frappe.db.commit()
		except BaseException as exc:  # noqa: BLE001 - surfaced to the test thread
			errors.append(exc)
		finally:
			frappe.destroy()

	t = threading.Thread(target=work)
	t.start()
	t.join(60)
	assert not t.is_alive(), "second connection hung"
	if errors:
		raise errors[0]


class TestStartSeesOtherStartsOnItsOwnConnection(_Base):
	def setUp(self):
		super().setUp()
		self.preview.side_effect = REAL_PREVIEW
		patch.object(bl, "get_messaging_limit", return_value={"tier": "TIER_250", "max_unique_24h": 10, "quality": None, "mps": 1000}).start()
		patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}).start()

	def _add_rows(self, broadcast, prefix, n):
		for i in range(n):
			self.row(broadcast, f"{prefix}{i:04d}")

	def test_second_start_sees_the_first_starts_reservation(self):
		"""A's rows and Running state commit on another connection after B has taken its first read.

		B's pre-lock reads are a REPEATABLE READ snapshot that predates A's rows; after the Gateway lock B
		must read current data, or both starts claim the same 24h budget."""
		a = self.make(n=0)
		b = self.make(n=0)
		self._add_rows(b, "1555222", 8)
		frappe.db.commit()
		real_check = start_gate.check_preview
		fired = []

		def check_then_race(*args, **kw):
			out = real_check(*args, **kw)
			if not fired:
				fired.append(1)

				def first_start():
					self._add_rows(a, "1555111", 8)
					frappe.db.commit()
					runner.start(a, USER, [])

				in_second_connection(first_start)
			return out

		with limit_override(one_active_per_gateway=False), patch.object(start_gate, "check_preview", check_then_race):
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [])
		self.assertEqual(cm.exception.code, "warnings_changed")
		codes = {w["code"] for w in cm.exception.extra["warnings"]}
		self.assertEqual(codes, {"over_budget", "other_broadcast_running"})
		self.assertEqual(frappe.db.get_value(B, a, "status"), "Running")
		self.assertEqual(frappe.db.get_value(B, b, "status"), "Draft")

	def test_recipients_changed_sees_a_concurrent_commit(self):
		b = self.make(n=3)
		real_check = start_gate.check_preview
		fired = []

		def check_then_race(*args, **kw):
			out = real_check(*args, **kw)
			if not fired:
				fired.append(1)
				in_second_connection(lambda: frappe.db.sql(
					f"update `tab{R}` set status='skipped', skip_reason='opted_out' where broadcast=%s limit 1", b))
			return out

		with patch.object(start_gate, "check_preview", check_then_race):
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [], expected_count=3)
		self.assertEqual(cm.exception.code, "recipients_changed")


class TestGatewayBucket(_Base):
	"""Real Redis, no sleeping: waits are read from ``reserve`` and never slept."""

	def setUp(self):
		super().setUp()
		gb.reset(GW)
		self.addCleanup(gb.reset, GW)

	def test_many_tickers_on_a_slow_gateway_queue_instead_of_bursting(self):
		# 1 message/s with 15 tickers each holding one reservation: the 11th used to push the schedule past
		# the 10 s horizon, which reset it and let a burst through.
		waits = [gb.reserve(GW, 1.0) for _ in range(15)]
		self.assertTrue(all(w is not None for w in waits))
		for i, w in enumerate(waits):
			self.assertAlmostEqual(w, float(i), delta=0.6, msg=str(waits))
		self.assertEqual(waits, sorted(waits))

	def test_the_schedule_uses_redis_time_not_the_worker_clock(self):
		self.assertIsNone(gb._now())  # no worker timestamp is sent; the Lua script reads TIME itself
		first, second = gb.reserve(GW, 10.0), gb.reserve(GW, 10.0)
		self.assertLess(first, 0.2)
		self.assertAlmostEqual(second - first, 0.1, delta=0.05)

	def test_reset_really_forgets_the_schedule(self):
		for _ in range(3):
			gb.reserve(GW, 1.0)
		self.assertGreater(gb.reserve(GW, 1.0), 2.0)
		gb.reset(GW)
		self.assertLess(gb.reserve(GW, 1.0), 0.6)

	def test_settings_read_at_call_time(self):
		with limit_override(gateway_bucket_horizon_seconds=1):
			self.assertEqual(gb.horizon(1.0), 100.0)  # never below 100 slots ahead
		self.assertGreaterEqual(gb.horizon(1.0), 100.0)


class TestFallbackPacing(_Base):
	def test_running_share_counts_running_broadcasts_on_the_gateway(self):
		self.assertEqual(gb.running_share(GW), 1)
		self.make(status="Running")
		self.make(status="Running")
		self.assertEqual(gb.running_share(GW), 2)

	def test_bucket_unavailable_divides_the_pace_by_the_running_count(self):
		a = self.make(n=3, status="Running")
		self.make(n=1, status="Running")
		self.addCleanup(lambda: frappe.cache().delete(runner._lock_key(a)))
		self.fake_send()
		patch.object(runner.gateway_bucket, "pace", return_value=False).start()
		self.assertEqual(runner.tick(a)["result"], "completed")
		slept = [c.args[0] for c in self.sleep.call_args_list if c.args and c.args[0] > 0]
		self.assertTrue(slept)
		self.assertGreater(min(slept), 0.08)  # 20 mps / 2 running = 10 mps = 0.1 s, not the 0.05 s of 20 mps


def _w(code):
	return {"code": code, "message": code, "limit_key": None}


class TestResumeAcknowledgements(_Base):
	def _paused(self, acked=None):
		b = self.make(n=2, status="Paused")
		if acked is not None:
			start_gate.record_acknowledged(b, acked)
		return b

	def test_a_transient_warning_does_not_strand_a_resume(self):
		b = self._paused(["quality_red"])
		self.preview.return_value = _preview(warnings=[_w("quality_red"), _w("other_broadcast_running")])
		runner.resume(b)
		self.assertEqual(self.st(b), "Running")

	def test_a_new_non_transient_warning_still_refuses(self):
		b = self._paused([])
		self.preview.return_value = _preview(warnings=[_w("other_broadcast_running"), _w("quality_red")])
		with self.assertRaises(runner.StartRefused):
			runner.resume(b)
		self.assertEqual(self.st(b), "Paused")

	def test_a_comment_cannot_forge_an_acknowledgement(self):
		b = self._paused()
		frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": B, "reference_name": b,
			"content": 'acknowledged_warnings: ["quality_red"]'}).insert(ignore_permissions=True)
		self.assertEqual(start_gate.stored_acknowledged(b), set())
		self.preview.return_value = _preview(warnings=[_w("quality_red")])
		with self.assertRaises(runner.StartRefused):
			runner.resume(b)

	def test_a_corrupt_stored_value_reads_as_nothing_acknowledged(self):
		b = self._paused()
		for raw in ("{not json", '{"a": 1}', '"quality_red"', '[1, "quality_red"]'):
			frappe.db.set_value(B, b, "acknowledged_warnings", raw)
			self.assertLessEqual(start_gate.stored_acknowledged(b), {"quality_red"})
		frappe.db.set_value(B, b, "acknowledged_warnings", "{not json")
		self.assertEqual(start_gate.stored_acknowledged(b), set())

	def test_start_stores_the_codes_on_the_broadcast_itself(self):
		b = self.make(n=1)
		self.preview.return_value = _preview(warnings=[_w("quality_red")])
		runner.start(b, USER, ["quality_red"])
		self.assertEqual(frappe.db.get_value(B, b, "acknowledged_warnings"), '["quality_red"]')


class TestRegistryAndInEffect(_Base):
	def test_internal_rows_are_read_at_call_time(self):
		for key in ("gateway_bucket_horizon_seconds", "gateway_bucket_key_seconds", "gateway_rate_cache_seconds"):
			self.assertEqual(policy.BY_KEY[key].kind, "internal")
		with limit_override(progress_throttle_seconds=7):
			self.assertEqual(progress.throttle_seconds(), 7.0)
		with limit_override(gateway_rate_cache_seconds=0, max_mps_cap=5):
			gb._rates.clear()
			patch.object(bl, "get_messaging_limit", return_value={"mps": None}).start()
			self.assertEqual(gb.gateway_rate(GW), 5)

	def test_a_saved_cap_setting_is_reported_as_in_effect(self):
		patch.object(bl, "get_messaging_limit", return_value={"tier": "TIER_UNLIMITED", "max_unique_24h": None, "quality": None, "mps": 80}).start()
		patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}).start()
		b = self.make(n=1)
		self.assertNotIn("max_recipients_default", REAL_PREVIEW(b)["limits_in_effect"])
		with limit_override(max_recipients_default=7):
			self.assertIn("max_recipients_default", REAL_PREVIEW(b)["limits_in_effect"])
		own = self.make(n=1, max_recipients=3)
		self.assertIn("max_recipients_default", REAL_PREVIEW(own)["limits_in_effect"])
