"""
Negative and limit tests for ``huf.ai.tools.ssh_execution``.

Paramiko and sockets are fully mocked; no real network is used.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_ssh_execution
"""
import base64
import hashlib
import json
import unittest
from unittest.mock import Mock, patch

import frappe

from huf.ai.tools.ssh_execution import execute_job, run_ssh_command
from huf.install import create_huf_roles


def _fingerprint_for(key_bytes):
	digest = hashlib.sha256(key_bytes).digest()
	return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


class _FakeHostKey:
	def __init__(self, key_bytes, name="ssh-ed25519"):
		self._key_bytes = key_bytes
		self._name = name

	def asbytes(self):
		return self._key_bytes

	def get_name(self):
		return self._name


class _SSHExecutionTestBase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		create_huf_roles()

	def setUp(self):
		self._users = []
		self._agents = []
		self._connections = []
		self._tool_calls = []
		self._approvals = []
		self.provider = self._ensure_provider()
		self.model = self._ensure_model(self.provider)

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._approvals:
			self._delete("Agent Execution Approval", name)
		for name in self._tool_calls:
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
				"provider_name": f"SSH Exec Test Provider {frappe.generate_hash(length=6)}",
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
				"model_name": f"ssh-exec-test-model-{frappe.generate_hash(length=6)}",
				"provider": provider,
			}
		)
		model.insert(ignore_permissions=True)
		return model.name

	def _make_user(self, roles=()):
		email = f"huf-ssh-exec-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SSHExec",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_connection(self, **overrides):
		doc = frappe.get_doc(
			{
				"doctype": "SSH Connection",
				"display_name": f"ssh-exec-{frappe.generate_hash(length=8)}",
				"enabled": 1,
				"host": "example.com",
				"port": 22,
				"username": "ubuntu",
				"auth_method": "Password",
				"password": "secret-pass",
				"host_key_fingerprint": _fingerprint_for(b"server-key"),
				"host_key_type": "ssh-ed25519",
				**overrides,
			}
		)
		doc.insert(ignore_permissions=True)
		self._connections.append(doc.name)
		return doc

	def _make_agent(self, allow_ssh=1, ssh_connections=None):
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"ssh-exec-agent-{frappe.generate_hash(length=8)}",
				"instructions": "Test SSH execution agent instructions",
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

	def _make_tool_call(self, connection_name):
		call = frappe.get_doc(
			{
				"doctype": "Agent Tool Call",
				"tool": "run_ssh_command",
				"status": "Queued",
				"execution_kind": "exec",
				"ssh_connection": connection_name,
			}
		)
		call.insert(ignore_permissions=True)
		self._tool_calls.append(call.name)
		return call

	def _run_execute_job(self, connection, agent, user, command="echo hi", limits=None,
			key_bytes=b"server-key", key_name="ssh-ed25519", authenticated=True, channel=None,
			configure_transport=None):
		call = self._make_tool_call(connection.name)
		transport = Mock()
		transport.get_remote_server_key.return_value = _FakeHostKey(key_bytes, key_name)
		transport.is_authenticated.return_value = authenticated
		transport.open_session.return_value = channel or Mock()
		if configure_transport:
			configure_transport(transport)
		with patch("huf.ai.tools.ssh_execution.socket.create_connection", return_value=Mock()), \
				patch("huf.ai.tools.ssh_execution.paramiko.Transport", return_value=transport):
			execute_job(
				call.name,
				command=command,
				policy_snapshot={"limits": limits or {}},
				acting_user=user,
				connection_name=connection.name,
				agent_name=agent.name,
			)
		call.reload()
		return call, transport


