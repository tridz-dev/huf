"""Integration tests for confirm-before-send (HUFCRM-06a). Run: bench run-tests --module huf.ai.tests.test_tool_confirmation"""

import hashlib
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import tool_confirmation as tc
from huf.ai.gateways import tool_policy
from huf.ai.tools.invocation import ToolResult

ARGS = {"recipients": ["+911", "+912"], "template": "promo", "message": "Hi there", "channel": "whatsapp"}


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "N06", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
	return email


class TestToolConfirmation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.other = _ensure_user("n06-other@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _park(self, args=None):
		# agent_run_id=None and no gateway context == a plain web/mobile run
		out = tool_policy.check_tool_call("send_campaign", dict(args or ARGS), None, True, conversation_id=None)
		return json.loads(out)

	def test_web_run_is_parked_not_executed(self):
		with patch.object(tc, "_execute") as ex:
			req = self._park()
		ex.assert_not_called()
		self.assertEqual(req["type"], "confirmation_request")
		self.assertEqual(req["state"], "pending")
		self.assertEqual(req["summary"]["recipient_count"], 2)
		self.assertEqual(req["summary"]["template"], "promo")
		self.assertEqual(req["summary"]["channel"], "whatsapp")
		row = frappe.get_doc(tc.DOCTYPE, req["id"])
		self.assertEqual(row.user, "Administrator")
		self.assertEqual(row.args_hash, tc.args_hash(ARGS))
		self.assertNotEqual(row.args_hash, hashlib.sha256(json.dumps(ARGS, sort_keys=True, separators=(',', ':')).encode()).hexdigest())

	def test_flag_off_web_run_proceeds(self):
		self.assertIsNone(tool_policy.check_tool_call("send_campaign", dict(ARGS), None, False))

	def test_fail_closed_when_park_breaks(self):
		with patch.object(tc, "park", side_effect=RuntimeError("x")):
			out = json.loads(tool_policy.check_tool_call("send_campaign", dict(ARGS), None, True))
		self.assertTrue(out["denied"])

	def test_wrong_user_cannot_approve(self):
		req = self._park()
		frappe.set_user(self.other)
		with self.assertRaises(tc.Forbidden):
			tc.decide(req["id"], True)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "pending")

	def test_approve_enqueues_then_job_executes_once_and_audits(self):
		req = self._park()
		with patch.object(tc, "assert_user_may_run"), patch.object(frappe, "enqueue") as enq, patch.object(
			tc, "_execute", return_value=ToolResult(success=True, result={"sent": 2})
		) as ex:
			out = tc.decide(req["id"], True)
			ex.assert_not_called()  # decide() never runs the tool in the HTTP request
			enq.assert_called_once()
			self.assertEqual(enq.call_args.kwargs["queue"], "long")
			self.assertTrue(enq.call_args.kwargs["enqueue_after_commit"])
			self.assertEqual(out["confirmation"]["state"], "approved")
			with self.assertRaises(tc.AlreadyDecided):  # replay
				tc.decide(req["id"], True)
			tc.run_approved(req["id"], "Administrator")
			tc.run_approved(req["id"], "Administrator")  # duplicate job is a no-op
			ex.assert_called_once()
			self.assertEqual(ex.call_args[0][1]["template"], "promo")
		row = frappe.get_doc(tc.DOCTYPE, req["id"])
		self.assertEqual(row.state, "executed")
		self.assertEqual((row.decision, row.decided_by), ("Approved", "Administrator"))
		self.assertTrue(row.decided_at)
		self.assertFalse(row.raw_args)  # raw args cleared, hash + redacted kept
		self.assertTrue(row.args_hash and row.redacted_args)

	def test_deny_does_not_execute(self):
		req = self._park()
		with patch.object(tc, "_execute") as ex:
			out = tc.decide(req["id"], "false")
		ex.assert_not_called()
		self.assertEqual(out["confirmation"]["state"], "denied")
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "decision"), "Denied")

	def test_expired_rejected(self):
		req = self._park()
		frappe.db.set_value(tc.DOCTYPE, req["id"], "expires_at", add_to_date(now_datetime(), minutes=-1))
		with patch.object(tc, "_execute") as ex, self.assertRaises(tc.Expired):
			tc.decide(req["id"], True)
		ex.assert_not_called()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "expired")
		with self.assertRaises(tc.Expired):
			tc.decide(req["id"], True)

	def test_args_changed_rejected(self):
		req = self._park()
		tampered = dict(ARGS, recipients=["+911", "+912", "+913"])
		frappe.db.set_value(tc.DOCTYPE, req["id"], "raw_args", json.dumps(tampered))
		with patch.object(tc, "assert_user_may_run"), patch.object(tc, "_execute") as ex, patch.object(
			frappe, "enqueue"
		), self.assertRaises(tc.ArgsChanged):
			tc.decide(req["id"], True)
		ex.assert_not_called()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "failed")

	def test_permission_recheck_blocks_execution(self):
		req = self._park()
		with patch.object(tc, "assert_user_may_run", side_effect=tc.RoleDenied("lost")), patch.object(
			tc, "_execute"
		) as ex, self.assertRaises(tc.RoleDenied):
			tc.decide(req["id"], True)
		ex.assert_not_called()

	def test_get_pending_scoped_to_user(self):
		req = self._park()
		self.assertIn(req["id"], [c["id"] for c in tc.get_pending()["confirmations"]])
		frappe.set_user(self.other)
		self.assertNotIn(req["id"], [c["id"] for c in tc.get_pending()["confirmations"]])

	def test_outbound_flag_parks_even_without_requires_confirmation(self):
		with patch.object(tc, "_execute") as ex:
			out = json.loads(tool_policy.check_tool_call("send_campaign", dict(ARGS), None, False, is_outbound=True))
		ex.assert_not_called()
		self.assertEqual(out["type"], "confirmation_request")

	def test_expires_at_is_iso_utc_everywhere(self):
		req = self._park()
		self.assertRegex(req["expires_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$")
		self.assertEqual(tc.get_pending()["confirmations"][0]["expires_at"][-6:], "+00:00")
		out = tc.decide(req["id"], "false")
		self.assertTrue(out["confirmation"]["expires_at"].endswith("+00:00"))

	def test_iso_utc_converts_site_timezone(self):
		with patch("huf.ai.tool_confirmation.hashing.get_system_timezone", return_value="Asia/Kolkata"):
			self.assertEqual(tc.iso_utc("2026-11-17 15:45:00"), "2026-11-17T10:15:00+00:00")

	def test_hmac_hash_verifies_and_detects_tamper(self):
		h = tc.args_hash(ARGS)
		self.assertTrue(tc.verify_args_hash(ARGS, h))
		self.assertFalse(tc.verify_args_hash(dict(ARGS, message="Bye"), h))

	def test_confirmation_doctype_has_no_write_permissions(self):
		meta = frappe.get_meta(tc.DOCTYPE)
		for p in meta.permissions:
			self.assertFalse(p.create or p.write or p.delete, p.role)

	def test_unresolved_recipient_count_on_outbound_tool_is_refused(self):
		meta = {"is_outbound": 1, "confirmation_summary_path": "huf.ai.tools.messaging.confirmation_summaries.whatsapp_broadcast"}
		with patch.object(tc, "_tool_meta", return_value=meta):
			out = json.loads(tool_policy.check_tool_call("bulk", {"audience": "A", "template": "t"}, None, True))
		self.assertTrue(out["denied"])
		self.assertEqual(out["error"], "confirmation_summary_unresolved")
		self.assertFalse(frappe.db.exists(tc.DOCTYPE, {"tool": "bulk"}))

	def test_custom_summarizer_used(self):
		meta = {"is_outbound": 1, "confirmation_summary_path": "huf.ai.tools.messaging.confirmation_summaries.single_target"}
		with patch.object(tc, "_tool_meta", return_value=meta):
			s = tc.build_summary("slack_send_message", {"channel": "C1", "text": "yo"})
		self.assertEqual((s["recipient_count"], s["sample"]), (1, "yo"))
