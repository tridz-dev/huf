"""Fan-out orchestration for 1:many remote-agent calls.

``fan_out_run_async`` dispatches the same prompt to a list of ``Remote Agent
Connection`` records (or to the members of an ``ACP Agent Group``), runs them in
parallel or sequentially, and aggregates the results.  Each child call respects
the per-connection ACP pool limit, the configured recursion guard, and a
per-child timeout; the whole fan-out is bounded by an overall deadline.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import frappe

from huf.ai.acp.exceptions import AcpCapacityError, AcpTimeoutError
from huf.ai.acp.pool import DEFAULT_SLOT_TIMEOUT_SECONDS, acquire_connection_slot
from huf.ai.remote_agents.adapter import AcpStdioAdapter
from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.policy import resolve_policy
from huf.ai.remote_agents.tool_handler import (
	CONNECTION_DOCTYPE,
	DEFAULT_AUTH_ENV_KEY,
	_build_launch_kwargs,
	_connection_timeout,
)

LOGGER = logging.getLogger("huf.ai.remote_agents.fan_out")

GROUP_DOCTYPE = "ACP Agent Group"
GROUP_MEMBER_CHILD_DOCTYPE = "ACP Agent Group Member"

DEFAULT_PER_CHILD_TIMEOUT = 60.0
DEFAULT_OVERALL_TIMEOUT = 180.0
DEFAULT_MODE = "parallel"


async def fan_out_run_async(
	agent_id: str | None,
	payload: dict[str, Any],
	connections: list[str] | None = None,
	group: str | None = None,
	*,
	mode: str = DEFAULT_MODE,
	min_success_count: int | None = None,
	per_child_timeout: float = DEFAULT_PER_CHILD_TIMEOUT,
	overall_timeout: float = DEFAULT_OVERALL_TIMEOUT,
	require_all: bool = False,
	user: str | None = None,
) -> dict[str, Any]:
	"""Run ``payload`` across multiple remote-agent connections and aggregate.

	Parameters
	----------
	agent_id:
		Default target agent to pass to each connection.  Per-member overrides
		from an ``ACP Agent Group`` take precedence.
	payload:
		The prompt/request payload.  A ``_meta.huf_call_chain`` value is
		forwarded to every child so the recursion guard works across fan-out.
	connections:
		List of ``Remote Agent Connection`` names.  Either this or ``group``
		must be supplied, not both.
	group:
		Name of an ``ACP Agent Group`` record to expand into connections.
	mode:
		``"parallel"`` (default) or ``"sequential"``.
	min_success_count:
		If set, the top-level status becomes ``"insufficient_success"`` when
		fewer than this many children succeed.
	per_child_timeout:
		Maximum wall-clock seconds for one child call.
	overall_timeout:
		Maximum wall-clock seconds for the whole fan-out.
	require_all:
		If ``True``, the top-level status becomes ``"partial"`` when any child
		fails or times out.
	user:
		Optional user override for policy resolution.

	Returns
	-------
	A dict with ``status``, ``mode``, ``results``, ``succeeded``, ``failed``,
	``timed_out``, and ``total``.
	"""
	targets = _resolve_targets(agent_id, connections, group)
	if not targets:
		raise RemoteAgentPolicyError("No connections or group members to fan out to.")

	if mode not in ("parallel", "sequential"):
		raise RemoteAgentPolicyError(f"Invalid fan-out mode: {mode!r}")

	child_payload = _child_payload(payload)

	if mode == "parallel":
		raw_results = await _run_parallel(
			targets,
			child_payload,
			per_child_timeout=per_child_timeout,
			overall_timeout=overall_timeout,
			user=user,
		)
	else:
		raw_results = await _run_sequential(
			targets,
			child_payload,
			per_child_timeout=per_child_timeout,
			overall_timeout=overall_timeout,
			user=user,
		)

	results = [
		_normalize_result(r, connection)
		for connection, r in zip(targets, raw_results, strict=False)
	]

	succeeded = sum(1 for r in results if r.get("status") == "success")
	failed = sum(1 for r in results if r.get("status") == "error")
	timed_out = sum(1 for r in results if r.get("status") == "timeout")

	status = "complete"
	if require_all and (failed + timed_out) > 0:
		status = "partial"
	if min_success_count is not None and succeeded < min_success_count:
		status = "insufficient_success"

	return {
		"status": status,
		"mode": mode,
		"results": results,
		"succeeded": succeeded,
		"failed": failed,
		"timed_out": timed_out,
		"total": len(results),
	}


def _resolve_targets(
	agent_id: str | None,
	connections: list[str] | None,
	group: str | None,
) -> list[tuple[str, str | None]]:
	"""Return a list of ``(connection_name, target_agent)`` tuples."""
	if connections and group:
		raise RemoteAgentPolicyError("Provide either a connection list or a group, not both.")

	if connections:
		return [(name, agent_id) for name in connections]

	if group:
		doc = frappe.get_doc(GROUP_DOCTYPE, group)
		if not getattr(doc, "enabled", 1):
			raise RemoteAgentPolicyError(f"ACP Agent Group {group!r} is disabled.")

		targets = []
		for row in getattr(doc, "members", []) or []:
			connection_name = getattr(row, "connection", None)
			if not connection_name:
				continue
			targets.append((connection_name, getattr(row, "target_agent", None) or agent_id))
		return targets

	raise RemoteAgentPolicyError("Either connections or group must be supplied.")


def _child_payload(payload: dict[str, Any]) -> dict[str, Any]:
	"""Return a payload copy that carries the incoming call chain, if any."""
	child = dict(payload)
	meta = dict(payload.get("_meta") or {})
	chain = meta.get("huf_call_chain")
	if isinstance(chain, str):
		meta["huf_call_chain"] = chain
	elif isinstance(chain, list):
		meta["huf_call_chain"] = ",".join(str(h) for h in chain)
	else:
		meta["huf_call_chain"] = ""
	child["_meta"] = meta
	return child


async def _run_parallel(
	targets: list[tuple[str, str | None]],
	payload: dict[str, Any],
	*,
	per_child_timeout: float,
	overall_timeout: float,
	user: str | None,
) -> list[dict[str, Any] | Exception]:
	"""Run all children concurrently with an overall deadline."""
	tasks = [
		asyncio.create_task(
			_run_one_child(connection_name, target_agent, payload, per_child_timeout, user),
			name=f"fan-out-{connection_name}",
		)
		for connection_name, target_agent in targets
	]

	try:
		raw = await asyncio.wait_for(
			asyncio.gather(*tasks, return_exceptions=True),
			timeout=overall_timeout,
		)
	except asyncio.TimeoutError:
		for task in tasks:
			if not task.done():
				task.cancel()
		await asyncio.gather(*tasks, return_exceptions=True)
		raw = []
		for task in tasks:
			if task.done() and not task.cancelled():
				raw.append(task.result())
			else:
				raw.append(
					{
						"status": "timeout",
						"error": "overall_timeout",
						"message": "Fan-out overall timeout expired before this child finished.",
					}
				)

	return raw


async def _run_sequential(
	targets: list[tuple[str, str | None]],
	payload: dict[str, Any],
	*,
	per_child_timeout: float,
	overall_timeout: float,
	user: str | None,
) -> list[dict[str, Any] | Exception]:
	"""Run children one at a time, respecting the overall deadline."""
	deadline = asyncio.get_event_loop().time() + overall_timeout
	results: list[dict[str, Any] | Exception] = []

	for connection_name, target_agent in targets:
		remaining = deadline - asyncio.get_event_loop().time()
		if remaining <= 0:
			results.append(
				{
					"status": "timeout",
					"error": "overall_timeout",
					"message": "Fan-out overall timeout expired before this child started.",
				}
			)
			continue

		try:
			result = await asyncio.wait_for(
				_run_one_child(connection_name, target_agent, payload, per_child_timeout, user),
				timeout=remaining,
			)
		except asyncio.TimeoutError:
			result = {
				"status": "timeout",
				"error": "overall_timeout",
				"message": "Fan-out overall timeout expired while waiting for this child.",
			}
		results.append(result)

	return results


async def _run_one_child(
	connection_name: str,
	agent_id: str | None,
	payload: dict[str, Any],
	per_child_timeout: float,
	user: str | None,
) -> dict[str, Any]:
	"""Resolve policy, acquire a pool slot, and run one ACP adapter call."""
	try:
		connection = frappe.get_doc(CONNECTION_DOCTYPE, connection_name)
		if getattr(connection, "enabled", 1) != 1:
			return {
				"connection": connection_name,
				"status": "error",
				"error": "disabled",
				"message": f"Remote Agent Connection {connection_name!r} is disabled.",
			}

		if getattr(connection, "protocol_type", None) != "acp_stdio":
			return {
				"connection": connection_name,
				"status": "error",
				"error": "unsupported_protocol",
				"message": (
					f"Remote Agent Connection {connection_name!r} uses unsupported protocol "
					f"{getattr(connection, 'protocol_type', None)!r}."
				),
			}

		policy = resolve_policy(
			"remote_connection",
			connection_name,
			requested_agent=agent_id,
			user=user,
		)
		resolved_agent = policy.get("resolved_agent") or agent_id
		if not resolved_agent:
			return {
				"connection": connection_name,
				"status": "error",
				"error": "no_agent",
				"message": "No agent could be resolved for this remote call.",
			}

		auth_secret = getattr(connection, "auth_secret", None)
		launch_kwargs = _build_launch_kwargs(connection, auth_secret)
		auth_env_key = launch_kwargs.pop("auth_env_key", None) or DEFAULT_AUTH_ENV_KEY
		timeout = min(per_child_timeout, _connection_timeout(connection))
		max_concurrent = int(getattr(connection, "max_concurrent_sessions", 3) or 3)
	except RemoteAgentPolicyError as exc:
		return {
			"connection": connection_name,
			"status": "error",
			"error": "policy",
			"message": str(exc),
		}
	except Exception as exc:
		LOGGER.exception("Failed to prepare fan-out child for %s", connection_name)
		return {
			"connection": connection_name,
			"status": "error",
			"error": type(exc).__name__,
			"message": str(exc),
		}

	slot = None
	try:
		slot = await acquire_connection_slot(
			connection_name,
			max_concurrent_sessions=max_concurrent,
			timeout=DEFAULT_SLOT_TIMEOUT_SECONDS,
		)
	except AcpCapacityError as exc:
		return {
			"connection": connection_name,
			"status": "error",
			"error": "capacity",
			"message": str(exc),
		}

	adapter = AcpStdioAdapter(
		connection_name=connection_name,
		auth_secret=auth_secret,
		auth_env_key=auth_env_key,
		timeout=timeout,
		call_chain=payload.get("_meta", {}).get("huf_call_chain", "").split(",") if payload.get("_meta", {}).get("huf_call_chain") else [],
		**launch_kwargs,
	)
	try:
		result = await asyncio.wait_for(
			adapter.create_run(resolved_agent, payload),
			timeout=timeout,
		)
	except asyncio.TimeoutError:
		return {
			"connection": connection_name,
			"status": "timeout",
			"error": "timeout",
			"message": f"Child call exceeded per-child timeout of {timeout}s.",
		}
	except AcpTimeoutError as exc:
		return {
			"connection": connection_name,
			"status": "timeout",
			"error": "acp_timeout",
			"message": str(exc),
		}
	except Exception as exc:
		LOGGER.exception("Fan-out child run failed for %s", connection_name)
		return {
			"connection": connection_name,
			"status": "error",
			"error": type(exc).__name__,
			"message": str(exc),
		}
	else:
		result.setdefault("connection", connection_name)
		return result
	finally:
		try:
			await adapter.close()
		except Exception:
			LOGGER.debug("Adapter close failed for %s", connection_name, exc_info=True)
		if slot is not None:
			slot.release()


def _normalize_result(
	result_or_exc: dict[str, Any] | Exception,
	connection_target: tuple[str, str | None],
) -> dict[str, Any]:
	"""Ensure every child result is a dict tagged with the connection name."""
	connection_name, target_agent = connection_target
	if isinstance(result_or_exc, Exception):
		LOGGER.exception("Unexpected fan-out task exception for %s", connection_name)
		return {
			"connection": connection_name,
			"target_agent": target_agent,
			"status": "error",
			"error": type(result_or_exc).__name__,
			"message": str(result_or_exc),
		}

	result = dict(result_or_exc)
	result.setdefault("connection", connection_name)
	result.setdefault("target_agent", target_agent)
	return result
