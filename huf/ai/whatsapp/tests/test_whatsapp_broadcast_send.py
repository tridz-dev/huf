# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WP-4: broadcast_send.send_one is crash-safe (claim before POST, ambiguous => unknown, never resent).

The recipient/broadcast rows live in an in-memory store that mimics the conditional-UPDATE semantics of the
real helpers (``_claim`` / ``_write`` / ``_release``), so these tests need no database rows. The Graph POST
is ``bridge.send_template`` mocked. ``whatsapp_errors.is_pause_signal`` / ``should_defer_24h`` come from WP-3;
the real implementations from whatsapp_errors are used.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from huf.ai.gateway_adapters import whatsapp_bridge as bridge
from huf.ai.gateway_adapters import whatsapp_errors as errors
from huf.ai.whatsapp.broadcast import policy as bpolicy
from huf.ai.whatsapp.broadcast import send as bs
from huf.ai.whatsapp import outbound_policy as policy

ROW = "BCAST-00001-15550001111"
BC = "BCAST-00001"


class _Store:
	def __init__(self, **row_over):
		self.row = {
			"name": ROW, "broadcast": BC, "recipient": "15550001111", "status": "queued", "attempts": 0,
			"params": None, "opaque_ref": ROW, "wamid": None,
		}
		self.row.update(row_over)
		self.bc = {
			"name": BC, "status": "Running", "gateway": "GW", "whatsapp_account": "ACC", "template": "promo-en_US",
			"language_code": "en_US", "body_params": '["Default"]', "header_params": None, "button_params": None,
			"max_recipients": 1000,
		}
		self.write_hook = None

	def claim(self, name):
		if self.row["status"] in ("queued", "deferred") and self.row["attempts"] < bpolicy.get("max_attempts"):
			self.row["status"] = "sending"
			self.row["attempts"] += 1
			return True
		return False

	def release(self, name, prior_status="queued", prior_next_attempt_at=None, cancelled=False):
		if self.row["status"] == "sending":
			self.row.update(status=prior_status or "queued", attempts=max(self.row["attempts"] - 1, 0))
			if cancelled:
				self.row.update(status="skipped", skip_reason="cancelled")

	def write(self, name, **fields):
		if self.write_hook:
			self.write_hook(fields)
		if self.row["status"] == "sending":
			self.row.update(fields)
			return True
		return False


class _Base(unittest.TestCase):
	def setUp(self):
		self.addCleanup(patch.stopall)
		self.store = _Store()
		s = self.store
		patch.object(bs, "_claim", side_effect=s.claim).start()
		patch.object(bs, "_release", side_effect=s.release).start()
		patch.object(bs, "_write", side_effect=s.write).start()
		patch.object(bs, "_load", side_effect=lambda n: dict(s.row)).start()
		patch.object(bs, "_template_row", side_effect=lambda n: {"status": "APPROVED", "category": s.bc.get("category", "UTILITY")}).start()
		patch.object(bs, "_load_broadcast", side_effect=lambda n: dict(s.bc)).start()
		patch.object(bs, "_started_count", return_value=1).start()
		patch.object(bs.frappe.db, "rollback", create=True).start()
		patch.object(bs.frappe.db, "commit", create=True).start()
		patch.object(errors, "is_pause_signal", create=True, side_effect=lambda c: c in (132015, 135000)).start()
		patch.object(errors, "should_defer_24h", create=True, side_effect=lambda c: c == 131049).start()
		self.check = patch.object(policy, "check_recipient", return_value=None).start()
		self.post = patch.object(bridge, "send_template", return_value={"wamid": "wamid.1", "message_status": "accepted"}).start()
		bs.frappe.flags.broadcast_pause = None

	def _graph_error(self, code, msg="boom"):
		return bridge.BridgeError({"success": False, "error": "send_failed", "graph_code": code, "message": msg})


