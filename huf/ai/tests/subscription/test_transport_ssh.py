"""Tests for SSHExecTransport.

Tests cover:
- Host-key mismatch failure
- Successful exec with stdout/stderr/exit-code capture
- Timeout enforcement
- File staging and cleanup
- Error sanitization (no credentials leaked)
- Connection validation at initialization
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from huf.ai.subscription.transports.base import ProcessResult, StagedFile
from huf.ai.subscription.transports.ssh import SSHExecTransport


class MockSSHConnection:
	"""Mock Frappe SSH Connection DocType."""

	def __init__(self, name="test-ssh"):
		self.name = name
		self.enabled = True
		self.host = "example.com"
		self.port = 22
		self.username = "user"
		self.auth_method = "Password"
		self.host_key_fingerprint = "SHA256:expected_fingerprint"
		self.host_key_type = "ssh-rsa"

	def get_password(self, field, raise_exception=True):
		if field == "password":
			return "actual_password"
		if field == "private_key":
			return "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
		if field == "private_key_passphrase":
			return None
		if raise_exception:
			raise KeyError(f"Unknown field: {field}")
		return None


@pytest.fixture
def mock_frappe():
	"""Mock frappe module."""
	with patch("huf.ai.subscription.transports.ssh.frappe") as mock:
		yield mock


@pytest.fixture
def mock_connection_doc():
	"""Create a mock SSH Connection document."""
	return MockSSHConnection()


@pytest.fixture
async def mock_transport_setup(mock_frappe, mock_connection_doc):
	"""Setup mock for connect_transport and run_exec_over_transport."""
	with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
	     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

		mock_frappe.get_doc.return_value = mock_connection_doc

		# Setup default mock transport
		mock_transport = MagicMock()
		mock_connect.return_value = (mock_transport, "SHA256:expected_fingerprint", "ssh-rsa")

		# Setup default mock exec result
		mock_result = MagicMock()
		mock_result.stdout = "test output"
		mock_result.stderr = ""
		mock_result.exit_code = 0
		mock_result.timed_out = False
		mock_result.idle_timed_out = False
		mock_run.return_value = mock_result

		yield {
			"frappe": mock_frappe,
			"connect": mock_connect,
			"run": mock_run,
			"transport": mock_transport,
			"result": mock_result,
			"connection_doc": mock_connection_doc,
		}


class TestSSHExecTransportInitialization:
	"""Test transport initialization and validation."""

	def test_init_with_valid_connection(self, mock_frappe, mock_connection_doc):
		"""Test successful initialization with enabled SSH Connection."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		transport = SSHExecTransport("test-ssh")

		assert transport.ssh_connection_name == "test-ssh"
		assert transport.limits["execution_timeout_seconds"] == 300

	def test_init_connection_not_found(self, mock_frappe):
		"""Test initialization fails when SSH Connection doesn't exist."""
		mock_frappe.DoesNotExistError = Exception
		mock_frappe.get_doc.side_effect = Exception("Not found")

		with pytest.raises(Exception):
			SSHExecTransport("nonexistent")

	def test_init_connection_disabled(self, mock_frappe, mock_connection_doc):
		"""Test initialization fails when SSH Connection is disabled."""
		mock_connection_doc.enabled = False
		mock_frappe.get_doc.return_value = mock_connection_doc
		mock_frappe.ValidationError = ValueError

		with pytest.raises(ValueError, match="disabled"):
			SSHExecTransport("test-ssh")

	def test_init_no_host_key_fingerprint(self, mock_frappe, mock_connection_doc):
		"""Test initialization fails when host-key fingerprint not enrolled."""
		mock_connection_doc.host_key_fingerprint = ""
		mock_frappe.get_doc.return_value = mock_connection_doc
		mock_frappe.ValidationError = ValueError

		with pytest.raises(ValueError, match="fingerprint"):
			SSHExecTransport("test-ssh")


