"""Frappe-facing tool handler for ACP remote agents.

This module bridges Huf's ``Agent Tool Function`` system to the ACP client
adapter.  A tool whose ``types`` is ``Remote ACP Agent`` resolves to the
whitelisted ``run_acp_agent_tool`` function, which delegates to the remote-agent
dispatch layer.
"""

from __future__ import annotations

import logging
from typing import Any

import frappe

from huf.ai.remote_agents.tool_handler import execute_remote_tool, test_remote_connection

LOGGER = logging.getLogger("huf.ai.acp.tool_handler")


@frappe.whitelist()
def run_acp_agent_tool(
    prompt: str,
    connection_name: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Invoke a remote ACP agent as a tool call.

    Args:
        prompt: The prompt text to send to the remote agent.
        connection_name: The ``Remote Agent Connection`` record name to use.
        kwargs: Reserved for future adapter overrides; forwarded to the
            remote-agent dispatch layer.

    Returns:
        A normalized result dict with ``status`` and ``response`` keys.
    """
    if not prompt:
        frappe.throw(frappe._("Prompt is required for Remote ACP Agent tools."))
    if not connection_name:
        frappe.throw(frappe._("Connection Name is required for Remote ACP Agent tools."))

    result = execute_remote_tool(
        connection_name=connection_name,
        agent_id=kwargs.pop("agent_id", None),
        payload={"prompt": prompt, **kwargs},
        user=frappe.session.user,
    )

    if isinstance(result, dict):
        return result

    return {"status": "success", "response": str(result)}


@frappe.whitelist()
def test_acp_connection(connection_name: str) -> dict[str, Any]:
    """Run the ACP initialize handshake against ``connection_name``.

    Returns a dict with ``ok``, ``protocol_version``, ``agent_name`` and ``error``.
    """
    if not connection_name:
        frappe.throw(frappe._("Connection Name is required to test an ACP connection."))

    try:
        return test_remote_connection(connection_name)
    except Exception as exc:
        LOGGER.exception("ACP connection test failed: %s", connection_name)
        return {"ok": False, "error": str(exc)}