class TestHappyPath(_Base):
	def test_sent_stores_wamid_and_message_status_and_forces_graph(self):
		self.post.return_value = {"wamid": "wamid.9", "message_status": "held_for_quality_assessment"}
		self.assertEqual(bs.send_one(ROW), "sent")
		r = self.store.row
		self.assertEqual((r["status"], r["wamid"], r["message_status"]), ("sent", "wamid.9", "held_for_quality_assessment"))
		self.assertEqual(r["attempts"], 1)
		kw = self.post.call_args.kwargs
		self.assertTrue(kw["force_graph"])
		self.assertEqual(kw["opaque_ref"], ROW)
		self.assertEqual(kw["gateway_name"], "GW")
		self.assertEqual(self.post.call_args.args[:3], ("ACC", "15550001111", "promo-en_US"))
		self.assertEqual(self.post.call_args.args[3], ["Default"])

	def test_recipient_params_override_defaults(self):
		self.store.row["params"] = '{"body": ["Alice"]}'
		bs.send_one(ROW)
		self.assertEqual(self.post.call_args.args[3], ["Alice"])

	def test_second_call_after_sent_is_lost_claim_no_post(self):
		bs.send_one(ROW)
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)

	def test_never_imports_legacy_tool_send(self):
		import inspect

		self.assertNotIn("tools.whatsapp", inspect.getsource(bs).replace('"""', "").split("import frappe", 1)[1])


class TestGuards(_Base):
	def test_broadcast_not_running_releases_row_and_posts_nothing(self):
		for status in ("Paused", "Draft"):
			self.store.bc["status"] = status
			self.assertEqual(bs.send_one(ROW), "lost_claim")
			self.assertEqual(self.store.row["status"], "queued")
			self.assertEqual(self.store.row["attempts"], 0)
		self.post.assert_not_called()

	def test_opted_out_is_skipped_and_not_posted(self):
		self.check.side_effect = policy.OutboundRefused("stopped", "opted_out")
		self.assertEqual(bs.send_one(ROW), "skipped")
		self.assertEqual((self.store.row["status"], self.store.row["skip_reason"]), ("skipped", "opted_out"))
		self.post.assert_not_called()

	def test_marketing_stop_refusal_from_bridge_is_skipped(self):
		self.post.side_effect = bridge.BridgeError({"success": False, "error": "marketing_opted_out", "message": "x"})
		self.assertEqual(bs.send_one(ROW), "skipped")
		self.assertEqual(self.store.row["skip_reason"], "marketing_opted_out")

	def test_max_recipients_cap(self):
		self.store.bc["max_recipients"] = 1
		with patch.object(bs, "_started_count", return_value=2):
			self.assertEqual(bs.send_one(ROW), "skipped")
		self.assertEqual(self.store.row["skip_reason"], "max_recipients")
		self.post.assert_not_called()

	def test_attempts_cap_five_gives_up_failed_without_post(self):
		self.store.row.update(status="deferred", attempts=5)
		with patch.object(bs.frappe.db, "sql", create=True):
			self.assertEqual(bs.send_one(ROW), "failed")
		self.post.assert_not_called()


