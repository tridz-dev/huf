# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Tests for lazy tool discovery: Agent.enable_lazy_tools, the four
huf.ai.tools.lazy_discovery handlers, and the eager/deferred partition in
huf.ai.sdk_tools.create_agent_tools().

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_lazy_tool_discovery
"""

import json
import unittest
from unittest import mock

import frappe

from huf.ai.sdk_tools import create_agent_tools
from huf.ai.tools.lazy_discovery import (
	handle_describe_tool_group,
	handle_list_tool_groups,
	handle_load_tools,
	handle_search_tools,
)


class TestLazyToolDiscovery(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.provider = cls._ensure_provider()
		cls.model = cls._ensure_model(cls.provider)

	def setUp(self):
		frappe.set_user("Administrator")
		self._agents = []
		self._tools = []
		self._tool_types = []
		self._conversations = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._agents:
			self._delete("Agent", name)
		for name in self._tools:
			self._delete("Agent Tool Function", name)
		for name in self._tool_types:
			self._delete("Agent Tool Type", name)
		for name in self._conversations:
			self._delete("Agent Conversation", name)
		frappe.db.commit()

	@staticmethod
	def _delete(doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	@staticmethod
	def _ensure_provider():
		existing = frappe.db.get_value("AI Provider", {}, "name")
		if existing:
			return existing
		provider = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Lazy Discovery Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		provider.insert(ignore_permissions=True)
		return provider.name

	@staticmethod
	def _ensure_model(provider):
		existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
		if existing:
			return existing
		model = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"lazy-discovery-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	# -- fixtures -----------------------------------------------------------

	def _make_tool_type(self):
		tool_type = frappe.get_doc(
			{"doctype": "Agent Tool Type", "name1": f"Lazy Discovery Test Tools {frappe.generate_hash(length=6)}"}
		)
		tool_type.insert(ignore_permissions=True)
		self._tool_types.append(tool_type.name)
		return tool_type.name

	def _make_tool(self, service=None, provider_app=None, description="A test tool.", params=None):
		tool_name = f"lazy-tool-{frappe.generate_hash(length=8)}"
		tool = frappe.get_doc(
			{
				"doctype": "Agent Tool Function",
				"tool_name": tool_name,
				"description": description,
				"tool_type": self._make_tool_type(),
				"types": "App Provided",
				"function_path": "huf.ai.tools.code_execution.run_python",
				"service": service,
				"provider_app": provider_app,
				"params": json.dumps(params) if params is not None else None,
			}
		)
		tool.insert(ignore_permissions=True)
		self._tools.append(tool.name)
		return tool

	def _make_agent(self, tools, enable_lazy_tools=0):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"lazy-discovery-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test lazy discovery agent instructions",
				"provider": self.provider,
				"model": self.model,
				"enable_lazy_tools": enable_lazy_tools,
				"agent_tool": [{"tool": tool.name} for tool in tools],
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	def _make_conversation(self):
		conversation = frappe.get_doc(
			{
				"doctype": "Agent Conversation",
				"title": f"lazy-discovery-test-{frappe.generate_hash(length=6)}",
				"session_id": f"test-session-{frappe.generate_hash(length=10)}",
				"is_active": 1,
			}
		)
		conversation.insert(ignore_permissions=True)
		self._conversations.append(conversation.name)
		return conversation.name

	@staticmethod
	def _tool_names(function_tools):
		return {tool.name for tool in function_tools}

	# -- (1) flag off leaves eager behavior unchanged ------------------------

	def test_disabled_flag_builds_every_allowed_tool_eagerly(self):
		email_tool = self._make_tool(service="gmail", description="Send an email.")
		crm_tool = self._make_tool(service="crm", description="Create a CRM lead.")
		agent = self._make_agent([email_tool, crm_tool], enable_lazy_tools=0)

		tools = create_agent_tools(agent)
		names = self._tool_names(tools)

		self.assertIn(email_tool.tool_name, names)
		self.assertIn(crm_tool.tool_name, names)

	# -- (2) flag on defers non-essential tools ------------------------------

	def test_enabled_flag_defers_non_essential_tools_but_keeps_eager_set(self):
		email_tool = self._make_tool(service="gmail", description="Send an email.")
		crm_tool = self._make_tool(service="crm", description="Create a CRM lead.")
		agent = self._make_agent([email_tool, crm_tool], enable_lazy_tools=1)
		conversation_id = self._make_conversation()

		tools = create_agent_tools(agent, conversation_id=conversation_id, agent_name=agent.name)
		names = self._tool_names(tools)

		# Neither non-essential tool has been discovered yet - both deferred.
		self.assertNotIn(email_tool.tool_name, names)
		self.assertNotIn(crm_tool.tool_name, names)

		# The discovery tools themselves must always be present, or the model
		# could never unlock anything.
		for discovery_tool_name in ("list_tool_groups", "search_tools", "describe_tool_group", "load_tools"):
			self.assertIn(discovery_tool_name, names)

	# -- (3) load_tools rejects a tool the agent is not permitted to use -----

	def test_load_tools_rejects_unpermitted_tool_name(self):
		allowed_tool = self._make_tool(service="gmail", description="Send an email.")
		agent = self._make_agent([allowed_tool], enable_lazy_tools=1)
		conversation_id = self._make_conversation()

		result = json.loads(
			handle_load_tools(
				tool_names=[allowed_tool.tool_name, "not_a_real_or_permitted_tool"],
				agent_name=agent.name,
				conversation_id=conversation_id,
			)
		)

		accepted_names = {entry["tool_name"] for entry in result["accepted"]}
		self.assertIn(allowed_tool.tool_name, accepted_names)
		self.assertIn("not_a_real_or_permitted_tool", result["rejected"])
		self.assertNotIn("not_a_real_or_permitted_tool", accepted_names)

	# -- (4) load_tools persists + promotes to eager on the next call -------

	def test_load_tools_persists_and_promotes_tool_to_eager(self):
		email_tool = self._make_tool(service="gmail", description="Send an email.")
		crm_tool = self._make_tool(service="crm", description="Create a CRM lead.")
		agent = self._make_agent([email_tool, crm_tool], enable_lazy_tools=1)
		conversation_id = self._make_conversation()

		# Still deferred before any discovery.
		before = self._tool_names(
			create_agent_tools(agent, conversation_id=conversation_id, agent_name=agent.name)
		)
		self.assertNotIn(email_tool.tool_name, before)

		load_result = json.loads(
			handle_load_tools(
				tool_names=[email_tool.tool_name],
				agent_name=agent.name,
				conversation_id=conversation_id,
			)
		)
		self.assertEqual(load_result["rejected"], [])

		after = self._tool_names(
			create_agent_tools(agent, conversation_id=conversation_id, agent_name=agent.name)
		)
		self.assertIn(email_tool.tool_name, after)
		# The un-discovered sibling tool must remain deferred.
		self.assertNotIn(crm_tool.tool_name, after)

	def test_load_tools_accepts_json_encoded_tool_names(self):
		"""HUF tool params often arrive JSON-encoded rather than as a real list."""
		email_tool = self._make_tool(service="gmail", description="Send an email.")
		agent = self._make_agent([email_tool], enable_lazy_tools=1)
		conversation_id = self._make_conversation()

		result = json.loads(
			handle_load_tools(
				tool_names=json.dumps([email_tool.tool_name]),
				agent_name=agent.name,
				conversation_id=conversation_id,
			)
		)

		accepted_names = {entry["tool_name"] for entry in result["accepted"]}
		self.assertIn(email_tool.tool_name, accepted_names)

	# -- (5) discovery handlers only ever surface permitted tools ------------

	def test_list_tool_groups_only_covers_allowed_tools(self):
		email_tool = self._make_tool(service="gmail", description="Send an email. Extra detail follows.")
		agent = self._make_agent([email_tool], enable_lazy_tools=1)
		other_agent = self._make_agent([], enable_lazy_tools=1)

		groups = json.loads(handle_list_tool_groups(agent_name=agent.name))
		gmail_group = next((g for g in groups if g["service"] == "gmail"), None)
		self.assertIsNotNone(gmail_group)
		self.assertEqual(gmail_group["tool_count"], 1)
		self.assertEqual(gmail_group["summary"], "Send an email.")

		other_groups = json.loads(handle_list_tool_groups(agent_name=other_agent.name))
		self.assertEqual(other_groups, [])

	def test_describe_tool_group_only_covers_allowed_tools(self):
		email_tool = self._make_tool(service="gmail", description="Send an email.")
		crm_tool = self._make_tool(service="crm", description="Create a CRM lead.")
		agent = self._make_agent([email_tool], enable_lazy_tools=1)

		gmail_tools = json.loads(handle_describe_tool_group(service="gmail", agent_name=agent.name))
		self.assertEqual([t["tool_name"] for t in gmail_tools], [email_tool.tool_name])

		crm_tools = json.loads(handle_describe_tool_group(service="crm", agent_name=agent.name))
		self.assertEqual(crm_tools, [])

	def test_search_tools_only_covers_allowed_tools(self):
		"""search_app_actions inspects real installed-app action metadata, which
		this test cannot fabricate, so the underlying search is mocked; what is
		under test here is the permission filter applied to its results."""
		email_tool = self._make_tool(
			service="gmail", provider_app="gmail", description="Send an email to a recipient."
		)
		agent = self._make_agent([email_tool], enable_lazy_tools=1)
		other_agent = self._make_agent([], enable_lazy_tools=1)

		fake_descriptors = [
			{"title": email_tool.tool_name, "description": "Send an email to a recipient."},
			{"title": "not_a_permitted_tool", "description": "Some other app action."},
		]
		with mock.patch(
			"huf.ai.capability_discovery.api.search_app_actions", return_value=fake_descriptors
		):
			results = json.loads(handle_search_tools(query="email", agent_name=agent.name))
			other_results = json.loads(handle_search_tools(query="email", agent_name=other_agent.name))

		self.assertEqual([r["tool_name"] for r in results], [email_tool.tool_name])
		self.assertEqual(other_results, [])


if __name__ == "__main__":
	unittest.main()
