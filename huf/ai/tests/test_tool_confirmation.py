"""Integration tests for confirm-before-send (HUFCRM-06a). Run: bench run-tests --module huf.ai.tests.test_tool_confirmation"""

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

	def test_approve_executes_once_and_audits(self):
		req = self._park()
		with patch.object(tc, "assert_user_may_run"), patch.object(
			tc, "_execute", return_value=ToolResult(success=True, result={"sent": 2})
		) as ex:
			out = tc.decide(req["id"], True)
			ex.assert_called_once()
			self.assertEqual(ex.call_args[0][1]["template"], "promo")
			with self.assertRaises(tc.AlreadyDecided):  # replay
				tc.decide(req["id"], True)
			self.assertEqual(ex.call_count, 1)
		self.assertEqual(out["confirmation"]["state"], "executed")
		row = frappe.get_doc(tc.DOCTYPE, req["id"])
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
		with patch.object(tc, "assert_user_may_run"), patch.object(tc, "_execute") as ex, self.assertRaises(
			tc.ArgsChanged
		):
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