class TestErrors(_Base):
	def test_131049_is_terminal_skipped_not_deferred(self):
		self.post.side_effect = self._graph_error(131049)
		self.assertEqual(bs.send_one(ROW), "skipped")
		self.assertEqual(self.store.row["status"], "skipped")
		self.assertEqual(self.store.row["skip_reason"], "per_user_marketing_limit")
		self.assertEqual(self.store.row["error_code"], 131049)
		self.assertNotIn("next_attempt_at", self.store.row)
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)

	def test_retryable_defers_with_backoff_and_counts_attempt(self):
		self.post.side_effect = self._graph_error(130429)
		with patch.object(bs, "_later", side_effect=lambda s: ("later", s)):
			self.assertEqual(bs.send_one(ROW), "deferred")
		self.assertEqual(self.store.row["status"], "deferred")
		self.assertEqual(self.store.row["attempts"], 1)
		self.assertTrue(0 < self.store.row["next_attempt_at"][1] <= 5)
		# redeliverable: a deferred row can be claimed again
		self.post.side_effect = None
		self.assertEqual(bs.send_one(ROW), "sent")
		self.assertEqual(self.store.row["attempts"], 2)

	def test_retryable_gives_up_failed_at_attempt_cap(self):
		self.store.row.update(status="deferred", attempts=4)  # claim makes this the 5th and last POST
		self.post.side_effect = self._graph_error(130429)
		self.assertEqual(bs.send_one(ROW), "failed")
		self.assertEqual(self.store.row["status"], "failed")

	def test_permanent_fails(self):
		self.post.side_effect = self._graph_error(131026, "undeliverable")
		self.assertEqual(bs.send_one(ROW), "failed")
		r = self.store.row
		self.assertEqual((r["status"], r["error_code"]), ("failed", 131026))
		self.assertIsNone(bs.frappe.flags.broadcast_pause)

	def test_pause_signal_sets_flag_and_fails(self):
		self.post.side_effect = self._graph_error(135000)
		self.assertEqual(bs.send_one(ROW), "failed")
		self.assertEqual(bs.frappe.flags.broadcast_pause, "meta_error_135000")

	def test_expired_token_pauses_and_keeps_the_row_sendable(self):
		self.post.side_effect = self._graph_error(190, "Authentication Error")
		with patch.object(bs, "_later", side_effect=lambda s: ("later", s)):
			self.assertEqual(bs.send_one(ROW), "deferred")
		r = self.store.row
		self.assertEqual((r["status"], r["error_code"]), ("deferred", 190))
		self.assertEqual(r["attempts"], 0)  # the attempt never reached the recipient
		self.assertEqual(bs.frappe.flags.broadcast_pause, "meta_error_190")
		# after the token is fixed the same row sends
		self.post.side_effect = None
		self.assertEqual(bs.send_one(ROW), "sent")

	def test_policy_refusal_before_post_fails_not_unknown(self):
		self.post.side_effect = bridge.BridgeError({"success": False, "error": "validation_failed", "message": "bad"})
		self.assertEqual(bs.send_one(ROW), "failed")

	def test_timeout_is_unknown_and_never_resent(self):
		self.post.side_effect = bridge.BridgeError({"success": False, "error": "send_failed", "graph_code": None, "message": "timed out"})
		self.assertEqual(bs.send_one(ROW), "unknown")
		self.assertEqual(self.store.row["status"], "unknown")
		self.post.side_effect = None
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)

	def test_unexpected_exception_after_post_attempt_is_unknown(self):
		self.post.side_effect = ConnectionError("reset")
		self.assertEqual(bs.send_one(ROW), "unknown")


class TestFaultInjection(_Base):
	def test_a_crash_after_claim_commit_before_post_stays_sending_and_is_never_resent(self):
		self.check.side_effect = RuntimeError("worker killed")  # raised after the claim, before the POST
		with self.assertRaises(RuntimeError):
			bs.send_one(ROW)
		self.assertEqual(self.store.row["status"], "sending")  # runner's resume_stale reaps this to unknown
		self.check.side_effect = None
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.post.assert_not_called()

	def test_b_post_succeeded_but_wamid_write_raises_row_not_queued_and_no_resend(self):
		calls = {"n": 0}

		def hook(fields):
			calls["n"] += 1
			if calls["n"] == 1:  # the status='sent' write
				raise RuntimeError("db gone")

		self.store.write_hook = hook
		self.assertEqual(bs.send_one(ROW), "unknown")
		self.assertEqual(self.store.row["status"], "unknown")
		self.assertEqual(self.store.row["wamid"], "wamid.1")
		self.assertEqual(self.post.call_count, 1)
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)

	def test_b2_both_writes_fail_row_stays_sending_not_queued(self):
		def hook(fields):
			raise RuntimeError("db gone")

		self.store.write_hook = hook
		with self.assertRaises(RuntimeError):
			bs.send_one(ROW)
		self.assertEqual(self.store.row["status"], "sending")
		self.store.write_hook = None
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)

	def test_double_claim_only_one_post(self):
		self.assertEqual(bs.send_one(ROW), "sent")
		self.assertEqual(bs.send_one(ROW), "lost_claim")
		self.assertEqual(self.post.call_count, 1)


if __name__ == "__main__":
	unittest.main()
