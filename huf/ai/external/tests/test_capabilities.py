# ruff: noqa: S101
from __future__ import annotations

import re

from huf.ai.external.capabilities import (
	CAPABILITIES,
	capability_names,
	get_capability,
	list_for_mcp,
)

NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def test_seven_unique_mcp_safe_names():
	names = capability_names()
	assert len(names) == 7
	assert len(set(names)) == 7
	for name in names:
		assert NAME_PATTERN.match(name), name


def test_every_schema_is_closed_object_with_required_keys_declared():
	for cap in CAPABILITIES:
		assert set(cap) >= {"name", "description", "inputSchema"}
		schema = cap["inputSchema"]
		assert schema["type"] == "object", cap["name"]
		assert schema["additionalProperties"] is False, cap["name"]
		properties = schema["properties"]
		for key in schema.get("required", []):
			assert key in properties, f"{cap['name']}: required '{key}' not in properties"


def test_get_capability_returns_copy_and_none_for_unknown():
	assert get_capability("no_such_capability") is None
	cap = get_capability("huf_invoke")
	assert cap is not None
	assert cap["name"] == "huf_invoke"
	cap["inputSchema"]["properties"].clear()
	assert "tool_name" in get_capability("huf_invoke")["inputSchema"]["properties"]


def test_list_for_mcp_returns_independent_copies():
	first = list_for_mcp()
	assert [c["name"] for c in first] == capability_names()
	first[0]["description"] = "mutated"
	first[0]["inputSchema"]["properties"]["injected"] = {"type": "string"}
	second = list_for_mcp()
	assert second[0]["description"] != "mutated"
	assert "injected" not in second[0]["inputSchema"]["properties"]
	assert "injected" not in CAPABILITIES[0]["inputSchema"]["properties"]
