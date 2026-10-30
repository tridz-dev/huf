"""``Agent Tool Call`` telemetry records for the deterministic tool path (see ``huf.ai.tools.invocation``)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

import frappe

if TYPE_CHECKING:
	from huf.ai.tools.invocation import RunContext, ToolResult

logger = frappe.logger("huf")


def start_tool_call_telemetry(tool_name: str, args: dict, ctx: RunContext):
	"""Insert an ``Agent Tool Call`` record with status Started, before
	invocation. Ported from ``flow_engine._exec_tool_call``
	(flow/engine.py:599-630 on the base checkout) -- the seam this task
	moves per GT-05/I5, generalized so any caller gets it for free by
	passing ``telemetry=True`` instead of assembling this block itself.
	"""
	is_mcp_tool = 0
	mcp_server = None
	from huf.ai.mcp_client import find_unique_mcp_server_for_tool

	mcp_tool_entry = find_unique_mcp_server_for_tool(tool_name)
	if mcp_tool_entry:
		is_mcp_tool = 1
		mcp_server = mcp_tool_entry

	call_id = ctx.call_id or f"call_{uuid4().hex[:12]}"
	ctx.call_id = call_id

	doc = frappe.get_doc({
		"doctype": "Agent Tool Call",
		"agent_run": ctx.agent_run_id,
		"conversation": ctx.conversation_id,
		"tool": tool_name,
		"is_mcp_tool": is_mcp_tool,
		"mcp_server": mcp_server,
		"tool_args": json.dumps(args, default=str) if args else None,
		"status": "Started",
		"call_id": call_id,
	})
	doc.insert(ignore_permissions=True)
	return doc


def finalize_tool_call_telemetry(doc, tool_result: ToolResult) -> None:
	"""Finalize the Agent Tool Call record as Completed/Failed, after
	invocation. Never raises -- a telemetry write failure must not turn a
	successful tool call into a failed one.
	"""
	result_val = tool_result.result
	if isinstance(result_val, (dict, list)):
		formatted_result = result_val
	else:
		formatted_result = {"output": str(result_val)} if result_val is not None else None

	try:
		doc.update({
			"status": "Completed" if tool_result.success else "Failed",
			"tool_result": formatted_result,
			"error_message": (tool_result.error or None),
		})
		doc.save(ignore_permissions=True)
	except Exception as e:
		logger.debug(f"tool_invocation: failed to finalize Agent Tool Call telemetry: {e!s}")