class TestSSHExecutionGating(_SSHExecutionTestBase):
	"""run_ssh_command refusals before any network access happens."""

	def test_empty_command_rejected(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_ssh_command(connection.name, "   ", agent_doc=agent.name)

	def test_denied_without_capability(self):
		user = self._make_user(roles=())
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			run_ssh_command(connection.name, "echo hi", agent_doc=agent.name)

	def test_denied_when_agent_flag_off(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(allow_ssh=0, ssh_connections=[connection.name])
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_ssh_command(connection.name, "echo hi", agent_doc=agent.name)

	def test_denied_when_connection_not_allowlisted(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			run_ssh_command(connection.name, "echo hi", agent_doc=agent.name)

	def test_denied_when_connection_disabled(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection(enabled=0)
		agent = self._make_agent(ssh_connections=[connection.name])
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_ssh_command(connection.name, "echo hi", agent_doc=agent.name)

	def test_denied_when_connection_has_no_host_key(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection(host_key_fingerprint="")
		agent = self._make_agent(ssh_connections=[connection.name])
		frappe.set_user(user)
		with self.assertRaises(frappe.ValidationError):
			run_ssh_command(connection.name, "echo hi", agent_doc=agent.name)


class TestSSHExecutionRedaction(_SSHExecutionTestBase):
	def test_pending_approval_payloads_carry_no_secret(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		frappe.set_user(user)
		with patch(
			"huf.ai.tools.ssh_execution.socket.create_connection",
			side_effect=AssertionError("no network access expected before approval"),
		):
			result = run_ssh_command(connection.name, "cat /etc/passwd", agent_doc=agent.name)

		self.assertEqual(result["status"], "Pending Approval")
		self._tool_calls.append(result["agent_tool_call"])
		self._approvals.append(result["approval"])

		call = frappe.get_doc("Agent Tool Call", result["agent_tool_call"])
		self.assertNotIn("secret-pass", json.dumps(call.tool_args or {}))
		self.assertNotIn("cat /etc/passwd", json.dumps(call.tool_args or {}))
		self.assertNotIn("secret-pass", json.dumps(call.execution_profile_snapshot or {}))

		cache_key = f"huf_pending_ssh_execution:{result['approval']}"
		raw = frappe.cache().get_value(cache_key)
		self.assertTrue(raw)
		self.assertNotIn("secret-pass", raw)
		frappe.cache().delete_key(cache_key)

	def test_auth_failure_does_not_leak_password(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		call, _ = self._run_execute_job(
			connection,
			agent,
			user,
			configure_transport=lambda t: setattr(
				t.auth_password, "side_effect", Exception("auth boom")
			),
		)
		self.assertEqual(call.status, "Failed")
		self.assertIn("auth boom", call.error_message or "")
		self.assertNotIn("secret-pass", call.error_message or "")
		self.assertNotIn("secret-pass", json.dumps(call.resource_usage or {}))


class TestSSHHostKeyVerification(_SSHExecutionTestBase):
	def test_host_key_mismatch_rejected(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		call, transport = self._run_execute_job(
			connection, agent, user, key_bytes=b"evil-key"
		)
		self.assertEqual(call.status, "Failed")
		self.assertIn("host key mismatch", call.error_message or "")
		transport.close.assert_called()

	def test_host_key_type_mismatch_rejected(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection(host_key_type="ssh-rsa")
		agent = self._make_agent(ssh_connections=[connection.name])
		call, transport = self._run_execute_job(
			connection, agent, user, key_name="ssh-ed25519"
		)
		self.assertEqual(call.status, "Failed")
		self.assertIn("host key type mismatch", call.error_message or "")
		transport.close.assert_called()

	def test_authentication_failure_rejected(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		call, transport = self._run_execute_job(connection, agent, user, authenticated=False)
		self.assertEqual(call.status, "Failed")
		self.assertIn("authentication failed", (call.error_message or "").lower())
		transport.close.assert_called()


class TestSSHExecutionLimits(_SSHExecutionTestBase):
	def test_execution_timeout_marks_call_failed(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		channel = Mock()
		channel.recv_ready.return_value = False
		channel.recv_stderr_ready.return_value = False
		channel.exit_status_ready.return_value = False
		with patch("huf.ai.tools.ssh_execution.time.monotonic", side_effect=[0.0, 9999.0, 9999.0]), \
				patch("huf.ai.tools.ssh_execution.select.select", return_value=([], [], [])):
			call, _ = self._run_execute_job(
				connection,
				agent,
				user,
				limits={"execution_timeout_seconds": 10, "idle_timeout_seconds": 99999},
				channel=channel,
			)
		self.assertEqual(call.status, "Failed")
		self.assertEqual(call.exit_status, "Timeout")
		self.assertEqual(call.limits_hit, 1)
		self.assertTrue(call.resource_usage["timed_out"])
		channel.close.assert_called()

	def test_idle_timeout_marks_call_killed(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		channel = Mock()
		channel.recv_ready.return_value = False
		channel.recv_stderr_ready.return_value = False
		channel.exit_status_ready.return_value = False
		with patch("huf.ai.tools.ssh_execution.time.monotonic", side_effect=[0.0, 40.0, 40.0]), \
				patch("huf.ai.tools.ssh_execution.select.select", return_value=([], [], [])):
			call, _ = self._run_execute_job(
				connection,
				agent,
				user,
				limits={"execution_timeout_seconds": 99999, "idle_timeout_seconds": 30},
				channel=channel,
			)
		self.assertEqual(call.status, "Failed")
		self.assertEqual(call.exit_status, "Killed")
		self.assertEqual(call.limits_hit, 1)
		self.assertTrue(call.resource_usage["idle_timed_out"])
		channel.close.assert_called()

	def test_stdout_capture_bounded_by_limit(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		channel = Mock()
		channel.recv_ready.return_value = True
		channel.recv.side_effect = lambda n: b"a" * n
		channel.recv_stderr_ready.return_value = False
		channel.exit_status_ready.return_value = False
		with patch("huf.ai.tools.ssh_execution.time.monotonic", return_value=0.0), \
				patch("huf.ai.tools.ssh_execution.select.select", return_value=([channel], [], [])):
			call, _ = self._run_execute_job(
				connection,
				agent,
				user,
				limits={"stdout_max_bytes": 16},
				channel=channel,
			)
		self.assertEqual(call.limits_hit, 1)
		self.assertEqual(call.tool_result["stdout"], "a" * 16)
		channel.close.assert_called()

	def test_stderr_capture_bounded_by_limit(self):
		user = self._make_user(roles=("Huf User",))
		connection = self._make_connection()
		agent = self._make_agent(ssh_connections=[connection.name])
		channel = Mock()
		channel.recv_ready.return_value = False
		channel.recv_stderr_ready.return_value = True
		channel.recv_stderr.side_effect = lambda n: b"e" * n
		channel.exit_status_ready.return_value = False
		with patch("huf.ai.tools.ssh_execution.time.monotonic", return_value=0.0), \
				patch("huf.ai.tools.ssh_execution.select.select", return_value=([channel], [], [])):
			call, _ = self._run_execute_job(
				connection,
				agent,
				user,
				limits={"stderr_max_bytes": 8},
				channel=channel,
			)
		self.assertEqual(call.limits_hit, 1)
		self.assertEqual(call.tool_result["stderr"], "e" * 8)
		channel.close.assert_called()


if __name__ == "__main__":
	unittest.main()
