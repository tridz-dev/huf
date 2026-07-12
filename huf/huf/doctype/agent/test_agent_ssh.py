"""
Tests for Agent-level gating of SSH execution.

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.agent.test_agent_ssh
"""
import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.tools.ssh_execution import run_ssh_command
from huf.install import create_huf_roles


class TestAgentSSH(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_huf_roles()

	def setUp(self):
		self._users = []
		self._agents = []
		self._connections = []
		self._calls = []
		self._approvals = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._approvals:
			self._delete("Agent Execution Approval", name)
		for name in self._calls:
			self._delete("Agent Tool Call", name)
		for name in self._agents:
			self._delete("Agent", name)
		for name in self._connections:
			self._delete("SSH Connection", name)
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
				"provider_name": f"SSH Agent Provider {frappe.generate_hash(length=6)}",
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
				"model_name": f"ssh-agent-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	def _make_user(self, roles=()):
		email = f"huf-ssh-agent-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SSHAgent",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_connection(self, enabled=1):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-agent-{frappe.generate_hash(length=8)}",
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

	def _make_agent(self, allow_ssh=0, ssh_connections=None, execution_profile=None):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"ssh-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test SSH agent instructions",
				"provider": self.provider,
				"model": self.model,
				"allow_ssh": allow_ssh,
				"execution_profile": execution_profile,
				"ssh_connections": [
					{"ssh_connection": name} for name in (ssh_connections or [])
				],
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent

	def test_dispatch_denied_when_agent_flag_off(self):
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=0, ssh_connections=[connection])
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_ssh_command(connection=connection, command="hostname", agent_doc=agent)

	def test_dispatch_denied_when_connection_not_allowlisted(self):
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=1, ssh_connections=[])
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			run_ssh_command(connection=connection, command="hostname", agent_doc=agent)

	def test_dispatch_denied_without_capability(self):
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=1, ssh_connections=[connection])
		user = self._make_user(roles=())
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			run_ssh_command(connection=connection, command="hostname", agent_doc=agent)

	def test_dispatch_allowed_when_fully_enabled(self):
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=1, ssh_connections=[connection])
		user = self._make_user(roles=("Huf User",))
		frappe.set_user(user)

		result = run_ssh_command(connection=connection, command="hostname", agent_doc=agent)
		self.assertTrue(result.get("success"))
		self.assertEqual(result.get("status"), "Pending Approval")
		self.assertEqual(result.get("execution_kind"), "exec")

		call_name = result.get("agent_tool_call")
		approval_name = result.get("approval")
		self._calls.append(call_name)
		self._approvals.append(approval_name)

		call = frappe.get_doc("Agent Tool Call", call_name)
		self.assertEqual(call.status, "Queued")
		self.assertEqual(call.ssh_connection, connection)
		self.assertEqual(call.execution_kind, "exec")
		self.assertTrue(call.execution_profile_snapshot)
		self.assertTrue(call.code_ref)

		approval = frappe.get_doc("Agent Execution Approval", approval_name)
		self.assertEqual(approval.execution_kind, "ssh_exec")
		self.assertEqual(approval.requested_capability, "ssh.run")
