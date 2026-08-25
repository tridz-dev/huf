"""Whitelisted REST API surface for remote-agent operations.

The standalone ``huf acp`` server calls these endpoints to resolve policy and
other Huf-side state without loading Frappe in-process.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import frappe

from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.fan_out import fan_out_run_async
from huf.ai.remote_agents.policy import resolve_policy

LOGGER = logging.getLogger("huf.ai.remote_agents.api")


@frappe.whitelist()
def resolve_agent_policy(
	caller_type: str,
	caller_reference: str | None = None,
	requested_agent: str | None = None,
) -> dict[str, Any]:
	"""Resolve which agent a caller is allowed to reach.

	This endpoint is consumed by the standalone ``huf acp`` server during
	``session/new``. The request is authenticated via Frappe's standard token
	auth, so ``frappe.session.user`` is available for ``caller_type == "user"``.
	"""
	try:
		return resolve_policy(caller_type, caller_reference, requested_agent)
	except RemoteAgentPolicyError as exc:
		frappe.throw(str(exc), frappe.PermissionError)


@frappe.whitelist()
def fan_out_run(
	agent_id: str | None = None,
	payload: str | dict[str, Any] | None = None,
	connections: str | list[str] | None = None,
	group: str | None = None,
	mode: str = "parallel",
	min_success_count: int | None = None,
	per_child_timeout: int | float = 60,
	overall_timeout: int | float = 180,
	require_all: bool = False,
) -> dict[str, Any]:
	"""Run the same prompt across a group of remote ACP agents.

	Either ``connections`` or ``group`` must be supplied.  Results are returned
	synchronously; callers that need to survive long-running orchestration
	should enqueue this method via ``frappe.enqueue``.
	"""
	if isinstance(payload, str):
		try:
			payload = frappe.parse_json(payload) or {}
		except Exception as exc:  # noqa: BLE001
			LOGGER.debug("Failed to parse payload JSON: %s", exc)
			payload = {}
	if not isinstance(payload, dict):
		payload = {}

	if isinstance(connections, str):
		try:
			connections = frappe.parse_json(connections) or []
		except Exception as exc:  # noqa: BLE001
			LOGGER.debug("Failed to parse connections JSON: %s", exc)
			connections = []
	if connections is not None and not isinstance(connections, list):
		connections = [connections]

	try:
		return asyncio.run(
			fan_out_run_async(
				agent_id=agent_id,
				payload=payload,
				connections=connections,
				group=group,
				mode=mode,
				min_success_count=min_success_count,
				per_child_timeout=float(per_child_timeout),
				overall_timeout=float(overall_timeout),
				require_all=bool(require_all),
			)
		)
	except RemoteAgentPolicyError as exc:
		frappe.throw(str(exc), frappe.PermissionError)
