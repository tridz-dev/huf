"""Low-level SSH connection and command execution primitives.

This module provides the foundational SSH operations that are reused by both
the Agent Tool (run_ssh_command) and the Subscription Provider runtime transports.

Extracted from ssh_execution.py to avoid duplication and ensure strict host-key
verification is always applied consistently.
"""

from __future__ import annotations

import base64
import hashlib
import io
import select
import socket
import time
from dataclasses import dataclass
from typing import Any

import frappe
import paramiko


DEFAULT_CONNECTION_TIMEOUT_S = 10
DEFAULT_EXECUTION_TIMEOUT_S = 300
DEFAULT_IDLE_TIMEOUT_S = 30
DEFAULT_STDOUT_MAX_BYTES = 65536
DEFAULT_STDERR_MAX_BYTES = 65536
DEFAULT_COMBINED_OUTPUT_MAX_BYTES = 131072


@dataclass
class SSHPrimitiveResult:
	"""Result of a low-level SSH exec operation."""

	stdout: str
	stderr: str
	exit_code: int | None
	exit_status: str
	wall_s: float
	output_bytes: int
	limits_hit: bool
	host_key_fingerprint: str
	host_key_type: str
	timed_out: bool = False
	idle_timed_out: bool = False


def fingerprint_for_key(server_key) -> str:
	"""Compute SHA-256 fingerprint of an SSH server key.

	Returns:
		str: Fingerprint in format "SHA256:..." (unpadded base64)
	"""
	digest = hashlib.sha256(server_key.asbytes()).digest()
	return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def load_private_key(private_key: str, passphrase: str | None):
	"""Load and parse a private SSH key.

	Tries Ed25519, RSA, ECDSA, and (on compatible Paramiko versions) DSS keys.

	Args:
		private_key: PEM-encoded private key string
		passphrase: Optional passphrase for encrypted keys

	Returns:
		Paramiko key object suitable for auth_publickey()

	Raises:
		frappe.ValidationError: If key cannot be parsed by any supported key class
	"""
	password = passphrase or None
	key_classes = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey]
	# DSSKey was removed from newer Paramiko releases. Keep compatibility with
	# old installations without making all private-key auth fail at import time.
	dss_key = getattr(paramiko, "DSSKey", None)
	if dss_key is not None:
		key_classes.append(dss_key)
	for key_cls in key_classes:
		try:
			return key_cls.from_private_key(io.StringIO(private_key), password=password)
		except Exception:
			continue
	frappe.throw("Unsupported or invalid private key.", frappe.ValidationError)


def connect_transport(connection_doc, limits: dict) -> tuple[paramiko.Transport, str, str]:
	"""Create an authenticated Paramiko transport with strict host-key verification.

	This function:
	  1. Opens a socket to the SSH host/port
	  2. Creates a Paramiko Transport
	  3. Retrieves and verifies the server's host key
	  4. Compares SHA-256 fingerprint to enrolled fingerprint (strict pinning)
	  5. Authenticates using either password or private key
	  6. Validates successful authentication

	Args:
		connection_doc: SSH Connection DocType instance with:
			- host, port, username, auth_method (Password or Private Key)
			- host_key_fingerprint (enrolled SHA-256 fingerprint)
			- host_key_type (optional key type constraint)
			- password or private_key + private_key_passphrase fields
		limits: dict with timeout_seconds (or uses DEFAULT_CONNECTION_TIMEOUT_S)

	Returns:
		Tuple of (transport, fingerprint, key_type_name)
		- transport: authenticated Paramiko Transport ready for exec_command()
		- fingerprint: computed SHA-256 fingerprint
		- key_type_name: SSH key type name (e.g., "ssh-rsa")

	Raises:
		frappe.ValidationError: Host key mismatch or invalid configuration
		frappe.PermissionError: Authentication failed
		socket.error: Connection failed
	"""
	timeout = int(limits.get("connection_timeout_seconds") or DEFAULT_CONNECTION_TIMEOUT_S)
	sock = socket.create_connection((connection_doc.host, int(connection_doc.port or 22)), timeout=timeout)
	transport = paramiko.Transport(sock)
	transport.banner_timeout = timeout
	transport.handshake_timeout = timeout
	transport.auth_timeout = timeout
	transport.start_client(timeout=timeout)
	server_key = transport.get_remote_server_key()
	fingerprint = fingerprint_for_key(server_key)
	expected = (connection_doc.host_key_fingerprint or "").strip()
	if fingerprint != expected:
		transport.close()
		frappe.throw(
			f"SSH host key mismatch for {connection_doc.name}. Expected {expected}, got {fingerprint}.",
			frappe.ValidationError,
		)
	if (connection_doc.host_key_type or "").strip() and server_key.get_name() != connection_doc.host_key_type:
		transport.close()
		frappe.throw(
			f"SSH host key type mismatch for {connection_doc.name}. Expected {connection_doc.host_key_type}, got {server_key.get_name()}.",
			frappe.ValidationError,
		)

	if connection_doc.auth_method == "Password":
		transport.auth_password(
			username=connection_doc.username,
			password=connection_doc.get_password("password"),
		)
	else:
		pkey = load_private_key(
			connection_doc.get_password("private_key"),
			connection_doc.get_password("private_key_passphrase", raise_exception=False),
		)
		transport.auth_publickey(username=connection_doc.username, key=pkey)

	if not transport.is_authenticated():
		transport.close()
		frappe.throw("SSH authentication failed.", frappe.PermissionError)
	return transport, fingerprint, server_key.get_name()


