"""SSH command execution tool for Huf.

First PR scope:
  - persistent encrypted SSH authentication via ``SSH Connection``;
  - one-shot remote ``exec`` only (no PTY);
  - per-call approval / pending payload resume;
  - strict host-key pin verification;
  - bounded stdout/stderr capture and timeouts.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import select
import socket
import time
from dataclasses import dataclass
from typing import Any

import frappe
import paramiko
from frappe.utils import add_to_date, now_datetime

from huf.permissions import has_capability

_TOOL_NAME = "run_ssh_command"
_APPROVAL_TTL_HOURS = 24
_PENDING_EXECUTION_PREFIX = "huf_pending_ssh_execution"

DEFAULT_CONNECTION_TIMEOUT_S = 10
DEFAULT_EXECUTION_TIMEOUT_S = 300
DEFAULT_IDLE_TIMEOUT_S = 30
DEFAULT_STDOUT_MAX_BYTES = 65536
DEFAULT_STDERR_MAX_BYTES = 65536
DEFAULT_COMBINED_OUTPUT_MAX_BYTES = 131072
DEFAULT_MAX_CONCURRENT_COMMANDS = 1


class PendingExecutionExpired(Exception):
	"""The Redis hold for a parked SSH execution expired before approval."""


@dataclass
class SSHExecutionResult:
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


def _as_agent_doc(agent_doc: Any) -> Any:
	if hasattr(agent_doc, "doctype"):
		return agent_doc
	return frappe.get_doc("Agent", agent_doc)


def _name_of(obj: Any) -> str | None:
	if obj is None:
		return None
	return getattr(obj, "name", None) or str(obj)


def _truncate(text: str | None, limit: int) -> str | None:
	if text is None:
		return None
	if len(text) <= limit:
		return text
	return text[:limit] + f"\n... [truncated; {len(text) - limit} chars omitted]"


def _sha256(text: str) -> str:
	return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _pending_execution_key(approval_name: str) -> str:
	return f"{_PENDING_EXECUTION_PREFIX}:{approval_name}"


def _fingerprint_for_key(server_key) -> str:
	digest = hashlib.sha256(server_key.asbytes()).digest()
	return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _load_private_key(private_key: str, passphrase: str | None):
	password = passphrase or None
	for key_cls in (
		paramiko.Ed25519Key,
		paramiko.RSAKey,
		paramiko.ECDSAKey,
		paramiko.DSSKey,
	):
		try:
			return key_cls.from_private_key(io.StringIO(private_key), password=password)
		except Exception:
			continue
	frappe.throw("Unsupported or invalid private key.", frappe.ValidationError)


def _has_allowlisted_connection(agent, connection_name: str) -> bool:
	for row in getattr(agent, "ssh_connections", None) or []:
		if row.ssh_connection == connection_name:
			return True
	return False


def _profile_for_ssh(agent) -> Any | None:
	profile_name = getattr(agent, "execution_profile", None)
	if not profile_name:
		return None
	try:
		profile = frappe.get_doc("Execution Profile", profile_name)
	except Exception:
		return None
	if getattr(profile, "disabled", 0):
		return None
	return profile


def _build_policy_snapshot(agent, connection_doc, timeout_seconds: int | None) -> dict:
	profile = _profile_for_ssh(agent)
	execution_timeout = int(timeout_seconds or DEFAULT_EXECUTION_TIMEOUT_S)
	return {
		"approval_mode": getattr(profile, "approval_mode", None) or "Ask Every Time",
		"network_policy": getattr(profile, "network_policy", None) or None,
		"limits": {
			"connection_timeout_seconds": DEFAULT_CONNECTION_TIMEOUT_S,
			"execution_timeout_seconds": execution_timeout,
			"idle_timeout_seconds": DEFAULT_IDLE_TIMEOUT_S,
			"stdout_max_bytes": DEFAULT_STDOUT_MAX_BYTES,
			"stderr_max_bytes": DEFAULT_STDERR_MAX_BYTES,
			"combined_output_max_bytes": DEFAULT_COMBINED_OUTPUT_MAX_BYTES,
			"max_concurrent_commands_per_connection": DEFAULT_MAX_CONCURRENT_COMMANDS,
		},
		"ssh_connection": connection_doc.name,
		"host": connection_doc.host,
		"port": int(connection_doc.port or 22),
	}


def _validate_agent_connection_for_user(agent_doc: Any, connection_name: str, acting_user: str):
	if not has_capability(acting_user, "ssh.run"):
		frappe.throw("You do not have permission to run SSH commands.", frappe.PermissionError)

	agent = _as_agent_doc(agent_doc)
	if not getattr(agent, "allow_ssh", None):
		frappe.throw("SSH execution is not enabled for this agent.", frappe.ValidationError)
	if not connection_name:
		frappe.throw("An SSH connection is required.", frappe.ValidationError)
	if not _has_allowlisted_connection(agent, connection_name):
		frappe.throw("This SSH connection is not allowlisted for the agent.", frappe.PermissionError)

	connection_doc = frappe.get_doc("SSH Connection", connection_name)
	if not getattr(connection_doc, "enabled", None):
		frappe.throw("The selected SSH connection is disabled.", frappe.ValidationError)
	if not (connection_doc.host_key_fingerprint or "").strip():
		frappe.throw(
			"The selected SSH connection has no enrolled host key fingerprint.",
			frappe.ValidationError,
		)
	return agent, connection_doc


def _validate_agent_and_connection(agent_doc: Any, connection_name: str):
	acting_user = frappe.session.user
	agent, connection_doc = _validate_agent_connection_for_user(agent_doc, connection_name, acting_user)
	return agent, connection_doc, acting_user


def _authorize_ssh_target(host: str, port: int, network_policy: str | None) -> str | None:
	"""Return None when SSH target is permitted by network policy, else reason."""
	if not network_policy:
		return None

	from huf.ai.tools.code_execution import _rule_host_matches, _rule_port_matches

	try:
		policy = frappe.get_doc("Network Access Policy", network_policy)
	except Exception:
		return f"SSH denied: network policy '{network_policy}' not found"

	for rule in policy.rules or []:
		if not _rule_host_matches(rule.host_or_cidr, host):
			continue
		if not _rule_port_matches(rule.port_range, port):
			continue
		protocol = (rule.protocol or "").strip().lower()
		if protocol and protocol not in ("ssh", "tcp"):
			continue
		return None

	return f"SSH denied: {host}:{port} is not allowed by network policy '{network_policy}'"


def stash_pending_execution(
	approval_name: str,
	*,
	command: str,
	policy_snapshot: dict,
	acting_user: str | None,
	connection_name: str,
	agent_name: str | None,
) -> None:
	payload = {
		"command": command,
		"code_ref": _sha256(command),
		"policy_snapshot": policy_snapshot or {},
		"acting_user": acting_user,
		"connection_name": connection_name,
		"agent_name": agent_name,
	}
	frappe.cache().set_value(
		_pending_execution_key(approval_name),
		json.dumps(payload),
		expires_in_sec=_APPROVAL_TTL_HOURS * 3600,
	)


def load_pending_execution(approval_doc) -> dict:
	raw = frappe.cache().get_value(_pending_execution_key(approval_doc.name))
	payload = None
	if raw:
		try:
			payload = json.loads(raw)
		except (TypeError, ValueError):
			payload = None
	if not isinstance(payload, dict):
		frappe.log_error(
			f"pending ssh execution hold for approval {approval_doc.name} is missing or corrupt",
			"Huf SSH Execution Approval",
		)
		raise PendingExecutionExpired(approval_doc.name)

	command = payload.get("command")
	if not isinstance(command, str) or not command or _sha256(command) != (approval_doc.code_ref or ""):
		frappe.throw(
			"The parked SSH execution payload failed its integrity check; refusing to enqueue.",
			frappe.ValidationError,
		)

	acting_user = payload.get("acting_user")
	if not isinstance(acting_user, str) or not acting_user:
		frappe.throw(
			"The original requesting user for this SSH execution is no longer resolvable; refusing to enqueue.",
			frappe.ValidationError,
		)

	connection_name = payload.get("connection_name")
	if not isinstance(connection_name, str) or not connection_name:
		frappe.throw(
			"The parked SSH execution has no connection reference; refusing to enqueue.",
			frappe.ValidationError,
		)

	agent_name = payload.get("agent_name")
	if not isinstance(agent_name, str) or not agent_name:
		frappe.throw(
			"The parked SSH execution has no agent reference; refusing to enqueue.",
			frappe.ValidationError,
		)

	return {
		"command": command,
		"policy_snapshot": payload.get("policy_snapshot") if isinstance(payload.get("policy_snapshot"), dict) else {},
		"acting_user": acting_user,
		"connection_name": connection_name,
		"agent_name": agent_name,
	}


def clear_pending_execution(approval_name: str) -> None:
	frappe.cache().delete_key(_pending_execution_key(approval_name))


def enqueue_approved_execution(approval_doc, payload: dict) -> None:
	enqueue_execution(
		approval_doc.agent_tool_call,
		command=payload["command"],
		policy_snapshot=payload["policy_snapshot"],
		acting_user=payload["acting_user"],
		connection_name=payload["connection_name"],
		agent_name=payload["agent_name"],
	)
	clear_pending_execution(approval_doc.name)


def run_ssh_command(
	connection: str,
	command: str,
	agent_doc: Any,
	conversation: Any = None,
	agent_run: Any = None,
	timeout_seconds: int | None = None,
	**kwargs: Any,
) -> dict:
	if not isinstance(command, str) or not command.strip():
		frappe.throw("A non-empty SSH command is required.", frappe.ValidationError)

	agent, connection_doc, acting_user = _validate_agent_and_connection(agent_doc, connection)
	policy_snapshot = _build_policy_snapshot(agent, connection_doc, timeout_seconds)
	denial = _authorize_ssh_target(
		connection_doc.host,
		int(connection_doc.port or 22),
		policy_snapshot.get("network_policy"),
	)
	if denial:
		frappe.throw(denial, frappe.PermissionError)

	command_ref = _sha256(command)
	call = frappe.get_doc(
		{
			"doctype": "Agent Tool Call",
			"agent_run": _name_of(agent_run),
			"conversation": _name_of(conversation),
			"tool": kwargs.get("tool_name") or _TOOL_NAME,
			"is_mcp_tool": 0,
			"tool_args": json.dumps({"command_ref": command_ref, "connection": connection_doc.name}),
			"status": "Started",
			"call_id": kwargs.get("call_id") or kwargs.get("tool_call_id"),
			"execution_kind": "exec",
			"ssh_connection": connection_doc.name,
			"execution_profile_snapshot": policy_snapshot,
			"code_ref": command_ref,
		}
	)
	call.insert(ignore_permissions=True)

	approval_mode = policy_snapshot.get("approval_mode") or "Ask Every Time"
	if approval_mode == "Never Allow":
		call.status = "Failed"
		call.error_message = "SSH execution not permitted by policy."
		call.exit_status = "Error"
		call.save(ignore_permissions=True)
		frappe.throw("SSH execution not permitted by policy.", frappe.PermissionError)

	if approval_mode == "Ask Every Time":
		approval = frappe.get_doc(
			{
				"doctype": "Agent Execution Approval",
				"agent_tool_call": call.name,
				"execution_kind": "ssh_exec",
				"requested_capability": "ssh.run",
				"code_ref": command_ref,
				"status": "Pending",
				"expires_on": add_to_date(now_datetime(), hours=_APPROVAL_TTL_HOURS),
			}
		)
		original_user = frappe.session.user
		try:
			frappe.set_user("Administrator")
			approval.insert(ignore_permissions=True)
		finally:
			frappe.set_user(original_user)
		stash_pending_execution(
			approval.name,
			command=command,
			policy_snapshot=policy_snapshot,
			acting_user=acting_user,
			connection_name=connection_doc.name,
			agent_name=agent.name,
		)
		call.status = "Queued"
		call.save(ignore_permissions=True)
		return {
			"success": True,
			"status": "Pending Approval",
			"agent_tool_call": call.name,
			"approval": approval.name,
			"command_ref": command_ref,
			"execution_kind": "exec",
			"message": "SSH execution paused pending approval.",
		}

	enqueue_execution(
		call.name,
		command=command,
		policy_snapshot=policy_snapshot,
		acting_user=acting_user,
		connection_name=connection_doc.name,
		agent_name=agent.name,
	)
	call.status = "Queued"
	call.save(ignore_permissions=True)
	return {
		"success": True,
		"status": "Queued",
		"agent_tool_call": call.name,
		"command_ref": command_ref,
		"execution_kind": "exec",
	}


def enqueue_execution(
	agent_tool_call_name: str,
	*,
	command: str,
	policy_snapshot: dict,
	acting_user: str | None = None,
	connection_name: str,
	agent_name: str | None = None,
) -> None:
	limits = (policy_snapshot or {}).get("limits") or {}
	timeout = int(limits.get("execution_timeout_seconds") or DEFAULT_EXECUTION_TIMEOUT_S) + 15
	frappe.enqueue(
		"huf.ai.tools.ssh_execution.execute_job",
		queue="code-execution",
		timeout=timeout,
		agent_tool_call_name=agent_tool_call_name,
		command=command,
		policy_snapshot=policy_snapshot,
		acting_user=acting_user,
		connection_name=connection_name,
		agent_name=agent_name,
		now=bool(getattr(frappe.flags, "in_test", False)),
	)


def _connection_counter_key(connection_name: str) -> str:
	return f"huf:ssh:active:{connection_name}"


def _acquire_connection_slot(connection_name: str, max_concurrent: int) -> None:
	cache = frappe.cache()
	key = _connection_counter_key(connection_name)
	current = int(cache.get_value(key) or 0)
	if current >= max_concurrent:
		frappe.throw(
			f"SSH connection '{connection_name}' is already running the maximum allowed concurrent commands.",
			frappe.ValidationError,
		)
	cache.set_value(key, current + 1, expires_in_sec=max(DEFAULT_EXECUTION_TIMEOUT_S * 2, 600))


def _release_connection_slot(connection_name: str) -> None:
	cache = frappe.cache()
	key = _connection_counter_key(connection_name)
	current = int(cache.get_value(key) or 0)
	if current <= 1:
		cache.delete_key(key)
		return
	cache.set_value(key, current - 1, expires_in_sec=max(DEFAULT_EXECUTION_TIMEOUT_S * 2, 600))


def _connect_transport(connection_doc, limits: dict):
	timeout = int(limits.get("connection_timeout_seconds") or DEFAULT_CONNECTION_TIMEOUT_S)
	sock = socket.create_connection((connection_doc.host, int(connection_doc.port or 22)), timeout=timeout)
	transport = paramiko.Transport(sock)
	transport.banner_timeout = timeout
	transport.handshake_timeout = timeout
	transport.auth_timeout = timeout
	transport.start_client(timeout=timeout)
	server_key = transport.get_remote_server_key()
	fingerprint = _fingerprint_for_key(server_key)
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
		pkey = _load_private_key(
			connection_doc.get_password("private_key"),
			connection_doc.get_password("private_key_passphrase", raise_exception=False),
		)
		transport.auth_publickey(username=connection_doc.username, key=pkey)

	if not transport.is_authenticated():
		transport.close()
		frappe.throw("SSH authentication failed.", frappe.PermissionError)
	return transport, fingerprint, server_key.get_name()


def _run_exec_over_transport(transport, command: str, limits: dict, fingerprint: str, host_key_type: str) -> SSHExecutionResult:
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
	return SSHExecutionResult(
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


def execute_job(
	agent_tool_call_name: str,
	command: str,
	policy_snapshot: dict,
	acting_user: str | None = None,
	connection_name: str | None = None,
	agent_name: str | None = None,
) -> None:
	call = frappe.get_doc("Agent Tool Call", agent_tool_call_name)
	call.status = "Started"
	call.save(ignore_permissions=True)

	connection_label = connection_name or call.ssh_connection
	limits = (policy_snapshot or {}).get("limits") or {}
	max_concurrent = int(limits.get("max_concurrent_commands_per_connection") or DEFAULT_MAX_CONCURRENT_COMMANDS)
	transport = None
	acquired = False

	try:
		if not acting_user:
			raise frappe.ValidationError("SSH execution is missing the original acting user.")
		if not agent_name:
			raise frappe.ValidationError("SSH execution is missing the original agent reference.")
		connection_doc = frappe.get_doc("SSH Connection", connection_label)
		_validate_agent_connection_for_user(agent_name, connection_doc.name, acting_user)
		_acquire_connection_slot(connection_doc.name, max_concurrent)
		acquired = True
		transport, fingerprint, host_key_type = _connect_transport(connection_doc, limits)
		result = _run_exec_over_transport(transport, command, limits, fingerprint, host_key_type)
		_apply_result(call, result, limits)
	except Exception as exc:  # noqa: BLE001
		call.status = "Failed"
		call.exit_status = "Error"
		call.limits_hit = 0
		call.error_message = _truncate(f"{type(exc).__name__}: {exc}", 60000)
		call.resource_usage = {
			"wall_s": 0,
			"execution_kind": "exec",
			"connection_name": connection_label,
		}
		call.save(ignore_permissions=True)
		frappe.log_error(f"execute_job failed for {agent_tool_call_name}: {exc}", "Huf SSH Execution")
	finally:
		if transport is not None:
			try:
				transport.close()
			except Exception:
				pass
		if acquired:
			_release_connection_slot(connection_doc.name)


def _apply_result(call, result: SSHExecutionResult, limits: dict | None = None) -> None:
	ok = result.exit_status == "Ok" and (result.exit_code in (None, 0))
	limits = limits or {}
	stdout_limit = int(limits.get("stdout_max_bytes") or DEFAULT_STDOUT_MAX_BYTES)
	stderr_limit = int(limits.get("stderr_max_bytes") or DEFAULT_STDERR_MAX_BYTES)

	call.status = "Completed" if ok else "Failed"
	call.exit_status = result.exit_status
	call.limits_hit = 1 if result.limits_hit else 0
	call.tool_result = {
		"stdout": _truncate(result.stdout, stdout_limit) or "",
		"stderr": _truncate(result.stderr, stderr_limit) or "",
		"exit_code": result.exit_code,
	}
	call.error_message = None if ok else _truncate(result.stderr or f"Remote command failed with exit code {result.exit_code}.", 60000)
	call.resource_usage = {
		"wall_s": round(result.wall_s, 4),
		"output_bytes": int(result.output_bytes),
		"exit_code": result.exit_code,
		"execution_kind": "exec",
		"host_key_fingerprint": result.host_key_fingerprint,
		"host_key_type": result.host_key_type,
		"idle_timed_out": bool(result.idle_timed_out),
		"timed_out": bool(result.timed_out),
	}
	call.save(ignore_permissions=True)
