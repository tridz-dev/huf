# ruff: noqa: S101
from __future__ import annotations

import pytest

from huf.ai.external.policy import (
	ALLOW,
	COMMUNICATE_TOOL_TYPES,
	DENY,
	READ_TOOL_TYPES,
	REQUIRES_APPROVAL,
	classify_tool,
	decide,
)

FULL_POLICY = {
	"read_policy": ALLOW,
	"write_policy": REQUIRES_APPROVAL,
	"communicate_policy": DENY,
}


@pytest.mark.parametrize("tool_type", sorted(READ_TOOL_TYPES))
def test_read_types_classify_as_read(tool_type):
	assert classify_tool(tool_type) == "read"


@pytest.mark.parametrize("tool_type", sorted(COMMUNICATE_TOOL_TYPES))
def test_communicate_types_classify_as_communicate(tool_type):
	assert classify_tool(tool_type) == "communicate"


@pytest.mark.parametrize(
	"tool_type",
	[
		"Create",
		"Update",
		"Delete",
		"Submit",
		"Run Script",
		"Create Document",
		"Update Document",
		"Delete Document",
		"PUT",
	],
)
def test_mutating_types_classify_as_write(tool_type):
	assert classify_tool(tool_type) == "write"


def test_unknown_type_is_write():
	assert classify_tool("Something Unknown") == "write"


def test_none_type_is_write():
	assert classify_tool(None) == "write"


def test_none_type_with_no_path_is_write_not_read():
	assert classify_tool(None, None) == "write"


def test_empty_string_type_is_write():
	assert classify_tool("") == "write"


@pytest.mark.parametrize("hint", ["whatsapp", "telegram", "slack", "email", "helpdesk", "google_chat"])
def test_path_hint_overrides_write_to_communicate(hint):
	assert classify_tool("Create", f"huf.integrations.{hint}.send") == "communicate"


def test_path_hint_overrides_read_to_communicate():
	assert classify_tool("GET", "myapp.slack_client.fetch") == "communicate"


def test_path_hint_is_case_insensitive():
	assert classify_tool("Create", "myapp.Telegram.Send") == "communicate"


def test_path_without_hint_keeps_write():
	assert classify_tool("Create", "myapp.billing.create_invoice") == "write"


def test_path_without_hint_keeps_read():
	assert classify_tool("Get List", "myapp.reports.summary") == "read"


def test_empty_path_is_ignored():
	assert classify_tool("Create", "") == "write"


def test_decide_allow():
	assert decide(FULL_POLICY, "read") == "allow"


def test_decide_approve():
	assert decide(FULL_POLICY, "write") == "approve"


def test_decide_deny():
	assert decide(FULL_POLICY, "communicate") == "deny"


def test_decide_missing_key_denies():
	assert decide({"read_policy": ALLOW}, "write") == "deny"


def test_decide_empty_policy_denies():
	assert decide({}, "read") == "deny"


def test_decide_unknown_class_denies():
	assert decide(FULL_POLICY, "delete") == "deny"


def test_decide_none_class_denies():
	assert decide(FULL_POLICY, None) == "deny"


@pytest.mark.parametrize("garbage", ["allow", "", None, 1, "Allow ", ["Allow"]])
def test_decide_garbage_value_denies(garbage):
	policy = {"read_policy": garbage}
	assert decide(policy, "read") == "deny"


def test_decide_none_policy_denies():
	assert decide(None, "read") == "deny"
