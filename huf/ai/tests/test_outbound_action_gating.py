"""Per-action confirmation for multi-action outbound tools (INTEGRATION). Read actions run; send actions park."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import tool_confirmation as tc
from huf.ai.gateways import tool_policy
from huf.ai.tools.outbound_actions import OUTBOUND_ACTIONS, is_outbound_call


class TestOutboundActionGating(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_helper_maps(self):
		self.assertIsNone(is_outbound_call("send_campaign", {"action": "x"}))
		self.assertFalse(is_outbound_call("whatsapp", {"action": "list_templates"}))
		self.assertFalse(is_outbound_call("whatsapp", {"action": "create_template"}))
		self.assertTrue(is_outbound_call("whatsapp", {"action": "send_template"}))
		self.assertTrue(is_outbound_call("whatsapp", {}), "missing action fails closed")
		self.assertTrue(is_outbound_call("whatsapp", {"action": "brand_new_action"}), "unknown action fails closed")
		self.assertFalse(is_outbound_call("telegram", {"action": "get_chat_info"}))
		self.assertTrue(is_outbound_call("telegram", {"action": "send_message"}))
		self.assertTrue(is_outbound_call("telegram", {"action": "delete_message"}))
		self.assertFalse(is_outbound_call("messenger", {"action": "list_messages"}))
		self.assertTrue(is_outbound_call("messenger", {"action": "reply_message"}))

	def test_every_send_action_of_real_tools_is_outbound(self):
		from huf.ai.tools import whatsapp as wa

		self.assertTrue((wa._SEND_ACTIONS - {"create_template"}) <= OUTBOUND_ACTIONS["whatsapp"])

	def test_read_action_runs_send_action_parks(self):
		with patch.object(tc, "_execute") as ex:
			self.assertIsNone(
				tool_policy.check_tool_call("whatsapp", {"action": "list_templates"}, None, True, is_outbound=True)
			)
			out = json.loads(
				tool_policy.check_tool_call(
					"whatsapp", {"action": "send_message", "to": "+911", "message": "hi"}, None, True, is_outbound=True
				)
			)
		ex.assert_not_called()
		self.assertEqual(out["type"], "confirmation_request")

	def test_explicit_requires_confirmation_still_gates_reads(self):
		with patch.object(tool_policy, "_explicit_requires_confirmation", return_value=True), patch.object(
			tc, "_execute"
		):
			out = tool_policy.check_tool_call("whatsapp", {"action": "list_templates"}, None, True, is_outbound=True)
		self.assertEqual(json.loads(out)["type"], "confirmation_request")