def run_exec_over_transport(
	transport: paramiko.Transport,
	command: str,
	limits: dict,
	fingerprint: str,
	host_key_type: str,
) -> SSHPrimitiveResult:
	"""Execute a one-shot remote command over an authenticated transport.

	Captures stdout/stderr with bounded size and timeout limits.
	No PTY is used (non-interactive exec only).

	Args:
		transport: Authenticated Paramiko Transport from connect_transport()
		command: Shell command string to execute remotely
		limits: dict with:
			- connection_timeout_seconds (for channel open; default 10s)
			- execution_timeout_seconds (total timeout; default 300s)
			- idle_timeout_seconds (inactivity timeout; default 30s)
			- stdout_max_bytes (per-stream limit; default 65536)
			- stderr_max_bytes (per-stream limit; default 65536)
			- combined_output_max_bytes (total limit; default 131072)
		fingerprint: Host key fingerprint (for result metadata)
		host_key_type: SSH key type name (for result metadata)

	Returns:
		SSHPrimitiveResult with stdout, stderr, exit_code, and timing/limit metadata

	Notes:
		- Uses select() to multiplex stdout/stderr reads
		- Enforces execution timeout (total elapsed time)
		- Enforces idle timeout (time since last I/O progress)
		- Respects per-stream and combined output size limits
		- Output beyond limits is silently truncated; limits_hit flag is set
		- Timeout flags indicate which limit was hit
	"""
	channel = transport.open_session(timeout=int(limits.get("connection_timeout_seconds") or DEFAULT_CONNECTION_TIMEOUT_S))
	channel.set_combine_stderr(False)
	channel.exec_command(command)

	execution_timeout = int(limits.get("execution_timeout_seconds") or DEFAULT_EXECUTION_TIMEOUT_S)
	idle_timeout = int(limits.get("idle_timeout_seconds") or DEFAULT_IDLE_TIMEOUT_S)
	stdout_limit = int(limits.get("stdout_max_bytes") or DEFAULT_STDOUT_MAX_BYTES)
	stderr_limit = int(limits.get("stderr_max_bytes") or DEFAULT_STDERR_MAX_BYTES)
	combined_limit = int(limits.get("combined_output_max_bytes") or DEFAULT_COMBINED_OUTPUT_MAX_BYTES)
	start = time.monotonic()
	last_progress = start
	stdout = bytearray()
	stderr = bytearray()
	limits_hit = False
	timed_out = False
	idle_timed_out = False

	while True:
		now = time.monotonic()
		if now - start > execution_timeout:
			timed_out = True
			limits_hit = True
			channel.close()
			break
		if now - last_progress > idle_timeout:
			idle_timed_out = True
			limits_hit = True
			channel.close()
			break

		wait_s = min(1.0, max(0.1, idle_timeout - (now - last_progress)))
		ready, _, _ = select.select([channel], [], [], wait_s)
		progress = False

		if ready and channel.recv_ready():
			chunk = channel.recv(min(4096, max(1, stdout_limit - len(stdout))))
			if chunk:
				stdout.extend(chunk)
				progress = True
		if ready and channel.recv_stderr_ready():
			chunk = channel.recv_stderr(min(4096, max(1, stderr_limit - len(stderr))))
			if chunk:
				stderr.extend(chunk)
				progress = True

		if len(stdout) >= stdout_limit or len(stderr) >= stderr_limit or (len(stdout) + len(stderr)) >= combined_limit:
			limits_hit = True
			channel.close()
			break

		if progress:
			last_progress = time.monotonic()

		if channel.exit_status_ready():
			while channel.recv_ready() and len(stdout) < stdout_limit:
				chunk = channel.recv(min(4096, max(1, stdout_limit - len(stdout))))
				if not chunk:
					break
				stdout.extend(chunk)
			while channel.recv_stderr_ready() and len(stderr) < stderr_limit:
				chunk = channel.recv_stderr(min(4096, max(1, stderr_limit - len(stderr))))
				if not chunk:
					break
				stderr.extend(chunk)
			break

	exit_code = channel.recv_exit_status() if channel.exit_status_ready() else None
	wall_s = time.monotonic() - start
	status = "Ok"
	if timed_out:
		status = "Timeout"
	elif idle_timed_out:
		status = "Killed"
	elif exit_code not in (None, 0):
		status = "Error"
	return SSHPrimitiveResult(
		stdout=stdout.decode("utf-8", errors="replace"),
		stderr=stderr.decode("utf-8", errors="replace"),
		exit_code=exit_code,
		exit_status=status,
		wall_s=wall_s,
		output_bytes=len(stdout) + len(stderr),
		limits_hit=limits_hit,
		host_key_fingerprint=fingerprint,
		host_key_type=host_key_type,
		timed_out=timed_out,
		idle_timed_out=idle_timed_out,
	)
