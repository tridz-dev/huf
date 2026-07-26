"""
Tests for ``PermissionAwareToolRegistry`` gating of the app-provided SSH tool.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_tool_registry_ssh
"""
import unittest

import frappe

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.install import create_huf_roles


class TestToolRegistrySSH(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		create_huf_roles()

	def setUp(self):
		self._users = []
		self._agents = []
		self._connections = []
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
		for name in self._connections:
			self._delete("SSH Connection", name)
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
				"provider_name": f"SSH Test Provider {frappe.generate_hash(length=6)}",
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
				"model_name": f"ssh-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	def _make_user(self, roles=()):
		email = f"huf-ssh-registry-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SSHRegistry",
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
			{"doctype": "Agent Tool Type", "name1": f"SSH Test Tools {frappe.generate_hash(length=6)}"}
		)
		tool_type.insert(ignore_permissions=True)
		self._tool_types.append(tool_type.name)
		return tool_type.name

	def _make_tool(self, function_path="huf.ai.tools.ssh_execution.run_ssh_command"):
		tool_name = f"ssh-tool-{frappe.generate_hash(length=8)}"
		tool = frappe.get_doc(
			{
				"doctype": "Agent Tool Function",
				"tool_name": tool_name,
				"description": "SSH tool test",
				"tool_type": self._make_tool_type(),
				"types": "App Provided",
				"function_path": function_path,
			}
		)
		tool.insert(ignore_permissions=True)
		self._tools.append(tool.name)
		return tool

	def _make_connection(self, enabled=1):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-registry-{frappe.generate_hash(length=8)}",
				"enabled": enabled,
				"host": "example.com",
				"port": 22,
				"username": "ubuntu",
				"auth_method": "Password",
				"password": "secret-pass",
				"host_key_fingerprint": "SHA256:testfingerprint",
				"host_key_type": "ssh-ed25519",
			}
		)
		doc.insert(ignore_permissions=True)
		self._connections.append(doc.name)
		return doc.name

	def _make_agent(self, allow_ssh=1, ssh_connections=None):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"ssh-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test SSH registry agent instructions",
				"provider": self.provider,
				"model": self.model,
				"allow_ssh": allow_ssh,
				"ssh_connections": [
					{"ssh_connection": name} for name in (ssh_connections or [])
				],
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	def test_non_ssh_tool_passes_gate(self):
		tool = self._make_tool(function_path="huf.ai.tools.code_execution.run_python")
		agent = self._make_agent(allow_ssh=0, ssh_connections=[])
		user = self._make_user(roles=())
		self.assertTrue(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))

	def test_gate_denied_without_capability(self):
		tool = self._make_tool()
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=1, ssh_connections=[connection])
		user = self._make_user(roles=())
		self.assertFalse(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))

	def test_gate_denied_when_agent_flag_off(self):
		tool = self._make_tool()
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=0, ssh_connections=[connection])
		user = self._make_user(roles=("Huf User",))
		self.assertFalse(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))

	def test_gate_denied_when_no_connections_allowlisted(self):
		tool = self._make_tool()
		agent = self._make_agent(allow_ssh=1, ssh_connections=[])
		user = self._make_user(roles=("Huf User",))
		self.assertFalse(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))

	def test_gate_denied_when_allowlisted_connection_disabled(self):
		tool = self._make_tool()
		connection = self._make_connection(enabled=0)
		agent = self._make_agent(allow_ssh=1, ssh_connections=[connection])
		user = self._make_user(roles=("Huf User",))
		self.assertFalse(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))

	def test_gate_allowed_when_all_conditions_met(self):
		tool = self._make_tool()
		connection = self._make_connection(enabled=1)
		agent = self._make_agent(allow_ssh=1, ssh_connections=[connection])
		user = self._make_user(roles=("Huf User",))
		self.assertTrue(PermissionAwareToolRegistry._allows_ssh_execution(tool, agent, user))


if __name__ == "__main__":
	unittest.main()
