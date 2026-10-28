# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-J: start-lock hygiene (no hidden commits), the pre-lock commit guard, fallback pacing re-read, REST guards.

Real bench rows. ``limits.preview`` is the REAL function here (only Graph, the template row and the 24h count
are stubbed) so the locked section runs everything a production start runs.
"""

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from huf.ai.whatsapp.broadcast import api as mgmt, limits as bl, runner
from huf.ai.whatsapp.broadcast.audiences import api as aud_api
from huf.ai.whatsapp.broadcast.checks import start_gate
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_audience_api import AudienceTestCase
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import GW, USER, B, R, _Base

REAL_PREVIEW = bl.preview
REAL_GET_LIMIT = bl.get_messaging_limit
RED_250 = {"tier": "TIER_250", "max_unique_24h": 250, "quality": "RED", "mps": 1000}
ACK = ["over_budget", "quality_red"]


class _Tx:
	"""Commits/rollbacks seen before and after the Gateway row lock was taken."""

	def __init__(self):
		self.locked = False
		self.before = self.after = self.rollbacks = 0


@contextmanager
def _track(strict: bool = False):
	"""Count commit/rollback calls; ``strict`` raises on any (for code that must never end a transaction)."""
	tx = _Tx()
	real_commit, real_get = frappe.db.commit, frappe.db.get_value

	def commit(*a, **kw):
		if strict:
			raise AssertionError("commit inside a section that must not commit")
		if tx.locked:
			tx.after += 1
		else:
			tx.before += 1
		return real_commit(*a, **kw)

	def rollback(*a, **kw):
		tx.rollbacks += 1
		raise AssertionError("rollback while the start lock is held")

	def get_value(*a, **kw):
		if kw.get("for_update") and a[:1] == ("Gateway",):
			tx.locked = True
		return real_get(*a, **kw)

	with patch.object(frappe.db, "commit", commit), patch.object(frappe.db, "rollback", rollback), \
		patch.object(frappe.db, "get_value", get_value):
		yield tx


class _RealPreviewBase(_Base):
	def setUp(self):
		super().setUp()
		patch.object(bl, "preview", REAL_PREVIEW).start()
		patch.object(bl, "get_messaging_limit", return_value=dict(RED_250)).start()
		patch.object(bl, "_template_row", return_value={"status": "APPROVED", "category": "UTILITY"}).start()
		patch.object(bl, "_used_24h", return_value=248).start()  # 250 - 248 = 2 left of 5 queued


class TestNoHiddenCommitsUnderTheLock(_RealPreviewBase):
	def _assert_one_commit_after_lock(self, tx, b):
		self.assertTrue(tx.locked)
		self.assertEqual(tx.after, 1)  # the final commit of _begin, nothing else after the lock
		self.assertEqual(tx.rollbacks, 0)
		self.assertEqual(tx.before, 1)  # the deliberate snapshot-ending commit
		rows = frappe.get_all(R, filters={"broadcast": b}, fields=["next_attempt_at"])
		self.assertEqual(sum(1 for r in rows if r.next_attempt_at), 3)  # over-budget deferral really ran
		self.assertEqual(self.st(b), "Running")
		self.assertEqual(start_gate.stored_acknowledged(b), set(ACK))

	def test_full_start_with_warnings_and_over_budget_deferral(self):
		b = self.make(n=5)
		with _track() as tx:
			res = runner.start(b, USER, ACK)
		self.assertEqual(res["deferred_over_budget"], 3)
		self._assert_one_commit_after_lock(tx, b)

	def test_resume_with_stored_warnings(self):
		b = self.make(n=5, status="Paused")
		start_gate.record_acknowledged(b, ACK)
		frappe.db.commit()
		with _track() as tx:
			res = runner.resume(b)
		self.assertEqual(res["deferred_over_budget"], 3)
		self._assert_one_commit_after_lock(tx, b)

	def test_graph_read_and_cache_never_commit(self):
		"""get_messaging_limit on a cache miss (Graph call, credentials lookup) must not end the transaction."""
		key = bl._cache_key(GW)
		frappe.cache().delete_value(key)
		self.addCleanup(lambda: frappe.cache().delete_value(key))
		creds = {"phone_id": "123", "base": "https://graph.example/v1", "token": "t"}
		body = {bl.LIMIT_FIELD: "TIER_250", "quality_rating": "GREEN", "throughput": 80}
		with patch.object(frappe.db, "exists", return_value=True), \
			patch.object(bl.tc, "resolve_credentials", return_value=creds), \
			patch.object(bl.tc, "_call", return_value=(200, body)), \
			_track(strict=True) as tx:
			out = REAL_GET_LIMIT(GW)
		self.assertEqual(out["tier"], "TIER_250")
		self.assertEqual((tx.before, tx.after, tx.rollbacks), (0, 0, 0))

	def test_locked_preview_alone_never_commits(self):
		b = self.make(n=5)
		with _track(strict=True):
			out = REAL_PREVIEW(b, locked=True)
		self.assertEqual([w["code"] for w in out["warnings"]], ["quality_red", "over_budget"])


class TestPreLockCommitGuard(_Base):
	def _writes(self, n):
		real = frappe.db.transaction_writes
		self.addCleanup(lambda: setattr(frappe.db, "transaction_writes", 0))
		frappe.db.transaction_writes = n
		return real

	def _production(self):
		prev = frappe.flags.in_test
		frappe.flags.in_test = False
		self.addCleanup(lambda: setattr(frappe.flags, "in_test", prev))

	def test_uncommitted_writes_refuse_the_start_and_commit_nothing(self):
		b = self.make()
		self._production()
		self._writes(1)
		with patch.object(frappe.db, "commit") as commit, self.assertRaises(start_gate.UncommittedWrites):
			runner.start(b, USER)
		commit.assert_not_called()
		self.assertEqual(self.st(b), "Draft")
		self.enqueue.assert_not_called()

	def test_uncommitted_writes_refuse_a_resume_too(self):
		b = self.make(status="Paused")
		self._production()
		self._writes(2)
		with self.assertRaises(start_gate.UncommittedWrites):
			runner.resume(b)
		self.assertEqual(self.st(b), "Paused")

	def test_clean_transaction_starts(self):
		b = self.make()
		self._production()
		frappe.db.transaction_writes = 0
		runner.start(b, USER)
		self.assertEqual(self.st(b), "Running")

	def test_tests_are_exempt_so_fixtures_can_share_the_transaction(self):
		b = self.make()
		self.assertTrue(frappe.flags.in_test)
		self._writes(3)
		runner.start(b, USER)
		self.assertEqual(self.st(b), "Running")

	def test_api_entry_points_have_written_nothing_when_they_call_the_runner(self):
		"""start/resume (and the pause/cancel wrapper) only read, so the guard never trips on a real request."""
		seen = {}

		def spy(name):
			def _f(*a, **kw):
				seen[name] = frappe.db.transaction_writes
				return {}
			return _f

		b = self.make()
		frappe.db.transaction_writes = 0
		with patch.object(runner, "start", spy("start")), patch.object(runner, "resume", spy("resume")), \
			patch.object(mgmt, "_is_api_key_caller", return_value=False):
			mgmt.start_broadcast(b, confirm_count="3")
			frappe.db.commit()  # the start's audit comment is written after the runner returned
			mgmt.resume_broadcast(b)
		self.assertEqual(seen, {"start": 0, "resume": 0})


class TestFallbackShareIsReread(_Base):
	def test_a_broadcast_starting_mid_batch_slows_the_running_one(self):
		a = self.make(n=45, status="Running")
		self.addCleanup(lambda: frappe.cache().delete(runner._lock_key(a)))
		self.fake_send()
		patch.object(runner.gateway_bucket, "pace", return_value=False).start()
		share = patch.object(runner.gateway_bucket, "running_share", side_effect=[1, 2, 2]).start()
		with limit_override(ramp_first_batch=60, heartbeat_every_sends=20):
			self.assertEqual(runner.tick(a)["result"], "completed")
		self.assertEqual(share.call_count, 3)  # once per 20 sends inside the single 45-row batch
		slept = [round(c.args[0], 2) for c in self.sleep.call_args_list if c.args and c.args[0] > 0]
		self.assertEqual(slept[0], 0.05)  # alone: 20 mps
		self.assertEqual(slept[-1], 0.1)  # a second broadcast appeared: 10 mps each


class TestRestGuards(_Base):
	def _rest_save(self, name, **changes):
		frappe.flags.in_broadcast_api = False
		doc = frappe.get_doc(B, name)
		doc.update(changes)
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)

	def test_params_language_and_cost_are_api_only(self):
		b = self.make(body_params='["a"]', language_code="en")
		for field, value in (("body_params", '["b"]'), ("header_params", '{"link": "http://x"}'),
							 ("button_params", '[{"i": 1}]'), ("language_code", "fr"), ("cost_estimate", {"total": 0})):
			with self.subTest(field=field), self.assertRaises(frappe.PermissionError):
				self._rest_save(b, **{field: value})

	def test_same_json_as_object_or_string_is_not_a_change(self):
		b = self.make(body_params='["a", "b"]')
		self._rest_save(b, body_params='["a",  "b"]', title="renamed")
		self.assertEqual(frappe.db.get_value(B, b, "title"), "renamed")

	def test_new_row_cannot_carry_params(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": B, "title": "t", "gateway": GW, "body_params": '["x"]'}).insert(
				ignore_permissions=True, ignore_links=True, ignore_mandatory=True)

	def test_audience_picks_are_api_only(self):
		b = self.make()
		doc = frappe.get_doc(B, b)
		doc.append("audiences", {"audience": "NOPE", "tag_filter_mode": "any", "exclude": 0})
		doc.flags.ignore_links = True
		frappe.flags.in_broadcast_api = False
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_runner_writes_still_work(self):
		b = self.make(n=2)
		runner.start(b, USER)
		frappe.db.set_value(B, b, {"cost_estimate": "{}", "status": "Paused"})
		self._rest_save(b, title="still editable")


class TestAudienceRestGuards(AudienceTestCase):
	def _save(self, name, **changes):
		frappe.flags.in_audience_api = False
		doc = frappe.get_doc(aud_doctype(), name)
		doc.update(changes)
		doc.save(ignore_permissions=True)

	def test_counters_and_adhoc_flag_are_api_only(self):
		name = self.make()
		for field, value in (("member_count", 99), ("suppressed_count", 5), ("is_adhoc", 1)):
			with self.subTest(field=field), self.assertRaises(frappe.PermissionError):
				self._save(name, **{field: value})

	def test_audience_cannot_be_created_outside_the_api(self):
		frappe.flags.in_audience_api = False
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": aud_doctype(), "gateway": "GW-AUD-TEST", "title": "x", "consent_source": "form",
							"purpose_marketing": 1}).insert(ignore_permissions=True, ignore_links=True)

	def test_title_edit_and_api_counter_refresh_still_work(self):
		name = self.make()
		self._save(name, title="Renamed")
		frappe.db.set_value(aud_doctype(), name, "member_count", 4)  # membership code uses set_value
		self.assertEqual(frappe.db.get_value(aud_doctype(), name, "title"), "Renamed")

	def test_members_stay_fully_guarded(self):
		name = self.make()
		frappe.flags.in_audience_api = False
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": "WhatsApp Audience Member", "audience": name, "recipient": "15550009999"}).insert(
				ignore_permissions=True, ignore_links=True)


def aud_doctype() -> str:
	return "WhatsApp Audience"


if __name__ == "__main__":
	unittest.main()


class TestReviewFollowUps(AudienceTestCase):
	def test_uncommitted_writes_is_a_clean_start_refusal_not_a_500(self):
		self.assertTrue(issubclass(start_gate.UncommittedWrites, start_gate.StartRefused))
		err = start_gate.UncommittedWrites("pending writes")
		self.assertEqual(err.code, "uncommitted_writes")

	def test_audience_create_and_delete_restore_the_api_flag(self):
		frappe.flags.in_audience_api = False
		name = self.make("Flag restore")
		self.assertFalse(frappe.flags.get("in_audience_api"))
		self.assertTrue(aud_api.delete_audience(name)["success"])
		self.assertFalse(frappe.flags.get("in_audience_api"))

	def test_unchanged_empty_json_is_not_a_change(self):
		from huf.huf.doctype.whatsapp_broadcast.whatsapp_broadcast import _json_value
		for empty in (None, "", "  ", "[]", "{}", [], {}):
			self.assertIsNone(_json_value(empty), empty)
		self.assertEqual(_json_value('["a"]'), ["a"])
		self.assertEqual(_json_value({"x": 1}), {"x": 1})
