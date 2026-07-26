"""
Tests for ``PermissionAwareToolRegistry`` gating of ``Code Execution`` tools:
the generic ``_can_use_tool`` checks as they apply to a Code Execution tool,
and the extra ``_allows_code_execution`` gate (capability + agent flag +
enabled Execution Profile).

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_tool_registry_code_execution

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import unittest

import frappe

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.install import create_huf_roles


class TestToolRegistryCodeExecution(unittest.TestCase):
	"""Registry-level capability checks for the Code Execution tool type."""

	@classmethod
	def setUpClass(cls):
		create_huf_roles()

	def setUp(self):
		self._users = []
		self._agents = []
		self._profiles = []
		self._tools = []
		self._tool_types = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._tools:
			self._delete("Agent Tool Function", name)
		for name in self._agents:
			self._delete("Agent", name)
		for name in self._profiles:
			self._delete("Execution Profile", name)
		for name in self._tool_types:
			self._delete("Agent Tool Type", name)
		for name in self._users:
			self._delete("User", name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _ensure_provider(self):
		existing = frappe.db.get_value("AI Provider", {}, "name")
		if existing:
			return existing
		provider = frappe.get_doc(
			{
				"doctype": "AI Provider",
				"provider_name": f"Test Provider {frappe.generate_hash(length=6)}",
				"api_key": "test-key-not-used",
				"provider_brand": "openai",
			}
		)
		provider.insert(ignore_permissions=True)
		return provider.name

	def _ensure_model(self, provider):
		existing = frappe.db.get_value("AI Model", {"provider": provider}, "name")
		if existing:
			return existing
		model = frappe.get_doc(
			{
				"doctype": "AI Model",
				"model_name": f"test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	def _make_user(self, roles=()):
		email = f"huf-exec-test-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ExecTest",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_tool_type(self):
		tool_type = frappe.get_doc(
			{"doctype": "Agent Tool Type", "name1": f"Test Tools {frappe.generate_hash(length=6)}"}
		)
		tool_type.insert(ignore_permissions=True)
		self._tool_types.append(tool_type.name)
		return tool_type.name

	def _make_tool(self, types="Code Execution", allowed_for_guest=0):
		tool = frappe.get_doc(
			{
				"doctype": "Agent Tool Function",
				"tool_name": f"test_tool_{frappe.generate_hash(length=8)}",
				"description": "Phase 7 test tool",
				"tool_type": self._make_tool_type(),
				"types": types,
				"allowed_for_guest": allowed_for_guest,
			}
		)
		tool.insert(ignore_permissions=True)
		self._tools.append(tool.name)
		return tool

	def _make_profile(self, disabled=0):
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": f"test-profile-{frappe.generate_hash(length=8)}",
				"approval_mode": "Auto Approve",
				"filesystem_policy": "None",
				"disabled": disabled,
			}
		)
		profile.insert(ignore_permissions=True)
		self._profiles.append(profile.name)
		return profile.name

	def _make_agent(self, allow_code_execution=1, execution_profile=None):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"test-agent-{frappe.generate_hash(length=8)}",
				"provider": self.provider,
				"model": self.model,
				"allow_code_execution": allow_code_execution,
				"execution_profile": execution_profile,
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	# -- _can_use_tool as it applies to a Code Execution tool ---------------------

	def test_can_use_tool_allows_normal_user(self):
		tool = self._make_tool()
		user = self._make_user(roles=("Huf User",))
		self.assertTrue(PermissionAwareToolRegistry._can_use_tool(tool, user))

	def test_can_use_tool_blocks_guest(self):
		tool = self._make_tool()
		self.assertFalse(PermissionAwareToolRegistry._can_use_tool(tool, "Guest"))

	def test_can_use_tool_guest_explicitly_allowed(self):
		tool = self._make_tool(allowed_for_guest=1)
		self.assertTrue(PermissionAwareToolRegistry._can_use_tool(tool, "Guest"))

	# -- _allows_code_execution gate -------------------------------------------------

	def test_non_code_execution_tool_passes_gate(self):
		tool = self._make_tool(types="Get Document")
		agent = self._make_agent(allow_code_execution=0, execution_profile=None)
		user_without_capability = self._make_user(roles=())
		self.assertTrue(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, user_without_capability)
		)

	def test_gate_denied_without_capability(self):
		tool = self._make_tool()
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		user_without_capability = self._make_user(roles=())
		self.assertFalse(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, user_without_capability)
		)

	def test_gate_denied_when_agent_flag_off(self):
		tool = self._make_tool()
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=0, execution_profile=profile)
		capable_user = self._make_user(roles=("Huf User",))
		self.assertFalse(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, capable_user)
		)

	def test_gate_denied_when_no_execution_profile(self):
		tool = self._make_tool()
		agent = self._make_agent(allow_code_execution=1, execution_profile=None)
		capable_user = self._make_user(roles=("Huf User",))
		self.assertFalse(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, capable_user)
		)

	def test_gate_denied_when_profile_disabled(self):
		tool = self._make_tool()
		profile = self._make_profile(disabled=1)
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		capable_user = self._make_user(roles=("Huf User",))
		self.assertFalse(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, capable_user)
		)

	def test_gate_allowed_when_all_conditions_met(self):
		tool = self._make_tool()
		profile = self._make_profile()
		agent = self._make_agent(allow_code_execution=1, execution_profile=profile)
		capable_user = self._make_user(roles=("Huf User",))
		self.assertTrue(
			PermissionAwareToolRegistry._allows_code_execution(tool, agent, capable_user)
		)


if __name__ == "__main__":
	unittest.main()
