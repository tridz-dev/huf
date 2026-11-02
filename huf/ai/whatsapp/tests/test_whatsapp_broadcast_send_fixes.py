# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""FIX-A: attempts cap (5 POSTs), _release restores prior status, template fail-closed, 131050 consent, cancel."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.whatsapp.broadcast import send as bs
from huf.ai.whatsapp import account_events
from huf.ai.whatsapp.tests.test_whatsapp_broadcast_send import BC, ROW, _Base

_REAL_RELEASE = bs._release  # _Base.setUp replaces bs._release with the in-memory fake


class TestAttemptsCap(_Base):
	def test_retryable_error_allows_fifth_attempt(self):
		self.store.row.update(status="deferred", attempts=3)  # claim -> 4: still retryable
		self.post.side_effect = self._graph_error(130429)
		self.assertEqual(bs.send_one(ROW), "deferred")
		self.assertEqual(self.store.row["attempts"], 4)

	def test_five_posts_then_failed(self):
		self.post.side_effect = self._graph_error(130429)
		with patch.object(bs, "_later", side_effect=lambda s: s):
			outcomes = [bs.send_one(ROW) for _ in range(6)]
		self.assertEqual(outcomes, ["deferred"] * 4 + ["failed", "lost_claim"])
		self.assertEqual(self.post.call_count, 5)

	def test_backoff_uses_real_attempt_count(self):
		self.store.row.update(attempts=0)
		self.post.side_effect = self._graph_error(130429)
		with patch.object(bs.errors, "backoff_seconds", return_value=7) as bo:
			bs.send_one(ROW)
		self.assertEqual(bo.call_args.args[1], 1)


class TestRelease(_Base):
	def test_release_sql_restores_deferred_with_next_attempt(self):
		with patch.object(bs.frappe.db, "sql", create=True) as sql, patch.object(bs.frappe.db, "commit", create=True):
			_REAL_RELEASE(ROW, "deferred", "2030-01-01 00:00:00")
		args = sql.call_args.args
		self.assertIn("status=%s", args[0])
		self.assertEqual(args[1], ("deferred", "2030-01-01 00:00:00", ROW))

	def test_release_sql_queued_stays_queued(self):
		with patch.object(bs.frappe.db, "sql", create=True) as sql, patch.object(bs.frappe.db, "commit", create=True):
			_REAL_RELEASE(ROW, "queued", None)
		self.assertEqual(sql.call_args.args[1], ("queued", None, ROW))

	def test_release_sql_cancelled_is_skipped(self):
		with patch.object(bs.frappe.db, "sql", create=True) as sql, patch.object(bs.frappe.db, "commit", create=True):
			_REAL_RELEASE(ROW, "deferred", "x", cancelled=True)
		self.assertIn("skip_reason='cancelled'", sql.call_args.args[0])

	def test_send_one_passes_prior_state_when_paused(self):
		self.store.row.update(status="deferred", attempts=1, next_attempt_at="LATER")
		self.store.bc["status"] = "Paused"
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.store.row["status"], "deferred")
		self.assertEqual(self.store.row["attempts"], 1)

	def test_send_one_cancelled_skips_row(self):
		self.store.bc["status"] = "Cancelled"
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual((self.store.row["status"], self.store.row["skip_reason"]), ("skipped", "cancelled"))
		self.post.assert_not_called()


class TestTemplateFailClosed(_Base):
	def _assert_closed(self):
		self.assertEqual(bs.send_one(ROW), "failed")
		self.assertEqual(self.store.row["status"], "failed")
		self.assertIn("template_missing", self.store.row["error_message"])
		self.assertEqual(bs.frappe.flags.broadcast_pause, "template_missing")
		self.post.assert_not_called()

	def test_missing_template_row(self):
		with patch.object(bs, "_template_row", return_value=None):
			self._assert_closed()

	def test_unreadable_category(self):
		with patch.object(bs, "_template_row", return_value={"status": "APPROVED", "category": None}):
			self._assert_closed()

	def test_lookup_error(self):
		with patch.object(bs, "_template_row", side_effect=RuntimeError("db")):
			self._assert_closed()


class TestMarketingStopAndErrorCode(_Base):
	def test_131050_records_marketing_stop_then_fails(self):
		self.post.side_effect = self._graph_error(131050)
		with patch.object(account_events, "record_user_preferences", return_value=1) as rec:
			self.assertEqual(bs.send_one(ROW), "failed")
		gw, items = rec.call_args.args
		self.assertEqual(gw, "GW")
		self.assertEqual((items[0]["category"], items[0]["value"], items[0]["wa_id"]), (account_events.MARKETING, "stop", "15550001111"))
		self.assertEqual(self.store.row["status"], "failed")

	def test_131050_consent_failure_does_not_strand_row(self):
		self.post.side_effect = self._graph_error(131050)
		with patch.object(account_events, "record_user_preferences", side_effect=RuntimeError("x")), patch.object(bs.frappe, "log_error", create=True):
			self.assertEqual(bs.send_one(ROW), "failed")
		self.assertEqual(self.store.row["status"], "failed")

	def test_other_errors_do_not_record_consent(self):
		self.post.side_effect = self._graph_error(131026)
		with patch.object(account_events, "record_user_preferences") as rec:
			bs.send_one(ROW)
		rec.assert_not_called()

	def test_mm_refusal_has_no_string_error_code(self):
		self.store.bc.update(send_via="marketing_messages", category="UTILITY")
		bs.send_one(ROW)
		self.assertNotIsInstance(self.store.row.get("error_code"), str)
