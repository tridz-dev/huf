# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-B: runner hardening (C1, C4, M1, lock owner/heartbeat/deadline, L2, L7, site-scoped keys)."""

from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, now_datetime

from huf.ai.whatsapp.broadcast import runner as runner
from huf.ai.whatsapp.broadcast import stale
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import GW, USER, B, R, _Base, _preview


class TestFixes(_Base):
	def setUp(self):
		super().setUp()
		self.addCleanup(lambda: frappe.cache().delete(runner._lock_key(self.b)) if getattr(self, "b", None) else None)

	def running(self, **kw):
		self.b = self.make(status="Running", **kw)
		return self.b

	# C1
	def test_complete_does_not_overwrite_cancelled_or_paused(self):
		for status in ("Cancelled", "Paused"):
			b = self.make(n=0, status=status)
			self.assertFalse(runner._complete_if_done(b))
			self.assertEqual(self.st(b), status)

	def test_complete_when_running(self):
		b = self.make(n=0, status="Running")
		self.assertTrue(runner._complete_if_done(b))
		self.assertEqual(self.st(b), "Completed")

	def test_cancel_landing_before_final_complete(self):
		b = self.running(n=1)

		def _send(name):
			frappe.db.set_value(R, name, "status", "sent")
			frappe.db.set_value(B, b, "status", "Cancelled")
			frappe.db.commit()
			return "sent"

		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		runner.tick(b)
		self.assertEqual(self.st(b), "Cancelled")

	# C4
	def test_resume_paused_with_only_deferred_rows(self):
		self.preview.return_value = _preview(queued=0)
		b = self.make(n=0, status="Paused")
		self.row(b, "15552220001", "deferred", next_attempt_at=add_to_date(now_datetime(), hours=1))
		frappe.db.commit()
		self.assertEqual(runner.resume(b)["status"], "Running")
		self.assertEqual(self.st(b), "Running")

	def test_resume_with_nothing_remaining_still_refused(self):
		self.preview.return_value = _preview(queued=0)
		with self.assertRaises(frappe.ValidationError):
			runner.resume(self.make(n=0, status="Paused"))

	# M1
	def test_two_starts_second_refused_when_first_commits_mid_flight(self):
		a, b = self.make(), self.make()
		orig = runner.broadcast_limits.preview

		def _preview_then_other_starts(name):
			# a concurrent start of `b` commits after `a` took its snapshot reads
			frappe.db.set_value(B, b, "status", "Running")
			frappe.db.commit()
			return _preview()

		self.preview.side_effect = _preview_then_other_starts
		with self.assertRaises(frappe.ValidationError):
			runner.start(a, USER)
		self.assertEqual(self.st(a), "Draft")
		self.preview.side_effect = None

	def test_other_running_query_is_locking_and_gateway_locked_first(self):
		a, b = self.make(), self.make()
		calls = []
		orig = frappe.db.get_value

		def spy(*args, **kw):
			calls.append(((args or [kw.get("doctype")])[0], kw.get("for_update")))
			return orig(*args, **kw)

		with patch.object(frappe.db, "get_value", side_effect=spy):
			runner.start(a, USER)
		locked = [c for c in calls if c[1]]
		self.assertEqual(locked[0][0], "Gateway")
		self.assertTrue(any(c[0] == B for c in locked))

	# lock token / TTL / deadline
	def test_lock_value_is_owner_token_and_release_only_if_owner(self):
		b = self.running(n=1)
		self.fake_send()
		seen = {}
		orig = runner._due_rows

		def spy(bc, n):
			seen["val"] = frappe.cache().get(runner._lock_key(bc))
			return orig(bc, n)

		patch.object(runner, "_due_rows", side_effect=spy).start()
		runner.tick(b)
		val = seen["val"].decode() if isinstance(seen["val"], bytes) else seen["val"]
		self.assertEqual(len(val), 32)
		self.assertIsNone(frappe.cache().get(runner._lock_key(b)))
		# a foreign owner's lock is not deleted by release
		frappe.cache().set(runner._lock_key(b), "other", ex=60)
		runner._release(runner._lock_key(b), "mine")
		raw = frappe.cache().get(runner._lock_key(b))
		self.assertEqual(raw.decode() if isinstance(raw, bytes) else raw, "other")

	def test_lock_stolen_mid_tick_is_not_deleted_and_tick_stops(self):
		b = self.running(n=3)

		def _send(name):
			frappe.db.set_value(R, name, "status", "sent")
			frappe.cache().set(runner._lock_key(b), "thief", ex=60)
			return "sent"

		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		with limit_override(heartbeat_every_sends=1):
			res = runner.tick(b)
		self.assertEqual(res["result"], "lock_lost")
		raw = frappe.cache().get(runner._lock_key(b))
		self.assertEqual(raw.decode() if isinstance(raw, bytes) else raw, "thief")

	def test_heartbeat_refreshes_ttl_during_batch(self):
		b = self.running(n=6)
		self.fake_send()
		with patch.object(runner, "_heartbeat", wraps=runner._heartbeat) as hb, limit_override(heartbeat_every_sends=2):
			runner.tick(b)
		self.assertGreaterEqual(hb.call_count, 3)  # more than the single end-of-batch beat

	def test_batch_respects_deadline(self):
		b = self.running(n=10)
		send = self.fake_send()
		import time as _t
		from types import SimpleNamespace

		n = {"i": 0}

		def mono():
			n["i"] += 1
			return 0.0 if n["i"] <= 8 else 1000.0

		fake = SimpleNamespace(monotonic=mono, time=_t.time, sleep=lambda s: None)
		with patch.object(runner, "time", fake):
			runner.tick(b)
		self.assertLess(send.call_count, 10)

	# L2
	def test_disabled_user_has_no_authority(self):
		runner._gateway_write_ok.return_value = True
		with patch.object(runner.frappe.db, "get_value", side_effect=lambda *a, **k: 0 if a and a[0] == "User" else None):
			self.assertFalse(runner._user_can_write(USER, GW))
		self.assertTrue(runner._user_can_write(USER, GW))

	def test_permission_rechecked_per_chunk_mid_tick(self):
		b = self.running(n=5)
		calls = {"n": 0}

		def _send(name):
			frappe.db.set_value(R, name, "status", "sent")
			calls["n"] += 1
			if calls["n"] == 2:
				runner._gateway_write_ok.return_value = False  # demoted mid-tick
			return "sent"

		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		with limit_override(perm_recheck_every_sends=1):
			res = runner.tick(b)
		self.assertEqual((res["result"], res["reason"]), ("paused", "permission_lost"))
		self.assertEqual(calls["n"], 2)
		self.assertEqual(self.st(b, "pause_reason"), "permission_lost")

	# L7
	def test_resume_authorizes_resumer_records_comment_and_passes_user(self):
		b = self.make(status="Paused", started_by="Guest")
		authorized = []
		runner._gateway_write_ok.side_effect = lambda gw: authorized.append(frappe.session.user) or True
		runner.resume(b)
		self.assertIn(frappe.session.user, authorized)
		self.assertEqual(self.st(b, "started_by"), "Guest")  # provenance kept
		self.assertEqual(self.st(b, "resumed_by"), frappe.session.user)
		# a Comment cannot change who the runner acts as
		frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": B, "reference_name": b,
						"content": "resumed_by: Administrator-forged"}).insert(ignore_permissions=True)
		self.assertEqual(runner._runner_user(b, "Guest"), frappe.session.user)
		self.enqueue.assert_called_with(b, user=frappe.session.user)
		self.assertEqual(runner._runner_user(b, "Guest"), frappe.session.user)

	def test_resume_denied_when_resumer_lacks_write_even_if_starter_had_it(self):
		b = self.make(status="Paused")
		runner._gateway_write_ok.return_value = False
		with self.assertRaises(frappe.PermissionError):
			runner.resume(b)

	def test_tick_runs_as_passed_user_and_continuation_forwards_it(self):
		b = self.running(n=5)
		seen = []
		def _send(name):
			seen.append(frappe.session.user)
			frappe.db.set_value(R, name, "status", "sent")
			return "sent"
		patch.object(runner.broadcast_send, "send_one", side_effect=_send).start()
		with limit_override(tick_budget_seconds=-1):
			runner.tick(b, user=USER)
		self.enqueue.assert_called_once_with(b, continuation=True, user=USER)
		runner.tick(b, user=USER)
		self.assertEqual(set(seen), {USER})

	# site scoping
	def test_keys_and_job_ids_are_site_scoped(self):
		site = frappe.local.site
		self.assertIn(site, runner._lock_key("BCAST-1"))
		self.assertIn(site, runner._job_id("BCAST-1"))
		with patch.object(runner, "_enqueue_tick", wraps=None) as _:
			pass

	def test_enqueue_uses_site_scoped_job_ids(self):
		patch.stopall()
		with patch.object(runner.frappe, "enqueue") as enq:
			runner._enqueue_tick("BCAST-1")
			runner._enqueue_tick("BCAST-1", continuation=True)
		ids = [c.kwargs["job_id"] for c in enq.call_args_list]
		self.assertTrue(all(frappe.local.site in i for i in ids))
		self.assertNotEqual(ids[0], ids[1])

	# counters reconcile
	def test_tampered_counter_corrected_at_completion(self):
		b = self.running(n=2)
		self.fake_send()
		frappe.db.set_value(B, b, "sent", 99)
		frappe.db.commit()
		self.assertEqual(runner.tick(b)["result"], "completed")
		self.assertEqual(self.st(b, "sent"), 2)

	def test_resume_stale_recounts_running_broadcast(self):
		b = self.running(n=0)
		self.row(b, "15553330001", "sent")
		self.row(b, "15553330002", "deferred", next_attempt_at=add_to_date(now_datetime(), hours=1))
		frappe.db.set_value(B, b, "sent", 42)
		frappe.db.commit()
		frappe.cache().delete(runner._lock_key(b))
		stale.resume_stale()
		self.assertEqual(self.st(b, "sent"), 1)
