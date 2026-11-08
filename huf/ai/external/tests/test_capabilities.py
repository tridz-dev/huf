# ruff: noqa: S101
from __future__ import annotations

import re

import pytest

from huf.ai.external.capabilities import (
	CAPABILITIES,
	HUB_CAPABILITIES,
	HUB_TIERS,
	capability_names,
	get_capability,
	hub_capability_names,
	hub_tier_required,
	is_hub_capability,
	list_for_mcp,
)

NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

BASE_NAMES = [
	"huf_discover",
	"huf_context",
	"huf_invoke",
	"huf_surface",
	"huf_wait",
	"huf_report",
	"huf_complete",
]

BUILD_HUB_NAMES = [
	"huf_find_agents",
	"huf_find_tools",
	"huf_find_tables",
	"huf_create_agent",
	"huf_create_tool",
	"huf_create_table",
]

ADMIN_HUB_NAMES = ["huf_build_app"]


def _all_catalogue():
	return [*CAPABILITIES, *HUB_CAPABILITIES]


def test_seven_unique_mcp_safe_base_names():
	names = capability_names()
	assert len(names) == 7
	assert len(set(names)) == 7
	assert names == BASE_NAMES
	for name in names:
		assert NAME_PATTERN.match(name), name


def test_hub_names_unique_mcp_safe_and_disjoint_from_base():
	names = hub_capability_names()
	assert names == BUILD_HUB_NAMES + ADMIN_HUB_NAMES
	assert len(set(names)) == len(names)
	assert not set(names) & set(capability_names())
	for name in names:
		assert NAME_PATTERN.match(name), name


def test_every_schema_is_closed_object_with_required_keys_declared():
	for cap in _all_catalogue():
		assert set(cap) >= {"name", "description", "inputSchema"}
		assert isinstance(cap["description"], str) and cap["description"], cap["name"]
		schema = cap["inputSchema"]
		assert schema["type"] == "object", cap["name"]
		assert schema["additionalProperties"] is False, cap["name"]
		properties = schema["properties"]
		assert isinstance(properties, dict), cap["name"]
		for key in schema.get("required", []):
			assert key in properties, f"{cap['name']}: required '{key}' not in properties"


def test_hub_required_keys():
	required = {cap["name"]: cap["inputSchema"].get("required", []) for cap in HUB_CAPABILITIES}
	assert required["huf_create_agent"] == ["name", "instructions"]
	assert required["huf_create_tool"] == ["spec"]
	assert required["huf_create_table"] == ["spec"]
	assert required["huf_build_app"] == ["action"]
	assert required["huf_find_agents"] == []


def test_hub_limit_bounds_and_default():
	for name in ("huf_find_agents", "huf_find_tools", "huf_find_tables"):
		schema = get_capability(name)["inputSchema"]
		limit = schema["properties"]["limit"]
		assert limit["type"] == "integer"
		assert limit["minimum"] == 1
		assert limit["maximum"] == 50
	agents_limit = get_capability("huf_find_agents")["inputSchema"]["properties"]["limit"]
	assert agents_limit["default"] == 10


def test_hub_create_agent_tool_names_is_string_array():
	props = get_capability("huf_create_agent")["inputSchema"]["properties"]
	assert props["tool_names"] == {
		"type": "array",
		"items": {"type": "string"},
		"description": props["tool_names"]["description"],
	}


def test_hub_build_app_action_enum():
	props = get_capability("huf_build_app")["inputSchema"]["properties"]
	assert props["action"]["enum"] == ["create", "update", "install"]


def test_hub_write_capabilities_ask_for_approval():
	write_names = [
		"huf_create_agent",
		"huf_create_tool",
		"huf_create_table",
		"huf_build_app",
	]
	for name in write_names:
		assert "approval" in get_capability(name)["description"].lower(), name


def test_get_capability_returns_copy_and_none_for_unknown():
	assert get_capability("no_such_capability") is None
	cap = get_capability("huf_invoke")
	assert cap is not None
	assert cap["name"] == "huf_invoke"
	cap["inputSchema"]["properties"].clear()
	assert "tool_name" in get_capability("huf_invoke")["inputSchema"]["properties"]


def test_get_capability_resolves_hub_names_as_copies():
	cap = get_capability("huf_create_tool")
	assert cap is not None
	assert cap["name"] == "huf_create_tool"
	cap["inputSchema"]["properties"].clear()
	assert "spec" in get_capability("huf_create_tool")["inputSchema"]["properties"]


def test_list_for_mcp_off_returns_exactly_base_capabilities():
	listed = list_for_mcp("Off")
	assert [c["name"] for c in listed] == BASE_NAMES
	assert [c["name"] for c in list_for_mcp()] == BASE_NAMES


def test_list_for_mcp_build_adds_six_hub_capabilities():
	listed = [c["name"] for c in list_for_mcp("Build")]
	assert listed == BASE_NAMES + BUILD_HUB_NAMES
	assert len(listed) == 13


def test_list_for_mcp_admin_adds_all_hub_capabilities():
	listed = [c["name"] for c in list_for_mcp("Admin")]
	assert listed == BASE_NAMES + BUILD_HUB_NAMES + ADMIN_HUB_NAMES
	assert len(listed) == 14
	assert len(set(listed)) == len(listed)


def test_list_for_mcp_rejects_unknown_tier():
	with pytest.raises(ValueError):
		list_for_mcp("Root")


def test_hub_tiers_order():
	assert HUB_TIERS == ("Off", "Build", "Admin")


def test_is_hub_capability():
	for name in BUILD_HUB_NAMES + ADMIN_HUB_NAMES:
		assert is_hub_capability(name), name
	for name in BASE_NAMES:
		assert not is_hub_capability(name), name
	assert not is_hub_capability("no_such_capability")


def test_hub_tier_required():
	for name in BUILD_HUB_NAMES:
		assert hub_tier_required(name) == "Build", name
	for name in ADMIN_HUB_NAMES:
		assert hub_tier_required(name) == "Admin", name
	assert hub_tier_required("huf_invoke") is None
	assert hub_tier_required("no_such_capability") is None


def test_list_for_mcp_returns_independent_copies():
	first = list_for_mcp()
	assert [c["name"] for c in first] == capability_names()
	first[0]["description"] = "mutated"
	first[0]["inputSchema"]["properties"]["injected"] = {"type": "string"}
	second = list_for_mcp()
	assert second[0]["description"] != "mutated"
	assert "injected" not in second[0]["inputSchema"]["properties"]
	assert "injected" not in CAPABILITIES[0]["inputSchema"]["properties"]


def test_list_for_mcp_admin_returns_independent_hub_copies():
	first = list_for_mcp("Admin")
	hub_entry = first[-1]
	assert hub_entry["name"] == "huf_build_app"
	hub_entry["inputSchema"]["properties"]["injected"] = {"type": "string"}
	hub_entry["description"] = "mutated"
	second = list_for_mcp("Admin")
	assert "injected" not in second[-1]["inputSchema"]["properties"]
	assert second[-1]["description"] != "mutated"
	assert "injected" not in HUB_CAPABILITIES[-1]["inputSchema"]["properties"]
