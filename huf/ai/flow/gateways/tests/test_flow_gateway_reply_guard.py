# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Double-reply guard and test-run safety around ``finish_flow_event``. Mock-based; needs the app's imports (bench)."""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

try:
	from huf.ai import gateway_service as svc
except Exception:  # pragma: no cover - the app's heavy imports are missing (no bench)
	svc = None


@unittest.skipIf(svc is None, "needs the app's imports (bench)")
class TestFinishFlowEvent(unittest.TestCase):
	def _run(self, replied, reply_text="Your order is ready"):
		event = MagicMock()
		fake = MagicMock()

		def get_value(doctype, filters, fieldname=None, **kw):
			if doctype == "Gateway Event" and isinstance(filters, dict):
				return "GWE-1"
			if doctype == "Gateway Event":
				return {"status": "Running", "error_message": ""}
			if doctype == "Flow Run":
				return 1 if replied else 0
			return None

		fake.db.get_value.side_effect = get_value
		fake.get_doc.return_value = event
		send = MagicMock()
		with patch.object(svc, "frappe", fake), patch.object(svc, "_commit_unless_testing"), patch(
			"huf.ai.gateway_webhook.send_gateway_reply", send
		), patch.object(svc.provider_hooks, "get", return_value=None):
			svc.finish_flow_event("FR-1", "Success", reply_text)
		return event, send

	def test_reply_tool_already_answered_so_end_text_is_suppressed(self):
		event, send = self._run(replied=True)
		send.assert_not_called()
		values = [c[0][0] for c in event.db_set.call_args_list if c[0] and isinstance(c[0][0], dict)]
		self.assertIn({"status": "Succeeded", "reply_status": "suppressed", "error_message": "already replied"}, values)

	def test_without_the_flag_the_end_text_is_sent(self):
		event, send = self._run(replied=False)
		send.assert_called_once()

	def test_run_without_gateway_event_is_a_no_op(self):
		"""A test run has trigger_type Gateway but no Gateway Event: nothing is sent, nothing is written."""
		fake = MagicMock()
		fake.db.get_value.return_value = None
		send = MagicMock()
		with patch.object(svc, "frappe", fake), patch("huf.ai.gateway_webhook.send_gateway_reply", send):
			self.assertIsNone(svc.finish_flow_event("FR-TEST", "Success", "hello"))
		send.assert_not_called()
		fake.get_doc.assert_not_called()


class TestReplyToolSetsFlag(unittest.TestCase):
	def test_flag_set_after_send(self):
		try:
			from huf.ai.tools.gateways import reply
		except Exception:  # pragma: no cover
			self.skipTest("needs the app's imports (bench)")
		gateway, event = MagicMock(), MagicMock(conversation_id="c1")
		fake_frappe, send = MagicMock(), MagicMock()
		fake_frappe.db.exists.return_value = True
		webhook = types.ModuleType("huf.ai.gateway_webhook")
		webhook.send_gateway_reply = send
		with patch.object(reply, "resolve_origin", return_value=(gateway, event, "FR-1")), patch.object(
			reply, "frappe", fake_frappe
		), patch.dict(sys.modules, {"huf.ai.gateway_webhook": webhook}):
			reply.handle_gateway_reply(text="hi", flow_run_id="FR-1")
		set_value = fake_frappe.db.set_value
		send.assert_called_once()
		set_value.assert_called_once_with("Flow Run", "FR-1", "replied_via_tool", 1, update_modified=False)


if __name__ == "__main__":
	unittest.main()
