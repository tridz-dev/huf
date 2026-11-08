"""Capability catalogue for the external (MCP-facing) surface.

Pure module: no Frappe imports, so it can be loaded under plain pytest.

Each capability is exposed to MCP clients under an MCP-safe name (underscores
only). The names map one-to-one onto the conceptual group names used in the
design docs: huf_discover -> huf.discover, huf_context -> huf.context,
huf_invoke -> huf.invoke, huf_surface -> huf.surface, huf_wait -> huf.wait,
huf_report -> huf.report, huf_complete -> huf.complete.

``CAPABILITIES`` is the base catalogue every connection gets. ``HUB_CAPABILITIES``
is an opt-in tier: ``list_for_mcp(tier)`` adds hub capabilities for ``"Build"``
(read and build) and ``"Admin"`` (everything), and nothing extra for ``"Off"``.
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


HUB_TIERS: tuple[str, ...] = ("Off", "Build", "Admin")

_TIER_RANK: dict[str, int] = {tier: rank for rank, tier in enumerate(HUB_TIERS)}

_WRITE_APPROVAL = "Writes ask for the user's approval first."

_HUB_TIER_REQUIRED: dict[str, str] = {
	"huf_find_agents": "Build",
	"huf_find_tools": "Build",
	"huf_find_tables": "Build",
	"huf_create_agent": "Build",
	"huf_create_tool": "Build",
	"huf_create_table": "Build",
	"huf_build_app": "Admin",
}

_QUERY_SCHEMA: dict[str, Any] = {
	"type": "string",
	"description": "Text to match against names and descriptions.",
}

_LIMIT_SCHEMA: dict[str, Any] = {
	"type": "integer",
	"minimum": 1,
	"maximum": 50,
	"default": 10,
	"description": "Maximum number of results to return.",
}

_SPEC_SCHEMA: dict[str, Any] = {
	"type": "object",
	"description": "Definition of the item to create.",
}

HUB_CAPABILITIES: list[dict[str, Any]] = [
	{
		"name": "huf_find_agents",
		"description": "Search the Huf agents this connection can see. Read-only.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"query": _QUERY_SCHEMA,
				"limit": _LIMIT_SCHEMA,
			},
		},
	},
	{
		"name": "huf_find_tools",
		"description": "Search the Huf tools this connection can see. Read-only.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"query": _QUERY_SCHEMA,
				"limit": _LIMIT_SCHEMA,
			},
		},
	},
	{
		"name": "huf_find_tables",
		"description": "Search the Huf tables this connection can see. Read-only.",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"query": _QUERY_SCHEMA,
				"limit": _LIMIT_SCHEMA,
			},
		},
	},
	{
		"name": "huf_create_agent",
		"description": f"Create a Huf agent from a name and instructions. {_WRITE_APPROVAL}",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"name": {
					"type": "string",
					"description": "Name of the agent.",
				},
				"instructions": {
					"type": "string",
					"description": "System instructions that define the agent's behaviour.",
				},
				"tool_names": {
					"type": "array",
					"items": {"type": "string"},
					"description": "Names of existing tools the agent may use.",
				},
				"description": {
					"type": "string",
					"description": "Short summary of what the agent does.",
				},
			},
			"required": ["name", "instructions"],
		},
	},
	{
		"name": "huf_create_tool",
		"description": f"Create a Huf tool from a spec. {_WRITE_APPROVAL}",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {"spec": _SPEC_SCHEMA},
			"required": ["spec"],
		},
	},
	{
		"name": "huf_create_table",
		"description": f"Create a Huf table from a spec. {_WRITE_APPROVAL}",
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {"spec": _SPEC_SCHEMA},
			"required": ["spec"],
		},
	},
	{
		"name": "huf_build_app",
		"description": (
			"Draft, update or install a Huf app from a spec. Drafting is read-only; "
			f"updating or installing is a write. {_WRITE_APPROVAL}"
		),
		"inputSchema": {
			**_OBJECT_SCHEMA_FLAGS,
			"properties": {
				"action": {
					"type": "string",
					"enum": ["draft", "update", "install"],
					"description": "Whether to draft, update or install the app.",
				},
				"app_id": {
					"type": "string",
					"description": "Identifier of the app to update or install.",
				},
				"spec": _SPEC_SCHEMA,
			},
			"required": ["action"],
		},
	},
]


def capability_names() -> list[str]:
	"""Return the MCP names of the base capabilities, in declaration order."""
	return [cap["name"] for cap in CAPABILITIES]


def hub_capability_names() -> list[str]:
	"""Return the MCP names of the hub capabilities, in declaration order."""
	return [cap["name"] for cap in HUB_CAPABILITIES]


def is_hub_capability(name: str) -> bool:
	"""Return True if ``name`` is a hub capability."""
	return name in _HUB_TIER_REQUIRED


def hub_tier_required(name: str) -> str | None:
	"""Return the tier ("Build" or "Admin") that unlocks a hub capability, else None."""
	return _HUB_TIER_REQUIRED.get(name)


def get_capability(name: str) -> dict[str, Any] | None:
	"""Return a deep copy of the named base or hub capability, or None if unknown."""
	for cap in (*CAPABILITIES, *HUB_CAPABILITIES):
		if cap["name"] == name:
			return copy.deepcopy(cap)
	return None


def list_for_mcp(tier: str = "Off") -> list[dict[str, Any]]:
	"""Return deep copies of the capabilities visible at ``tier`` for an MCP tools/list response.

	"Off" returns only the base capabilities, "Build" adds the read and build hub
	capabilities, and "Admin" adds every hub capability.
	"""
	if tier not in _TIER_RANK:
		raise ValueError(f"Unknown hub tier: {tier!r}")
	rank = _TIER_RANK[tier]
	visible = [
		cap for cap in HUB_CAPABILITIES if _TIER_RANK[_HUB_TIER_REQUIRED[cap["name"]]] <= rank
	]
	return copy.deepcopy([*CAPABILITIES, *visible])
