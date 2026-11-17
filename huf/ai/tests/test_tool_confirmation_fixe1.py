"""FIX-E1 tests. Run: bench run-tests --module huf.ai.tests.test_tool_confirmation_fixe1"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import tool_confirmation as tc
from huf.ai.conversation_manager import repair_message_sequence


def _capture_followup(call_id):
	doc = SimpleNamespace(conversation="CONV-1", name="ATC-1", tool="whatsapp", tool_call_id=call_id)
	rows = []

	def fake_get_doc(row):
		rows.append(row)
		return MagicMock()

	with (
		patch.object(frappe.db, "exists", return_value=True),
		patch.object(tc, "_next_index", return_value=7),
		patch.object(frappe, "get_doc", side_effect=fake_get_doc),
	):
		tc._append_followup(doc, "denied", None)
	return rows[0]


class TestFixE1(IntegrationTestCase):
	def test_followup_with_call_id_is_a_tool_result_for_that_call(self):
		row = _capture_followup("call_abc")
		self.assertEqual((row["role"], row["kind"], row["tool_call_id"]), ("tool", "Tool Result", "call_abc"))
		self.assertIn("Do not retry", json.loads(row["content"])["message"])
		history = [
			{"role": "assistant", "content": None, "tool_calls": [{"id": "call_abc", "type": "function", "function": {"name": "whatsapp", "arguments": "{}"}}]},
			{"role": "tool", "tool_call_id": row["tool_call_id"], "content": row["content"]},
		]
		with patch.object(frappe, "log_error") as log:
			out = repair_message_sequence(history)
		self.assertEqual(len(out), 2)  # nothing dropped
		log.assert_not_called()

	def test_followup_without_call_id_is_a_system_note(self):
		row = _capture_followup(None)
		self.assertEqual((row["role"], row["kind"]), ("system", "Message"))
		self.assertNotIn("tool_call_id", row)
		self.assertIn("denied", row["content"])

	def test_failed_and_executed_notes_instruct_no_retry(self):
		self.assertIn("Do not retry", tc._OUTCOME_NOTE["failed"])
		self.assertIn("Do not run it again", tc._OUTCOME_NOTE["executed"])

	def test_next_index_locks_conversation_row(self):
		with patch.object(frappe.db, "get_value") as gv, patch.object(frappe.db, "sql", return_value=[(4,)]):
			self.assertEqual(tc._next_index("CONV-1"), 5)
		self.assertEqual(gv.call_args.kwargs.get("for_update"), True)
		self.assertEqual(gv.call_args.args[0], "Agent Conversation")

	def test_park_stores_tool_call_id(self):
		with patch.object(tc, "_tool_meta", return_value={}):
			req = tc.park("send_campaign", {"recipients": ["+1"]}, tool_call_id="call_xyz")
		self.assertEqual(frappe.db.get_value(tc.DOCTYPE, req["id"], "tool_call_id"), "call_xyz")

	def test_whatsapp_summarizer(self):
		from huf.ai.tools.confirmation_summaries import whatsapp

		s = whatsapp({"action": "send_template", "template_name": "promo", "to": "+1"})
		self.assertEqual((s["recipient_count"], s["template"], s["channel"]), (1, "promo", "whatsapp"))

	def test_registry_marks_outbound_tools(self):
		from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS

		by = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for name in ("whatsapp", "gmail_send_email", "slack_send_message"):
			self.assertEqual(by[name].get("is_outbound"), 1, name)
			self.assertTrue(by[name].get("confirmation_summary_path"))
