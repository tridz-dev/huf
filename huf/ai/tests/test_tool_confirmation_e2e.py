"""End-to-end park -> approve -> run -> history for a web-run outbound tool (INTEGRATION).
Run: bench run-tests --module huf.ai.tests.test_tool_confirmation_e2e"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai import tool_confirmation as tc
from huf.ai.conversation_manager import ConversationManager, repair_message_sequence, supersede_duplicate_tool_results
from huf.ai.gateways import tool_policy
from huf.ai.tools.invocation import ToolResult
from huf.testing.factories import make_agent_conversation

CALL_ID = "call_e2e_1"
ARGS = {"action": "send_message", "to": "+911", "message": "hello"}


def _user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "E2E", "send_welcome_email": 0}).insert(ignore_permissions=True)
	return email


class TestToolConfirmationE2E(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.other = _user("e2e-other@example.com")
		self.conv = make_agent_conversation().name

	def tearDown(self):
		frappe.set_user("Administrator")

	def _history_rows(self, pending):
		"""What the streaming layer persists for a parked call: the user turn, then ONE combined assistant row
		(declaration + 'awaiting approval' result) under the call id."""
		calls = [{"id": CALL_ID, "type": "function", "function": {"name": "whatsapp", "arguments": json.dumps(ARGS)}}]
		for idx, row in enumerate(
			[
				{"role": "user", "kind": "Message", "content": "send hello"},
				{
					"role": "agent",
					"kind": "Tool Result",
					"content": "**Tool Result:**\n" + json.dumps(pending),
					"tool_call_id": CALL_ID,
					"tool_calls": json.dumps(calls),
				},
			],
			start=1,
		):
			frappe.get_doc({"doctype": "Agent Message", "conversation": self.conv, "conversation_index": idx, **row}).insert(ignore_permissions=True)

	def _park(self):
		out = json.loads(
			tool_policy.check_tool_call(
				"whatsapp", dict(ARGS), None, True, conversation_id=self.conv, agent_name=None, tool_call_id=CALL_ID
			)
		)
		self.assertEqual(out["type"], "confirmation_request")
		return out

	def test_park_approve_run_followup_and_events(self):
		with patch.object(frappe, "publish_realtime") as pub:
			req = self._park()
			self._history_rows(req)
			with patch.object(frappe, "enqueue") as enq:
				tc.decide(req["id"], True)
			enq.assert_called_once()
			self.assertEqual(enq.call_args.args[0], "huf.ai.tool_confirmation.run_approved")
			self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "approved")
			with patch.object(tc, "_execute", return_value=ToolResult(success=True, result={"sent": 1})) as ex:
				tc.run_approved(req["id"], "Administrator")
				tc.run_approved(req["id"], "Administrator")  # duplicate job: no second run
			ex.assert_called_once()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "executed")
		events = [
			c.kwargs["message"]["type"]
			for c in pub.call_args_list
			if isinstance(c.kwargs.get("message"), dict) and str(c.kwargs["message"].get("type", "")).startswith("approval-")
		]
		self.assertEqual(events, ["approval-requested", "approval-resolved"])

		history = ConversationManager("x").get_conversation_history(self.conv)
		tool_msgs = [m for m in history if m.get("role") == "tool" and m.get("tool_call_id") == CALL_ID]
		self.assertEqual(len(tool_msgs), 1, history)
		self.assertIn("confirmation_result", tool_msgs[0]["content"])  # the real outcome superseded 'pending'
		self.assertNotIn("confirmation_request", tool_msgs[0]["content"])
		fixed = repair_message_sequence(history, self.conv)
		self.assertEqual(sum(1 for m in fixed if m.get("role") == "tool" and m.get("tool_call_id") == CALL_ID), 1)
		decl = [i for i, m in enumerate(fixed) if m.get("tool_calls")]
		self.assertEqual(len(decl), 1)
		self.assertEqual(fixed[decl[0] + 1]["role"], "tool")

	def test_supersede_keeps_position_and_latest_content(self):
		msgs = [
			{"role": "assistant", "tool_calls": [{"id": "a"}]},
			{"role": "tool", "tool_call_id": "a", "content": "pending"},
			{"role": "user", "content": "hm"},
			{"role": "tool", "tool_call_id": "a", "content": "done"},
		]
		out = supersede_duplicate_tool_results(msgs)
		self.assertEqual([m["role"] for m in out], ["assistant", "tool", "user"])
		self.assertEqual(out[1]["content"], "done")

	def test_other_user_cannot_decide(self):
		req = self._park()
		frappe.set_user(self.other)
		with self.assertRaises(tc.Forbidden):
			tc.decide(req["id"], True)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "pending")

	def test_expired_is_rejected(self):
		req = self._park()
		frappe.db.set_value(tc.DOCTYPE, req["id"], "expires_at", add_to_date(now_datetime(), minutes=-1))
		with patch.object(frappe, "enqueue") as enq, self.assertRaises(tc.Expired):
			tc.decide(req["id"], True)
		enq.assert_not_called()
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "state"), "expired")
