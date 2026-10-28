# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-H: fixes from the final review (start/audience race, deferral window, limits read, audit, consent)."""

from __future__ import annotations

import json
from unittest.mock import patch

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from huf.ai.whatsapp.broadcast import api_limits, limits, policy, runner, send as broadcast_send
from huf.ai.whatsapp.broadcast.audiences import api as aud_api, wiring
from huf.ai.whatsapp.broadcast.audiences import membership as aud
from huf.ai.whatsapp.broadcast.checks import start_gate
from huf.ai.whatsapp.tests.broadcast_policy_helper import limit_override
from huf.ai.whatsapp.tests.test_whatsapp_audience_api import GW as AGW, AudienceTestCase
from huf.ai.whatsapp.tests.test_whatsapp_audience_wiring import N, WiringCase
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_runner import USER, B, R, _Base, _preview

SETTINGS = policy.SETTINGS


def _w(code):
	return {"code": code, "message": code, "limit_key": None}


class TestStartRaceRecheck(_Base):
	def test_changed_count_after_lock_refuses(self):
		b = self.make(n=3)
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(b, USER, [], expected_count=2)
		self.assertEqual(cm.exception.code, "recipients_changed")
		self.assertEqual(self.st(b), "Draft")
		self.enqueue.assert_not_called()

	def test_row_added_between_preview_and_lock_refuses(self):
		b = self.make(n=3)
		calls = []

		def sneaky(_b):
			if not calls:  # the first (pre-lock) preview; a rival then adds a row
				self.row(b, "15559990000")
			calls.append(1)
			return _preview()

		self.preview.side_effect = sneaky
		with self.assertRaises(runner.StartRefused) as cm:
			runner.start(b, USER, [], expected_count=3)
		self.assertEqual(cm.exception.code, "recipients_changed")
		self.assertEqual(self.st(b), "Draft")

	def test_matching_count_starts_and_preview_runs_again_after_lock(self):
		b = self.make(n=3)
		runner.start(b, USER, [], expected_count=3)
		self.assertEqual(self.st(b), "Running")
		self.assertEqual(self.preview.call_count, 2)

	def test_purpose_rechecked_after_lock(self):
		b = self.make(n=2)
		issue = {"code": "audience_purpose_mismatch", "message": "no", "limit_key": None}
		with patch.object(start_gate.audience_check, "purpose_issues", return_value=[issue]) as pi:
			with self.assertRaises(runner.StartRefused) as cm:
				runner.start(b, USER, [], expected_count=2)
		self.assertEqual(cm.exception.code, "audience_purpose_mismatch")
		pi.assert_called_once()
		self.assertEqual(self.st(b), "Draft")


