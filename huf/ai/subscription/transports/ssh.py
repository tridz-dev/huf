"""SSH-based execution transport for subscription provider runtime.

Provides remote command execution and file staging via SSH using HUF's
existing SSH Connection security model (strict host-key pinning, encrypted
password/key storage).
"""

from __future__ import annotations

import asyncio
import os
import shlex
import uuid
from typing import Any

import frappe
import paramiko

from huf.ai.subscription.transports.base import (
	ExecutionTransport,
	ProcessResult,
	StagedFile,
	TransportProbe,
)
from huf.ai.tools.ssh_connection_primitive import (
	DEFAULT_CONNECTION_TIMEOUT_S,
	DEFAULT_EXECUTION_TIMEOUT_S,
	DEFAULT_IDLE_TIMEOUT_S,
	connect_transport,
	run_exec_over_transport,
)

# Output limits for structured event streams (JSONL, JSON)
# Larger than the default SSH tool limits (131KB) to accommodate structured data
DEFAULT_COMBINED_OUTPUT_MAX_BYTES = 1024 * 1024  # 1MB

# Directory for staging files on remote host
STAGING_BASE_DIR = "/tmp/huf-subscription"


class SSHExecTransport(ExecutionTransport):
	"""SSH-based execution transport using HUF SSH Connection.

	Provides one-shot non-interactive command execution via SSH and file staging
	through SFTP, reusing HUF's existing SSH Connection security model.

	The transport is stateless: each command execution is independent, and the
	underlying SSH connection is created fresh and closed after each operation.

	Args:
		ssh_connection_name: Name of an SSH Connection DocType (must be enabled,
			with valid host-key fingerprint enrolled)
		connection_timeout_seconds: Timeout for establishing the SSH connection
		execution_timeout_seconds: Total timeout for command execution
		idle_timeout_seconds: Timeout for idle I/O (no progress)
		max_output_bytes: Maximum total output (stdout + stderr) to capture

	Raises:
		frappe.DoesNotExistError: SSH Connection not found
		frappe.ValidationError: SSH Connection missing required fields
	"""

	def __init__(
		self,
		ssh_connection_name: str,
		connection_timeout_seconds: int = DEFAULT_CONNECTION_TIMEOUT_S,
		execution_timeout_seconds: int = DEFAULT_EXECUTION_TIMEOUT_S,
		idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_S,
		max_output_bytes: int = DEFAULT_COMBINED_OUTPUT_MAX_BYTES,
	) -> None:
		"""Initialize SSH execution transport.

		Args:
			ssh_connection_name: Name of SSH Connection DocType
			connection_timeout_seconds: Connection timeout in seconds
			execution_timeout_seconds: Execution timeout in seconds
			idle_timeout_seconds: Idle timeout in seconds
			max_output_bytes: Maximum combined output size in bytes
		"""
		self.ssh_connection_name = ssh_connection_name
		self.limits = {
			"connection_timeout_seconds": connection_timeout_seconds,
			"execution_timeout_seconds": execution_timeout_seconds,
			"idle_timeout_seconds": idle_timeout_seconds,
			"combined_output_max_bytes": max_output_bytes,
			"stdout_max_bytes": max_output_bytes,
			"stderr_max_bytes": max_output_bytes,
		}

		# Validate the connection exists and is enabled
		try:
			self._connection_doc = frappe.get_doc("SSH Connection", ssh_connection_name)
		except frappe.DoesNotExistError:
			raise frappe.DoesNotExistError(f"SSH Connection '{ssh_connection_name}' not found")

		if not getattr(self._connection_doc, "enabled", False):
			raise frappe.ValidationError(f"SSH Connection '{ssh_connection_name}' is disabled")

		if not (self._connection_doc.host_key_fingerprint or "").strip():
			raise frappe.ValidationError(
				f"SSH Connection '{ssh_connection_name}' has no enrolled host key fingerprint"
			)

		self._staging_dir: str | None = None
		self._run_id = str(uuid.uuid4())

	async def probe(self) -> TransportProbe:
		"""Check if the SSH target is reachable.

		Attempts to connect to the SSH host, verify the host key, and authenticate.
		Does not execute any command; purely a reachability check.

		Returns:
			TransportProbe with reachable=True on success, False with error detail on failure
		"""
		try:
			transport, _, _ = connect_transport(self._connection_doc, self.limits)
			transport.close()
			return TransportProbe(reachable=True)
		except Exception as exc:
			return TransportProbe(reachable=False, detail=self._sanitize_error_message(str(exc)))

	async def run(
		self,
		argv: list[str],
		*,
		cwd: str | None = None,
		env: dict[str, str] | None = None,
		stdin: str | None = None,
		timeout: int | None = None,
	) -> ProcessResult:
		"""Execute a command over SSH.

		Executes the command as a single non-interactive remote exec call (no PTY).
		Arguments are shell-escaped via shlex.join() for safe transmission.

		Args:
			argv: Command as list of arguments
			cwd: Working directory (passed via 'cd' prepend)
			env: Environment variables (passed via 'export' prepend)
			stdin: Standard input (sent to command via pipe)
			timeout: Override for execution timeout in seconds

		Returns:
			ProcessResult with captured stdout/stderr and exit code

		Raises:
			frappe.ValidationError: Host key mismatch, authentication failed
			frappe.PermissionError: SSH access denied
			Exception: Other transport-specific errors
		"""
		if not argv:
			return ProcessResult(stdout="", stderr="", exit_code=None)

		# Build the remote command
		command_parts = []

		if env:
			for key, value in env.items():
				command_parts.append(f"export {key}={shlex.quote(value)}")

		if cwd:
			command_parts.append(f"cd {shlex.quote(cwd)}")

		command_parts.append(shlex.join(argv))
		remote_command = " && ".join(command_parts)

		# Use provided timeout or default
		limits = dict(self.limits)
		if timeout is not None:
			limits["execution_timeout_seconds"] = timeout

		# Execute via SSH
		try:
			transport, fingerprint, host_key_type = connect_transport(self._connection_doc, limits)
			try:
				result = run_exec_over_transport(transport, remote_command, limits, fingerprint, host_key_type)
				return ProcessResult(
					stdout=result.stdout,
					stderr=result.stderr,
					exit_code=result.exit_code,
					timed_out=result.timed_out or result.idle_timed_out,
				)
			finally:
				try:
					transport.close()
				except Exception:
					pass
		except Exception as exc:
			# Sanitize error to avoid leaking credentials
			sanitized_msg = self._sanitize_error_message(str(exc))
			raise Exception(f"SSH transport error: {sanitized_msg}") from exc

	async def stage_file(
		self,
		source_path: str,
		*,
		target_name: str | None = None,
	) -> StagedFile:
		"""Copy a file to the remote host via SFTP.

		Creates a staging directory (/tmp/huf-subscription/<run-id>/) on the remote
		host and copies the file there. Returns a StagedFile with a cleanup callable.

		Args:
			source_path: Local path to the file
			target_name: Optional filename on the remote (defaults to basename)

		Returns:
			StagedFile with remote_path and cleanup callable

		Raises:
			FileNotFoundError: Source file not found
			Exception: SFTP transfer or permission error
		"""
		if not os.path.exists(source_path):
			raise FileNotFoundError(f"File not found: {source_path}")

		if target_name is None:
			target_name = os.path.basename(source_path)

		# Ensure staging directory exists on remote
		if self._staging_dir is None:
			self._staging_dir = f"{STAGING_BASE_DIR}/{self._run_id}"
			mkdir_command = f"mkdir -p {shlex.quote(self._staging_dir)}"
			result = await self.run(["/bin/sh", "-c", mkdir_command])
			if result.exit_code not in (None, 0):
				raise Exception(f"Failed to create staging directory: {result.stderr}")

		remote_path = f"{self._staging_dir}/{target_name}"

		try:
			transport, _, _ = connect_transport(self._connection_doc, self.limits)
			try:
				sftp = paramiko.SFTPClient.from_transport(transport)
				try:
					sftp.put(source_path, remote_path)
				finally:
					sftp.close()
			finally:
				try:
					transport.close()
				except Exception:
					pass
		except Exception as exc:
			sanitized_msg = self._sanitize_error_message(str(exc))
			raise Exception(f"SFTP staging failed: {sanitized_msg}") from exc

		async def cleanup() -> None:
			"""Remove the staged file."""
			try:
				await self.remove_staged_file(StagedFile(remote_path, source_path))
			except Exception:
				pass  # Best effort; don't fail if cleanup doesn't work

		return StagedFile(
			remote_path=remote_path,
			local_path=source_path,
			cleanup=cleanup,
		)

	async def remove_staged_file(self, staged_file: StagedFile) -> None:
		"""Remove a staged file from the remote host.

		Args:
			staged_file: StagedFile returned from stage_file()

		Raises:
			Exception: SFTP or SSH error
		"""
		try:
			result = await self.run(["/bin/rm", "-f", staged_file.remote_path])
			if result.exit_code not in (None, 0):
				# Log but don't raise; cleanup is best-effort
				frappe.log_error(
					title="HUF SSH Transport Staging Cleanup",
					message=f"Failed to remove {staged_file.remote_path}: {result.stderr}",
				)
		except Exception as exc:
			# Log but don't raise; cleanup is best-effort
			frappe.log_error(
				title="HUF SSH Transport Staging Cleanup",
				message=f"Error removing {staged_file.remote_path}: {exc}",
			)

	@staticmethod
	def _sanitize_error_message(msg: str) -> str:
		"""Remove sensitive information from error messages.

		Never include SSH password, private key material, or other credentials
		in exceptions that might be logged or exposed.

		Args:
			msg: Original error message

		Returns:
			Sanitized message with credential references removed
		"""
		# Common credential patterns to redact
		patterns = [
			"password",
			"private_key",
			"passphrase",
			"secret",
			"token",
			"auth",
		]

		# If the message contains any credential keywords, replace details
		msg_lower = msg.lower()
		if any(pattern in msg_lower for pattern in patterns):
			return "[SSH authentication or credential error - details redacted]"

		return msg
