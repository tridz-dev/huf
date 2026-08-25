"""Outbound remote-agent tool-call handler.

``execute_remote_tool()`` is the entry point used by the ``Agent Tool Function``
wiring and by direct callers: it loads a ``Remote Agent Connection``, enforces
``Remote Agent Policy``, builds an adapter, and dispatches the call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import frappe

from huf.ai.acp.registry import build_launch_context
from huf.ai.remote_agents.adapter import AcpStdioAdapter
from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.policy import resolve_policy

LOGGER = logging.getLogger("huf.ai.remote_agents.tool_handler")

CONNECTION_DOCTYPE = "Remote Agent Connection"
REGISTRY_DOCTYPE = "ACP Command Registry"
DEFAULT_AUTH_ENV_KEY = "HUF_ACP_TARGET_TOKEN"


def execute_remote_tool(
	connection_name: str,
	agent_id: str | None,
	payload: dict[str, Any],
	*,
	user: str | None = None,
) -> dict[str, Any]:
	"""Run a remote agent tool call against ``connection_name``.

	This is a synchronous wrapper that drives the async adapter lifecycle.
	"""
	return asyncio.run(_execute_remote_tool_async(connection_name, agent_id, payload, user=user))


def test_remote_connection(connection_name: str) -> dict[str, Any]:
	"""Test a ``Remote Agent Connection`` by running the ACP initialize handshake.

	Returns a dict with ``ok``, ``protocol_version``, ``agent_name`` and ``error``.
	"""
	return asyncio.run(_test_remote_connection_async(connection_name))


async def _execute_remote_tool_async(
	connection_name: str,
	agent_id: str | None,
	payload: dict[str, Any],
	*,
	user: str | None = None,
) -> dict[str, Any]:
	connection = frappe.get_doc(CONNECTION_DOCTYPE, connection_name)

	if getattr(connection, "enabled", 1) != 1:
		raise RemoteAgentPolicyError(f"Remote Agent Connection {connection_name!r} is disabled.")

	protocol_type = getattr(connection, "protocol_type", None)
	if protocol_type != "acp_stdio":
		raise RemoteAgentPolicyError(
			f"Remote Agent Connection {connection_name!r} uses unsupported protocol {protocol_type!r}."
		)

	# Policy check: the connection itself is the caller identity.
	policy = resolve_policy(
		"remote_connection",
		connection_name,
		requested_agent=agent_id,
		user=user,
	)

	# Build the adapter kwargs. Prefer the ACP Command Registry entry when present;
	# fall back to legacy connection-level launch_command/launch_args if this branch
	# predates the registry DocType.
	auth_secret = getattr(connection, "auth_secret", None)
	launch_kwargs = _build_launch_kwargs(connection, auth_secret)
	# If the registry supplied an auth_env_key, prefer it; otherwise use the default.
	auth_env_key = launch_kwargs.pop("auth_env_key", None) or DEFAULT_AUTH_ENV_KEY

	_call_chain = payload.get("_meta", {}).get("huf_call_chain", [])
	if isinstance(_call_chain, str):
		_call_chain = [h for h in _call_chain.split(",") if h]

	adapter = AcpStdioAdapter(
		connection_name=connection_name,
		auth_secret=auth_secret,
		auth_env_key=auth_env_key,
		timeout=_connection_timeout(connection),
		call_chain=_call_chain,
		**launch_kwargs,
	)

	resolved_agent = policy.get("resolved_agent") or agent_id
	if not resolved_agent:
		raise RemoteAgentPolicyError("No agent could be resolved for this remote call.")

	LOGGER.debug(
		"Executing remote tool: connection=%s agent=%s policy=%s",
		connection_name,
		resolved_agent,
		policy.get("policy"),
	)
	return await adapter.create_run(resolved_agent, payload)


async def _test_remote_connection_async(connection_name: str) -> dict[str, Any]:
	connection = frappe.get_doc(CONNECTION_DOCTYPE, connection_name)

	if getattr(connection, "enabled", 1) != 1:
		return {"ok": False, "error": f"Remote Agent Connection {connection_name!r} is disabled."}

	protocol_type = getattr(connection, "protocol_type", None)
	if protocol_type != "acp_stdio":
		return {
			"ok": False,
			"error": f"Remote Agent Connection {connection_name!r} uses unsupported protocol {protocol_type!r}.",
		}

	auth_secret = getattr(connection, "auth_secret", None)
	launch_kwargs = _build_launch_kwargs(connection, auth_secret)
	auth_env_key = launch_kwargs.pop("auth_env_key", None) or DEFAULT_AUTH_ENV_KEY

	adapter = AcpStdioAdapter(
		connection_name=connection_name,
		auth_secret=auth_secret,
		auth_env_key=auth_env_key,
		timeout=_connection_timeout(connection),
		**launch_kwargs,
	)

	try:
		manifest = await adapter.fetch_manifest()
	finally:
		# Ensure the subprocess launched for the handshake is reaped.
		if adapter._client is not None:
			await adapter._client.close()

	return {
		"ok": True,
		"protocol_version": manifest.get("protocol_version"),
		"agent_name": manifest.get("server_name"),
	}


def _build_launch_kwargs(connection: Any, auth_secret: str | None) -> dict[str, Any]:
	"""Return launch_command/launch_args/working_directory/env for the adapter."""
	registry_entry = getattr(connection, "acp_registry_entry", None)
	if registry_entry:
		return _load_registry_launch_context(registry_entry, auth_secret)

	# Legacy path: connection supplies the command shape directly. This is kept
	# for compatibility with early track code and test fixtures; production rows
	# should use the ACP Command Registry per D1.
	launch_command = getattr(connection, "launch_command", None)
	if not launch_command:
		raise RemoteAgentPolicyError(
			"Remote Agent Connection has no launch_command and no ACP Command Registry entry."
		)

	launch_args = getattr(connection, "launch_args", None) or "[]"
	if isinstance(launch_args, str):
		try:
			launch_args = json.loads(launch_args)
		except json.JSONDecodeError as exc:
			raise RemoteAgentPolicyError(f"Invalid launch_args JSON: {exc}") from None

	return {
		"launch_command": launch_command,
		"launch_args": launch_args if isinstance(launch_args, list) else [],
		"working_directory": getattr(connection, "working_directory", None),
	}


def _load_registry_launch_context(registry_name: str, auth_secret: str | None) -> dict[str, Any]:
	"""Load an ACP Command Registry entry and return sanitized adapter launch kwargs."""
	context = build_launch_context(registry_name, auth_secret=auth_secret)
	cmd = context["cmd"]
	return {
		"launch_command": cmd[0],
		"launch_args": cmd[1:],
		"working_directory": context["cwd"],
		"env": context["env"],
		"auth_env_key": context["auth_env_key"],
	}


def _connection_timeout(connection: Any) -> float:
	"""Return the per-connection timeout, falling back to a sensible default."""
	value = getattr(connection, "max_wall_time_seconds", None) or 300
	try:
		return float(value)
	except (TypeError, ValueError):
		return 300.0
