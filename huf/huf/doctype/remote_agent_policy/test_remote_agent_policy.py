# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestRemoteAgentPolicy(IntegrationTestCase):
	def test_single_agent_scope_requires_default_agent(self):
		doc = frappe.new_doc("Remote Agent Policy")
		doc.policy_name = "test-single-no-agent"
		doc.caller_type = "api_key"
		doc.scope_type = "single_agent"
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_agent_list_scope_requires_allowed_agents(self):
		doc = frappe.new_doc("Remote Agent Policy")
		doc.policy_name = "test-list-no-agents"
		doc.caller_type = "api_key"
		doc.scope_type = "agent_list"
		with self.assertRaises(frappe.ValidationError):
			doc.insert()

	def test_allowed_agents_populated_for_list_scope(self):
		agent_name = self._ensure_test_agent()
		doc = frappe.new_doc("Remote Agent Policy")
		doc.policy_name = "test-list-ok"
		doc.caller_type = "api_key"
		doc.scope_type = "agent_list"
		doc.append("allowed_agents", {"agent": agent_name})
		doc.insert()
		self.assertEqual(doc.get_allowed_agent_names(), [agent_name])

	def _ensure_test_agent(self):
		name = "_test_remote_agent_policy_agent"
		if not frappe.db.exists("Agent", name):
			frappe.get_doc({
				"doctype": "Agent",
				"agent_name": name,
				"ai_model": self._ensure_test_model(),
				"instructions": "Test agent for Remote Agent Policy tests.",
			}).insert()
		return name

	def _ensure_test_model(self):
		name = "_test_remote_agent_policy_model"
		if not frappe.db.exists("AI Model", name):
			frappe.get_doc({
				"doctype": "AI Model",
				"model_name": name,
				"model_id": name,
				"provider": self._ensure_test_provider(),
			}).insert()
		return name

	def _ensure_test_provider(self):
		name = "_test_remote_agent_policy_provider"
		if not frappe.db.exists("AI Provider", name):
			frappe.get_doc({
				"doctype": "AI Provider",
				"provider_name": name,
				"provider_brand": "ollama",
				"is_local_llm": 1,
				"url": "http://localhost:11434",
			}).insert()
		return name
