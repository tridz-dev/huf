"""Tests for ACP tool-registry wiring.

These tests verify that ``Agent Tool Function`` records can expose a remote ACP
agent as a tool and that the tool handler dispatches to the remote-agent layer.
No real subprocess is spawned; the remote-agent dispatch layer is mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from huf.ai.acp.tool_handler import run_acp_agent_tool
from huf.ai.acp.tool_handler import test_acp_connection as _test_acp_connection
from huf.huf.doctype.agent_tool_function.agent_tool_function import AgentToolFunction

AGENT_TOOL_FUNCTION_JSON = (
    Path(__file__).resolve().parents[4]
    / "huf"
    / "huf"
    / "doctype"
    / "agent_tool_function"
    / "agent_tool_function.json"
)


def _make_tool_doc(**kwargs: Any) -> AgentToolFunction:
    """Return a bare AgentToolFunction instance with the requested attributes."""
    doc = AgentToolFunction.__new__(AgentToolFunction)
    defaults = {
        "tool_name": "test_acp_tool",
        "types": "Remote ACP Agent",
        "description": "Test remote ACP agent tool",
        "function_path": "",
        "reference_doctype": None,
        "parameters": [],
        "params": "{}",
        "base_url": None,
        "http_headers": [],
    }
    defaults.update(kwargs)
    for key, value in defaults.items():
        setattr(doc, key, value)
    return doc


def test_agent_tool_function_json_has_acp_type() -> None:
    """The Agent Tool Function schema exposes the Remote ACP Agent type."""
    raw = json.loads(AGENT_TOOL_FUNCTION_JSON.read_text(encoding="utf-8"))
    types_field = next(f for f in raw["fields"] if f["fieldname"] == "types")
    options = types_field["options"].split("\n")
    assert "Remote ACP Agent" in options


def test_remote_acp_agent_params_and_handler() -> None:
    """Remote ACP Agent tools get the correct parameter schema and handler path."""
    doc = _make_tool_doc()
    doc.before_validate()

    assert doc.function_path == "huf.ai.acp.tool_handler.run_acp_agent_tool"
    assert doc.reference_doctype is None

    params = json.loads(doc.params)
    assert params["type"] == "object"
    assert set(params["required"]) == {"connection_name", "prompt"}
    assert "connection_name" in params["properties"]
    assert "prompt" in params["properties"]


def test_run_acp_agent_tool_delegates_to_execute_remote_tool() -> None:
    """``run_acp_agent_tool`` calls the remote-agent dispatch layer correctly."""
    with patch(
        "huf.ai.acp.tool_handler.execute_remote_tool",
        return_value={"status": "success", "response": "Hello from ACP"},
    ) as mock_execute:
        result = run_acp_agent_tool(
            prompt="Say hello.",
            connection_name="kimi-local",
        )

    mock_execute.assert_called_once_with(
        connection_name="kimi-local",
        agent_id=None,
        payload={"prompt": "Say hello."},
        user="Administrator",
    )
    assert result == {"status": "success", "response": "Hello from ACP"}


def test_run_acp_agent_tool_forwards_agent_id_and_overrides() -> None:
    """Extra kwargs are folded into the payload passed to the dispatch layer."""
    with patch(
        "huf.ai.acp.tool_handler.execute_remote_tool",
        return_value={"status": "success", "response": "ok"},
    ) as mock_execute:
        run_acp_agent_tool(
            prompt="Go.",
            connection_name="local",
            agent_id="assistant",
            extra_param=123,
        )

    mock_execute.assert_called_once_with(
        connection_name="local",
        agent_id="assistant",
        payload={"prompt": "Go.", "extra_param": 123},
        user="Administrator",
    )


def test_test_acp_connection_runs_initialize_handshake() -> None:
    """``test_acp_connection`` returns the normalized manifest from the initialize handshake."""
    connection = _make_tool_doc()
    connection.name = "CONN-0001"
    connection.connection_name = "kimi-local"
    connection.enabled = 1
    connection.protocol_type = "acp_stdio"
    connection.acp_registry_entry = "kimi-acp"
    connection.auth_secret = "secret"
    connection.max_concurrent_sessions = 3
    connection.session_ttl_seconds = 300

    registry = _make_tool_doc()
    registry.name = "kimi-acp"
    registry.registry_name = "Kimi ACP"
    registry.enabled = 1
    registry.binary_path = "/usr/local/bin/kimi"
    registry.argv_shape = '["acp"]'
    registry.working_directory = "/tmp"
    registry.auth_required = 1
    registry.auth_env_key = "HUF_ACP_TARGET_TOKEN"
    registry.max_wall_time_seconds = 120

    def _get_doc(doctype: str, name: str) -> Any:
        if doctype == "Remote Agent Connection":
            return connection
        if doctype == "ACP Command Registry":
            return registry
        raise ValueError(doctype, name)

    with (
        patch("huf.ai.remote_agents.tool_handler.frappe.get_doc", side_effect=_get_doc),
        patch(
            "huf.ai.remote_agents.adapter.AcpStdioAdapter.fetch_manifest",
            return_value={
                "server_name": "kimi-code",
                "protocol_version": 1,
                "agents": [],
                "raw_manifest": {},
            },
        ) as mock_manifest,
        patch(
            "huf.ai.remote_agents.tool_handler.build_launch_context",
            return_value={
                "cmd": ["/usr/local/bin/kimi", "acp"],
                "cwd": "/tmp",
                "env": {},
                "auth_env_key": "HUF_ACP_TARGET_TOKEN",
            },
        ) as mock_build_context,
    ):
        result = _test_acp_connection("kimi-local")

    mock_build_context.assert_called_once_with("kimi-acp", auth_secret="secret")
    mock_manifest.assert_called_once()
    assert result == {"ok": True, "protocol_version": 1, "agent_name": "kimi-code"}
