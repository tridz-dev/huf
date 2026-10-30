"""The tools a Flow step can call: built-in tool records and the tools of enabled MCP servers."""

from __future__ import annotations

import json

import frappe
from frappe import _

from huf.ai.flow.testrun.effects import tool_effect


@frappe.whitelist()
def list_flow_tools() -> list:
	"""
	List all tools available to flow tool-call nodes: built-in Agent Tool
	Function records plus tools exposed by enabled MCP Server documents.

	Each dict:
	    {
	        "name": str,
	        "label": str,
	        "description": str,
	        "source": "builtin" | "mcp",
	        "effect": "reads" | "changes" | "sends",   # what a test run does with it
	        "mcp_server": str | None,
	        "params_json_schema": dict,
	    }

	Returns:
	    list[dict]
	"""
	if not frappe.has_permission("Agent Tool Function", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	tools = []

	# Built-in tools: Agent Tool Function.params is the authoritative JSON
	# Schema source (see huf/ai/sdk_tools.py:create_agent_tools, which is the
	# only code path that actually builds runtime tools from this doctype).
	# The "parameters" child table (Agent Function Params) is not read by
	# any conversion code in the app and is treated as stale/unused here.
	for row in frappe.get_all(
		"Agent Tool Function",
		fields=["name", "tool_name", "description", "params", "types"],
		# Flow/Procedure runs have no Agent Execution Profile, so a Code Execution tool is
		# refused on every call (PermissionAwareToolRegistry._allows_code_execution); don't offer it.
		filters={"types": ["!=", "Code Execution"]},
	):
		params_json_schema = {}
		if row.params:
			try:
				params_json_schema = json.loads(row.params)
			except (json.JSONDecodeError, TypeError):
				params_json_schema = {}

		tools.append({
			"name": row.tool_name,
			"label": row.tool_name,
			"description": row.description or "",
			"source": "builtin",
			"effect": tool_effect(row.tool_name, None, row.types),
			"mcp_server": None,
			"params_json_schema": params_json_schema if isinstance(params_json_schema, dict) else {},
		})

	# MCP tools: each enabled "MCP Server" document caches its tools in the
	# "tools" child table (MCP Server Tool: tool_name, description,
	# parameters JSON, enabled). "mcp_server" below is the MCP Server
	# document name (server_name, since autoname is field:server_name),
	# matching the identifier huf.ai.mcp_client.execute_mcp_tool expects
	# for its server_name argument.
	mcp_servers = frappe.get_all(
		"MCP Server",
		filters={"enabled": 1},
		fields=["name", "tool_namespace"],
	)
	for server in mcp_servers:
		tool_rows = frappe.get_all(
			"MCP Server Tool",
			filters={"parent": server.name, "parenttype": "MCP Server", "enabled": 1},
			fields=["tool_name", "description", "parameters"],
		)
		for tool_row in tool_rows:
			params_json_schema = {}
			if tool_row.parameters:
				try:
					params_json_schema = json.loads(tool_row.parameters)
				except (json.JSONDecodeError, TypeError):
					params_json_schema = {}

			label = tool_row.tool_name
			if server.tool_namespace:
				label = f"{server.tool_namespace}.{tool_row.tool_name}"

			tools.append({
				"name": tool_row.tool_name,
				"label": label,
				"description": tool_row.description or "",
				"source": "mcp",
				"effect": "changes",
				"mcp_server": server.name,
				"params_json_schema": params_json_schema if isinstance(params_json_schema, dict) else {},
			})

	return tools
