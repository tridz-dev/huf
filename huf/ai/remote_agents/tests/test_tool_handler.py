"""Unit tests for the outbound remote-agent tool handler."""

from __future__ import annotations

import sys
from typing import Any

import frappe
import pytest

from huf.ai.remote_agents.exceptions import RemoteAgentPolicyError
from huf.ai.remote_agents.policy import POLICY_DOCTYPE
from huf.ai.remote_agents.tool_handler import execute_remote_tool

_FAKE_SERVER_CODE = r"""
import json
import sys

session_id = "session_test_123"

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue

    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        result = {
            "protocolVersion": 1,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {"image": False, "audio": False, "embeddedContext": False},
                "sessionCapabilities": {"list": {}, "resume": {}, "close": {}, "delete": {}},
                "mcpCapabilities": {"http": False, "sse": False},
                "auth": {"logout": {}},
            },
            "authMethods": [],
            "agentInfo": {"name": "FakeACP", "version": "0.1.0"},
        }
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}), flush=True)
    elif method == "initialized":
        continue
    elif method == "session/new":
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"sessionId": session_id, "configOptions": [], "modes": {"currentModeId": "default", "availableModes": [{"id": "default"}]}}}), flush=True)
    elif method == "session/prompt":
        words = ["Hello", "from", "tool", "handler."]
        for word in words:
            print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": word + " "}}}}), flush=True)
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"stopReason": "end_turn"}}), flush=True)
    elif method == "session/delete":
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}), flush=True)
    elif method == "exit":
        break
"""


class FakeConnection:
	def __init__(self, **fields: Any):
		for key, value in fields.items():
			setattr(self, key, value)


@pytest.fixture(autouse=True)
def _reset_frappe_stubs():
	frappe.get_all = lambda *args, **kwargs: []
	frappe.get_doc = lambda *args, **kwargs: None
	frappe.get_roles = lambda user=None: ["System Manager"]


@pytest.fixture
def fake_acp_command() -> list[str]:
	return [sys.executable, "-c", _FAKE_SERVER_CODE]


class TestExecuteRemoteTool:
	def test_runs_prompt_through_connection(self, fake_acp_command: list[str], monkeypatch):
		connection = FakeConnection(
			name="conn-1",
			enabled=1,
			protocol_type="acp_stdio",
			launch_command=fake_acp_command[0],
			launch_args=fake_acp_command[1:],
			working_directory=None,
			auth_secret="secret",
			max_wall_time_seconds=10,
		)

		def _fake_get_doc(doctype, name):
			if doctype == "Remote Agent Connection" and name == "conn-1":
				return connection
			raise frappe.DoesNotExistError(f"Not found: {doctype} {name}")

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE and filters.get("caller_type") == "remote_connection":
				return [
					{
						"name": "policy-1",
						"default_agent": "agent-default",
						"scope_type": "single_agent",
						"capability_scope": "{}",
						"max_run_duration_seconds": 300,
					}
				]
			return []

		monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		result = execute_remote_tool("conn-1", None, {"prompt": "Say hello."})
		assert result["status"] == "success"
		assert "Hello from tool handler" in result["response"]

	def test_disabled_connection_raises(self, monkeypatch):
		connection = FakeConnection(name="conn-1", enabled=0, protocol_type="acp_stdio")

		monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: connection if doctype == "Remote Agent Connection" else None)

		with pytest.raises(RemoteAgentPolicyError, match="disabled"):
			execute_remote_tool("conn-1", None, {"prompt": "Hi."})

	def test_non_acp_protocol_raises(self, monkeypatch):
		connection = FakeConnection(name="conn-1", enabled=1, protocol_type="huf_native")

		monkeypatch.setattr(frappe, "get_doc", lambda doctype, name: connection if doctype == "Remote Agent Connection" else None)

		with pytest.raises(RemoteAgentPolicyError, match="unsupported protocol"):
			execute_remote_tool("conn-1", None, {"prompt": "Hi."})


class TestCycleRejection:
	def test_rejects_direct_recursive_call(self, monkeypatch):
		connection = FakeConnection(
			name="conn-cycle",
			enabled=1,
			protocol_type="acp_stdio",
			launch_command="/nonexistent-binary",
			launch_args=[],
			working_directory=None,
			auth_secret=None,
			max_wall_time_seconds=10,
		)

		def _fake_get_doc(doctype, name):
			if doctype == "Remote Agent Connection" and name == "conn-cycle":
				return connection
			raise frappe.DoesNotExistError(f"Not found: {doctype} {name}")

		def _fake_get_all(doctype, filters=None, fields=None, order_by=None):
			if doctype == POLICY_DOCTYPE and filters.get("caller_type") == "remote_connection":
				return [
					{
						"name": "policy-cycle",
						"default_agent": "agent-default",
						"scope_type": "single_agent",
						"capability_scope": "{}",
						"max_run_duration_seconds": 300,
					}
				]
			return []

		monkeypatch.setattr(frappe, "get_doc", _fake_get_doc)
		monkeypatch.setattr(frappe, "get_all", _fake_get_all)

		# The payload carries a call chain that already contains this exact hop.
		payload = {
			"prompt": "Hi.",
			"_meta": {"huf_call_chain": "acp:conn-cycle:agent-default"},
		}
		result = execute_remote_tool("conn-cycle", None, payload)

		assert result["status"] == "error"
		assert result["error"] == "recursive_call"
		assert "acp:conn-cycle:agent-default" in result["chain"]