class TestSetAudiencesLocksAndRechecks(WiringCase):
	def test_not_draft_after_lock_is_refused(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		stale = {"gateway": GW_, "status": "Draft", "category": "UTILITY"}
		frappe.db.set_value("WhatsApp Broadcast", b, "status", "Running")  # a start won the race
		with patch.object(wiring.broadcast_api, "_require_broadcast_write", return_value=dict(stale)):
			out = self.wire(b, [{"audience": a}])
		self.assertEqual(out.get("error"), "not_draft")
		self.assertEqual(self.rows(b), [])

	def test_status_read_takes_the_row_lock(self):
		a = self.make("A")
		self.fill(a, N[0])
		b = self.bc()
		real = frappe.db.get_value
		seen = []

		def spy(*args, **kw):
			if args[:1] == ("WhatsApp Broadcast",) and kw.get("for_update"):
				seen.append(args)
			return real(*args, **kw)

		with patch.object(frappe.db, "get_value", spy):
			self.wire(b, [{"audience": a}])
		self.assertTrue(any("status" in x for x in seen), seen)

	def test_attesters_are_kept_on_the_broadcast(self):
		a = self.make("Spring")
		self.fill(a, N[0], N[1])
		b = self.bc()
		out = self.wire(b, [{"audience": a}])
		self.assertTrue(out["success"], out)
		src = frappe.db.get_value("WhatsApp Broadcast", b, "consent_source")
		self.assertIn("Spring", src)
		self.assertIn("(attested by Administrator)", src)


GW_ = AGW


class TestOverBudgetDeferral(_Base):
	def _deferred(self, b):
		return frappe.get_all(R, {"broadcast": b, "next_attempt_at": ["is", "set"]}, pluck="name")

	def test_remaining_is_taken_after_the_lock(self):
		b = self.make(n=3)
		first = _preview(warnings=[_w("over_budget")], remaining_24h=3)
		second = _preview(warnings=[_w("over_budget")], remaining_24h=1)
		self.preview.side_effect = [first, second]
		with patch.object(runner.broadcast_limits, "oldest_counted_send", return_value=None):
			out = runner.start(b, USER, ["over_budget"], expected_count=3)
		self.assertEqual(out["deferred_over_budget"], 2)
		self.assertEqual(len(self._deferred(b)), 2)

	def test_hold_ends_when_oldest_counted_send_leaves_the_window(self):
		b = self.make(n=3)
		self.preview.return_value = _preview(warnings=[_w("over_budget")], remaining_24h=1)
		oldest = add_to_date(now_datetime(), hours=-20)
		with patch.object(runner.broadcast_limits, "oldest_counted_send", return_value=oldest):
			runner.start(b, USER, ["over_budget"])
		when = get_datetime(frappe.db.get_value(R, self._deferred(b)[0], "next_attempt_at"))
		self.assertLess(abs((when - add_to_date(oldest, hours=24)).total_seconds()), 5)

	def test_fallback_is_now_plus_window_and_follows_the_registry(self):
		b = self.make(n=2)
		self.preview.return_value = _preview(warnings=[_w("over_budget")], remaining_24h=1)
		with patch.object(runner.broadcast_limits, "oldest_counted_send", return_value=None), \
			limit_override(over_budget_hold_hours=48):
			runner.start(b, USER, ["over_budget"])
		when = get_datetime(frappe.db.get_value(R, self._deferred(b)[0], "next_attempt_at"))
		self.assertLess(abs((when - add_to_date(now_datetime(), hours=48)).total_seconds()), 10)

	def test_hold_window_and_chunk_are_internal_registry_rows(self):
		for key, default in (("over_budget_hold_hours", 24), ("defer_chunk", 1000)):
			lim = policy.BY_KEY[key]
			self.assertEqual((lim.kind, lim.default, lim.editable), ("internal", default, False))
			self.assertIn(f"`{key}`", policy.render_docs())

	def test_defer_chunk_size_is_used(self):
		b = self.make(n=5)
		with limit_override(defer_chunk=2), patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
			start_gate.defer_over_budget(b, 0)
		updates = [c for c in sql.call_args_list if str(c.args[0]).lstrip().startswith("update")]
		self.assertEqual(len(updates), 3)


class TestRemainingInternals(_Base):
	def test_all_listed_internals_are_registered_read_only(self):
		for key in (
			"progress_throttle_seconds", "api_rate_window_seconds", "consent_source_max",
			"member_consent_source_max", "audience_delete_chunk",
		):
			lim = policy.BY_KEY[key]
			self.assertEqual(lim.kind, "internal")
			self.assertFalse(lim.editable)
			meta = frappe.get_meta(SETTINGS)
			self.assertIsNone(meta.get_field(key))


class TestLimitsReadAuthority(_Base):
	def test_unknown_broadcast_is_not_open_access(self):
		with patch.object(api_limits.frappe, "has_permission", return_value=False), \
			patch.object(api_limits.frappe, "get_roles", return_value=["Guest"]):
			with self.assertRaises(frappe.PermissionError):
				api_limits.get_broadcast_limits(broadcast="NO-SUCH-BROADCAST")

	def test_unknown_broadcast_falls_to_the_gateway_check_for_readers(self):
		with patch.object(api_limits.frappe, "has_permission", return_value=True):
			out = api_limits.get_broadcast_limits(broadcast="NO-SUCH-BROADCAST")
		self.assertTrue(out["success"])


class TestSettingsAudit(_Base):
	def _comments(self):
		return frappe.get_all(
			"Comment", {"reference_doctype": SETTINGS, "reference_name": SETTINGS, "content": ["like", "limits changed%"]},
			pluck="content",
		)

	def test_desk_save_writes_the_comment(self):
		before = len(self._comments())
		doc = frappe.get_doc(SETTINGS)
		doc.max_csv_mb = "3"
		doc.save(ignore_permissions=True)
		after = self._comments()
		self.assertEqual(len(after), before + 1)
		self.assertIn("max_csv_mb=3", " ".join(after))

	def test_api_update_writes_exactly_one_comment(self):
		before = len(self._comments())
		out = api_limits.update_broadcast_limits(values={"max_csv_mb": 4})
		self.assertTrue(out["success"], out)
		self.assertEqual(len(self._comments()), before + 1)

	def test_unchanged_save_writes_none(self):
		doc = frappe.get_doc(SETTINGS)
		doc.save(ignore_permissions=True)
		before = len(self._comments())
		frappe.get_doc(SETTINGS).save(ignore_permissions=True)
		self.assertEqual(len(self._comments()), before)


class TestAudienceConsentSourceFrozen(AudienceTestCase):
	def test_editable_when_unused(self):
		a = self.make("Free")
		out = aud_api.update_audience(audience=a, consent_source="new text")
		self.assertTrue(out.get("success"), out)

	def test_blocked_while_an_unfinished_broadcast_uses_it(self):
		a = self.make("Busy")
		self.draft_broadcast(a)
		try:
			out = aud_api.update_audience(audience=a, consent_source="changed")
		except frappe.ValidationError:
			out = {"success": False}
		self.assertFalse(out.get("success"))
		self.assertEqual(frappe.db.get_value(aud.AUDIENCE, a, "consent_source"), "signup form")

	def test_blocked_when_a_finished_broadcast_relied_on_it(self):
		a = self.make("Relied")
		b = self.draft_broadcast(a, status="Completed")
		frappe.db.set_value(
			"WhatsApp Broadcast", b,
			{"consent_attested": 1, "consent_source": "Audiences: Relied (attested by Administrator)"},
		)
		frappe.flags.in_broadcast_api = True
		frappe.get_doc({"doctype": R, "broadcast": b, "recipient": "447900000099", "status": "sent",
			"audience": a}).insert(ignore_permissions=True, ignore_links=True, ignore_mandatory=True)  # fmt: skip
		try:
			out = aud_api.update_audience(audience=a, consent_source="rewritten history")
		except frappe.ValidationError:
			out = {"success": False}
		self.assertFalse(out.get("success"))
		self.assertEqual(frappe.db.get_value(aud.AUDIENCE, a, "consent_source"), "signup form")


class TestBroadcastDefaultsFollowSettings(_Base):
	def test_doctype_has_no_hard_defaults(self):
		meta = frappe.get_meta(B)
		self.assertFalse(meta.get_field("mps").default)
		self.assertFalse(meta.get_field("max_recipients").default)

	def test_new_broadcast_uses_the_settings(self):
		b = self.make(n=0)
		doc = frappe.get_doc(B, b)
		self.assertFalse(doc.mps)
		self.assertFalse(doc.max_recipients)
		self.assertEqual(policy.resolve("default_mps", doc), (20, "default"))
		self.assertEqual(policy.resolve("max_recipients_default", doc), (1000, "default"))
		policy.set_values({"default_mps": 33, "max_recipients_default": 77})
		self.addCleanup(lambda: policy.set_values({"default_mps": None, "max_recipients_default": None}))
		self.assertEqual(policy.resolve("default_mps", doc), (33, "settings"))
		self.assertEqual(policy.resolve("max_recipients_default", doc), (77, "settings"))

	def test_explicit_per_broadcast_value_still_wins(self):
		b = self.make(n=0, mps=5, max_recipients=9)
		doc = frappe.get_doc(B, b)
		self.assertEqual(policy.resolve("default_mps", doc), (5, "broadcast"))
		self.assertEqual(policy.resolve("max_recipients_default", doc), (9, "broadcast"))

	def test_send_cap_falls_back_to_the_setting(self):
		from huf.ai.whatsapp.broadcast.recipients import effective_cap

		with limit_override(max_recipients_default=7):
			self.assertEqual(effective_cap({"name": "x", "max_recipients": None}), 7)
		self.assertEqual(effective_cap({"name": "x", "max_recipients": 3}), 3)


class TestResumeKeepsAcknowledgedWarnings(_Base):
	def _paused(self, acked):
		b = self.make(n=3, status="Paused")
		start_gate.record_acknowledged(b, acked)
		return b

	def test_resume_with_the_same_warnings_runs(self):
		b = self._paused(["quality_red"])
		self.preview.return_value = _preview(warnings=[_w("quality_red")])
		runner.resume(b)
		self.assertEqual(self.st(b), "Running")

	def test_resume_with_a_vanished_warning_runs(self):
		b = self._paused(["quality_red"])
		runner.resume(b)
		self.assertEqual(self.st(b), "Running")

	def test_resume_with_a_new_warning_is_refused(self):
		b = self._paused(["quality_yellow"])
		self.preview.return_value = _preview(warnings=[_w("quality_yellow"), _w("quality_red")])
		with self.assertRaises(runner.StartRefused) as cm:
			runner.resume(b)
		self.assertEqual(cm.exception.code, "warnings_changed")
		self.assertEqual(self.st(b), "Paused")

	def test_start_records_the_acknowledged_codes(self):
		b = self.make(n=1)
		self.preview.return_value = _preview(warnings=[_w("quality_red")])
		runner.start(b, USER, ["quality_red"])
		self.assertEqual(start_gate.stored_acknowledged(b), {"quality_red"})

	def test_resume_reapplies_the_over_budget_hold(self):
		b = self._paused(["over_budget"])
		self.preview.return_value = _preview(warnings=[_w("over_budget")], remaining_24h=1)
		with patch.object(runner.broadcast_limits, "oldest_counted_send", return_value=None):
			out = runner.resume(b)
		self.assertEqual(out["deferred_over_budget"], 2)
