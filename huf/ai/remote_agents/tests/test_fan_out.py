"""Unit tests for fan-out orchestration."""

from __future__ import annotations

from typing import Any

import frappe
import pytest

from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.fan_out import _child_payload, _resolve_targets


class FakeGroup:
    def __init__(self, **fields: Any):
        for key, value in fields.items():
            setattr(self, key, value)


class FakeRow:
    def __init__(self, **fields: Any):
        for key, value in fields.items():
            setattr(self, key, value)


@pytest.fixture(autouse=True)
def _reset_frappe_stubs():
    frappe.get_doc = lambda *args, **kwargs: None


def test_resolve_targets_from_connections():
    targets = _resolve_targets("agent-default", ["conn-1", "conn-2"], None)
    assert targets == [("conn-1", "agent-default"), ("conn-2", "agent-default")]


def test_resolve_targets_rejects_both_inputs():
    with pytest.raises(RemoteAgentPolicyError, match="either a connection list or a group"):
        _resolve_targets(None, ["conn-1"], "group-1")


def test_resolve_targets_rejects_neither_input():
    with pytest.raises(RemoteAgentPolicyError, match="Either connections or group"):
        _resolve_targets(None, None, None)


def test_resolve_targets_from_group(monkeypatch):
    group = FakeGroup(
        name="group-1",
        enabled=1,
        members=[
            FakeRow(connection="conn-1", target_agent="agent-1"),
            FakeRow(connection="conn-2", target_agent=None),
        ],
    )

    def _fake_get_doc(doctype, name):
        if doctype == "ACP Agent Group" and name == "group-1":
            return group
        raise frappe.DoesNotExistError(f"Not found: {doctype} {name}")

    monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
    targets = _resolve_targets("agent-default", None, "group-1")
    assert targets == [("conn-1", "agent-1"), ("conn-2", "agent-default")]


def test_resolve_targets_skips_empty_group_members(monkeypatch):
    group = FakeGroup(
        name="group-1",
        enabled=1,
        members=[FakeRow(connection="conn-1", target_agent="agent-1"), FakeRow(connection=None)],
    )

    def _fake_get_doc(doctype, name):
        if doctype == "ACP Agent Group" and name == "group-1":
            return group
        raise frappe.DoesNotExistError(f"Not found: {doctype} {name}")

    monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
    targets = _resolve_targets(None, None, "group-1")
    assert targets == [("conn-1", "agent-1")]


def test_resolve_targets_rejects_disabled_group(monkeypatch):
    group = FakeGroup(name="group-1", enabled=0)

    def _fake_get_doc(doctype, name):
        if doctype == "ACP Agent Group" and name == "group-1":
            return group
        raise frappe.DoesNotExistError(f"Not found: {doctype} {name}")

    monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
    with pytest.raises(RemoteAgentPolicyError, match="disabled"):
        _resolve_targets(None, None, "group-1")


def test_child_payload_preserves_call_chain_string():
    child = _child_payload({"prompt": "hi", "_meta": {"huf_call_chain": "a,b,c"}})
    assert child["_meta"]["huf_call_chain"] == "a,b,c"


def test_child_payload_flattens_call_chain_list():
    child = _child_payload({"prompt": "hi", "_meta": {"huf_call_chain": ["a", "b", "c"]}})
    assert child["_meta"]["huf_call_chain"] == "a,b,c"


def test_child_payload_defaults_empty_chain():
    child = _child_payload({"prompt": "hi"})
    assert child["_meta"]["huf_call_chain"] == ""
