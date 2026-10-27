# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""connect_agent_to_channel: one step from a channel credential to an agent that answers it."""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai import gateway_service as gsvc
from huf.testing.factories import make_agent, make_ai_provider_and_model


class TestConnectAgentToChannel(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.provider, self.model = make_ai_provider_and_model()
		suffix = frappe.generate_hash(length=6)
		self.agents = [
			make_agent(agent_name=f"_Test Connect {label} {suffix}", provider=self.provider, model=self.model)
			for label in ("A", "B")
		]
		self.settings = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"is_active": 1,
				"credentials": [
					{"key": "phone_number_id", "value": f"55{frappe.generate_hash(length=8)}"},
					{"key": "access_token", "value": "t"},
					{"key": "webhook_verify_token", "value": "v"},
					{"key": "app_secret", "value": "s"},
				],
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Gateway", {"integration_settings": self.settings.name})
		frappe.db.delete("Integration Settings", {"name": self.settings.name})
		for agent in self.agents:
			frappe.delete_doc("Agent", agent.name, ignore_permissions=True, force=True)
		frappe.db.delete("AI Model", {"name": self.model})
		frappe.db.delete("AI Provider", {"name": self.provider})

	def _tools(self, agent):
		return {row.tool for row in frappe.get_doc("Agent", agent).agent_tool or []}

	def test_creates_a_pairing_gateway_routed_to_the_agent(self):
		agent = self.agents[0].name
		result = gsvc.connect_agent_to_channel(self.settings.name, agent)

		self.assertTrue(result["created"])
		gateway = frappe.get_doc("Gateway", result["gateway"])
		self.assertEqual(gateway.provider, "WhatsApp")
		self.assertEqual(gateway.integration_settings, self.settings.name)
		self.assertEqual((gateway.default_target_type, gateway.default_agent), ("Agent", agent))
		self.assertEqual(gateway.direct_policy, "Pairing")
		self.assertEqual(bool(gateway.is_enabled), result["enabled"])
		if not result["enabled"]:
			self.assertTrue(result["enable_error"])
		whatsapp_tools = set(frappe.get_all("Agent Tool Function", {"service": "whatsapp"}, pluck="name"))
		self.assertTrue(whatsapp_tools <= self._tools(agent))

	def test_reconnecting_replaces_the_agent_on_the_same_gateway(self):
		first = gsvc.connect_agent_to_channel(self.settings.name, self.agents[0].name)
		second = gsvc.connect_agent_to_channel(self.settings.name, self.agents[1].name)

		self.assertFalse(second["created"])
		self.assertEqual(second["gateway"], first["gateway"])
		self.assertEqual(second["previous_agent"], self.agents[0].name)
		self.assertEqual(frappe.db.get_value("Gateway", first["gateway"], "default_agent"), self.agents[1].name)
		self.assertEqual(frappe.db.count("Gateway", {"integration_settings": self.settings.name}), 1)

	def test_tools_are_not_attached_twice(self):
		agent = self.agents[0].name
		gsvc.connect_agent_to_channel(self.settings.name, agent)
		again = gsvc.connect_agent_to_channel(self.settings.name, agent)
		self.assertEqual(again["tools_added"], 0)
		self.assertIsNone(again["previous_agent"])

	def test_connection_lists_the_gateway_and_its_agent(self):
		result = gsvc.connect_agent_to_channel(self.settings.name, self.agents[0].name)
		info = gsvc.get_channel_agent_connection(self.settings.name)
		self.assertEqual(info["provider"], "WhatsApp")
		self.assertEqual([g["name"] for g in info["gateways"]], [result["gateway"]])
		self.assertEqual(info["gateways"][0]["default_agent"], self.agents[0].name)

	def test_rejects_a_credential_that_is_not_a_channel(self):
		other = frappe.get_doc(
			{"doctype": "Integration Settings", "service": "github", "is_active": 1,
			 "credentials": [{"key": "access_token", "value": "x"}]}
		).insert(ignore_permissions=True)
		try:
			with self.assertRaises(frappe.ValidationError):
				gsvc.connect_agent_to_channel(other.name, self.agents[0].name)
		finally:
			frappe.db.delete("Integration Settings", {"name": other.name})