class TestSSHExecTransportProbe:
	"""Test the probe() method for reachability checks."""

	@pytest.mark.asyncio
	async def test_probe_success(self, mock_frappe, mock_connection_doc):
		"""Test successful probe when SSH is reachable."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect:
			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			transport = SSHExecTransport("test-ssh")
			probe_result = await transport.probe()

			assert probe_result.reachable is True
			assert probe_result.detail is None
			mock_transport.close.assert_called_once()

	@pytest.mark.asyncio
	async def test_probe_host_key_mismatch(self, mock_frappe, mock_connection_doc):
		"""Test probe fails with host-key mismatch."""
		mock_frappe.get_doc.return_value = mock_connection_doc
		mock_frappe.ValidationError = ValueError

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect:
			mock_connect.side_effect = ValueError("SSH host key mismatch for test-ssh. Expected X, got Y.")

			transport = SSHExecTransport("test-ssh")
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert "key mismatch" in probe_result.detail.lower()

	@pytest.mark.asyncio
	async def test_probe_connection_refused(self, mock_frappe, mock_connection_doc):
		"""Test probe fails when connection is refused."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect:
			mock_connect.side_effect = OSError("Connection refused")

			transport = SSHExecTransport("test-ssh")
			probe_result = await transport.probe()

			assert probe_result.reachable is False
			assert probe_result.detail is not None


