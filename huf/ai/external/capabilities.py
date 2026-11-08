"""Capability catalogue for the external (MCP-facing) surface.

Pure module: no Frappe imports, so it can be loaded under plain pytest.

Each capability is exposed to MCP clients under an MCP-safe name (underscores
only). The names map one-to-one onto the conceptual group names used in the
design docs: huf_discover -> huf.discover, huf_context -> huf.context,
huf_invoke -> huf.invoke, huf_surface -> huf.surface, huf_wait -> huf.wait,
huf_report -> huf.report, huf_complete -> huf.complete.
"""

from __future__ import annotations

import copy
from typing import Any

_OBJECT_SCHEMA_FLAGS: dict[str, Any] = {"type": "object", "additionalProperties": False}

CAPABILITIES: list[dict[str, Any]] = [
	{
		"name": "huf_discover",
		"description": "List the Huf tools this connection is permitted to use.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {},
		},
	},
	{
		"name": "huf_context",
		"description": "Read the context permitted for this connection.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"scope": {
					"type": "string",
					"enum": ["conversation", "agent"],
					"default": "conversation",
					"description": "Which context to read.",
				},
				"limit": {
					"type": "integer",
					"minimum": 1,
					"maximum": 50,
					"default": 20,
					"description": "Maximum number of items to return.",
				},
			},
		},
	},
	{
		"name": "huf_invoke",
		"description": "Run a Huf tool under the connection's policy.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"tool_name": {
					"type": "string",
					"description": "Name of the Huf tool to run.",
				},
				"arguments": {
					"type": "object",
					"description": "Arguments passed to the tool.",
				},
				"client_call_id": {
					"type": "string",
					"description": "Caller-chosen identifier for correlating this call.",
				},
			},
			"required": ["tool_name"],
		},
	},
	{
		"name": "huf_surface",
		"description": "Create or update an interactive surface.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"action": {
					"type": "string",
					"enum": ["create", "update"],
					"description": "Whether to create a new surface or update an existing one.",
				},
				"surface_id": {
					"type": "string",
					"description": "Identifier of the surface to update.",
				},
				"spec": {
					"type": "object",
					"description": "Surface definition.",
				},
			},
			"required": ["action", "spec"],
		},
	},
	{
		"name": "huf_wait",
		"description": "Wait for the next user interaction or task.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"timeout_seconds": {
					"type": "integer",
					"minimum": 0,
					"maximum": 10,
					"default": 5,
					"description": "How long to wait before returning.",
				},
			},
		},
	},
	{
		"name": "huf_report",
		"description": "Report progress, an observation, or an artifact back to Huf.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"message": {
					"type": "string",
					"description": "Human-readable report message.",
				},
				"kind": {
					"type": "string",
					"enum": ["progress", "observation", "artifact"],
					"default": "progress",
					"description": "Category of the report.",
				},
				"data": {
					"type": "object",
					"description": "Optional structured payload.",
				},
			},
			"required": ["message"],
		},
	},
	{
		"name": "huf_complete",
		"description": "Mark the current task as finished.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"status": {
					"type": "string",
					"enum": ["success", "failed"],
					"description": "Final outcome of the task.",
				},
				"result": {
					"type": "string",
					"description": "Summary of the result.",
				},
			},
			"required": ["status"],
		},
	},
]


def capability_names() -> list[str]:
	"""Return the MCP names of all capabilities, in declaration order."""
	return [cap["name"] for cap in CAPABILITIES]


def get_capability(name: str) -> dict[str, Any] | None:
	"""Return a deep copy of the named capability, or None if unknown."""
	for cap in CAPABILITIES:
		if cap["name"] == name:
			return copy.deepcopy(cap)
	return None


def list_for_mcp() -> list[dict[str, Any]]:
	"""Return deep copies of all capabilities for an MCP tools/list response."""
	return copy.deepcopy(CAPABILITIES)
