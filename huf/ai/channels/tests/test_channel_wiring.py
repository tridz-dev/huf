import frappe
from frappe.tests import IntegrationTestCase


class TestChannelWiring(IntegrationTestCase):
	def test_channel_tools_registered(self):
		from huf.ai.tools import _registry as r

		names = {t["tool_name"] for t in r.ALL_INTEGRATION_TOOLS}
		for tool in (
			"handoff_to_human",
			"create_lead",
			"create_ticket",
			"erp_lookup_customer",
			"erp_create_order",
			"erp_order_status",
			"setup_gateway",
			"test_gateway_health",
		):
			self.assertIn(tool, names)

	def test_communication_hooks_both_registered(self):
		hooks = frappe.get_hooks("doc_events").get("Communication", {}).get("after_insert", [])
		self.assertIn("huf.ai.channels.handoff_hooks.communication_after_insert", hooks)
		self.assertIn("huf.ai.gateway_adapters.email.on_communication_inserted", hooks)