class TestSSHExecTransportRun:
	"""Test the run() method for command execution."""

	@pytest.mark.asyncio
	async def test_run_simple_command_success(self, mock_frappe, mock_connection_doc):
		"""Test successful command execution."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = "hello world"
			mock_result.stderr = ""
			mock_result.exit_code = 0
			mock_result.timed_out = False
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			result = await transport.run(["echo", "hello world"])

			assert isinstance(result, ProcessResult)
			assert result.stdout == "hello world"
			assert result.stderr == ""
			assert result.exit_code == 0
			assert result.timed_out is False

	@pytest.mark.asyncio
	async def test_run_with_stderr(self, mock_frappe, mock_connection_doc):
		"""Test capturing stderr from command execution."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = ""
			mock_result.stderr = "error message"
			mock_result.exit_code = 1
			mock_result.timed_out = False
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			result = await transport.run(["ls", "/nonexistent"])

			assert result.stdout == ""
			assert result.stderr == "error message"
			assert result.exit_code == 1

	@pytest.mark.asyncio
	async def test_run_with_timeout_flag(self, mock_frappe, mock_connection_doc):
		"""Test timeout detection."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = "partial output"
			mock_result.stderr = ""
			mock_result.exit_code = None
			mock_result.timed_out = True
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			result = await transport.run(["sleep", "1000"])

			assert result.timed_out is True

	@pytest.mark.asyncio
	async def test_run_with_custom_timeout(self, mock_frappe, mock_connection_doc):
		"""Test custom timeout parameter is passed to limits."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = ""
			mock_result.stderr = ""
			mock_result.exit_code = 0
			mock_result.timed_out = False
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			await transport.run(["echo", "test"], timeout=60)

			# Check that limits were passed with custom timeout
			call_args = mock_run.call_args
			assert call_args[0][2]["execution_timeout_seconds"] == 60

	@pytest.mark.asyncio
	async def test_run_with_cwd(self, mock_frappe, mock_connection_doc):
		"""Test command execution with working directory."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = "/tmp"
			mock_result.stderr = ""
			mock_result.exit_code = 0
			mock_result.timed_out = False
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			await transport.run(["pwd"], cwd="/tmp")

			# Check that cd was prepended to command
			call_args = mock_run.call_args
			command = call_args[0][1]
			assert "cd /tmp" in command

	@pytest.mark.asyncio
	async def test_run_with_env(self, mock_frappe, mock_connection_doc):
		"""Test command execution with environment variables."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.stdout = "value"
			mock_result.stderr = ""
			mock_result.exit_code = 0
			mock_result.timed_out = False
			mock_result.idle_timed_out = False
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			await transport.run(["echo", "$MY_VAR"], env={"MY_VAR": "value"})

			# Check that export was prepended
			call_args = mock_run.call_args
			command = call_args[0][1]
			assert "export MY_VAR=" in command

	@pytest.mark.asyncio
	async def test_run_empty_argv(self, mock_frappe, mock_connection_doc):
		"""Test run with empty argv returns empty result."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		transport = SSHExecTransport("test-ssh")
		result = await transport.run([])

		assert result.stdout == ""
		assert result.stderr == ""
		assert result.exit_code is None


class TestSSHExecTransportStaging:
	"""Test file staging and cleanup."""

	@pytest.mark.asyncio
	async def test_stage_file_success(self, mock_frappe, mock_connection_doc):
		"""Test successful file staging via SFTP."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.paramiko.SFTPClient") as mock_sftp_cls, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_sftp = MagicMock()
			mock_sftp_cls.from_transport.return_value = mock_sftp

			# Mock mkdir result
			mkdir_result = MagicMock()
			mkdir_result.exit_code = 0
			mkdir_result.stderr = ""
			mock_run.return_value = mkdir_result

			transport = SSHExecTransport("test-ssh")

			# Create a temporary test file
			with tempfile.NamedTemporaryFile(delete=False) as tmp:
				tmp.write(b"test content")
				tmp_path = tmp.name

			try:
				staged = await transport.stage_file(tmp_path, target_name="test.txt")

				assert staged.remote_path.endswith("test.txt")
				assert staged.local_path == tmp_path
				assert staged.cleanup is not None
				mock_sftp.put.assert_called_once()
			finally:
				os.unlink(tmp_path)

	@pytest.mark.asyncio
	async def test_stage_file_not_found(self, mock_frappe, mock_connection_doc):
		"""Test staging a non-existent file raises error."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		transport = SSHExecTransport("test-ssh")

		with pytest.raises(FileNotFoundError):
			await transport.stage_file("/nonexistent/path/file.txt")

	@pytest.mark.asyncio
	async def test_remove_staged_file(self, mock_frappe, mock_connection_doc):
		"""Test removing a staged file."""
		mock_frappe.get_doc.return_value = mock_connection_doc

		with patch("huf.ai.subscription.transports.ssh.connect_transport") as mock_connect, \
		     patch("huf.ai.subscription.transports.ssh.run_exec_over_transport") as mock_run:

			mock_transport = MagicMock()
			mock_connect.return_value = (mock_transport, "SHA256:...", "ssh-rsa")

			mock_result = MagicMock()
			mock_result.exit_code = 0
			mock_result.stderr = ""
			mock_run.return_value = mock_result

			transport = SSHExecTransport("test-ssh")
			staged = StagedFile(
				remote_path="/tmp/test.txt",
				local_path="/local/test.txt",
			)

			await transport.remove_staged_file(staged)

			# Verify rm command was executed
			call_args = mock_run.call_args
			assert "/bin/rm" in call_args[0][0]


class TestSSHExecTransportErrorSanitization:
	"""Test that sensitive information is not leaked in errors."""

	def test_sanitize_error_with_password(self):
		"""Test that password-related errors are sanitized."""
		msg = "SSH authentication failed: password incorrect"
		sanitized = SSHExecTransport._sanitize_error_message(msg)
		assert "password" not in sanitized.lower() or "redacted" in sanitized.lower()

	def test_sanitize_error_with_key(self):
		"""Test that private key errors are sanitized."""
		msg = "SSH authentication failed: private_key format invalid"
		sanitized = SSHExecTransport._sanitize_error_message(msg)
		assert "redacted" in sanitized.lower()

	def test_sanitize_error_with_token(self):
		"""Test that token errors are sanitized."""
		msg = "Authentication failed: token expired"
		sanitized = SSHExecTransport._sanitize_error_message(msg)
		assert "redacted" in sanitized.lower()

	def test_sanitize_error_generic(self):
		"""Test that generic errors pass through."""
		msg = "Connection timeout after 10 seconds"
		sanitized = SSHExecTransport._sanitize_error_message(msg)
		# Generic errors are not sanitized
		assert "timeout" in sanitized.lower()
