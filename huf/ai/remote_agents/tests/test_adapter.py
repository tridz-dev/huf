"""Unit tests for the remote_agents adapter seam."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from huf.ai.remote_agents.adapter import AcpStdioAdapter, RemoteAgentAdapter, get_adapter
from huf.ai.remote_agents.exceptions import RemoteAgentNotImplementedError

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
        words = ["Hello", "from", "fake", "ACP."]
        for word in words:
            print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": session_id, "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": word + " "}}}}), flush=True)
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {"stopReason": "end_turn"}}), flush=True)
    elif method == "session/delete":
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}), flush=True)
    elif method == "exit":
        break
"""


@pytest.fixture
def fake_acp_command() -> list[str]:
	return [sys.executable, "-c", _FAKE_SERVER_CODE]


class TestAcpStdioAdapter:
	def test_fetch_manifest(self, fake_acp_command: list[str]) -> None:
		async def _run() -> dict[str, Any]:
			adapter = AcpStdioAdapter(
				connection_name="test",
				launch_command=fake_acp_command[0],
				launch_args=fake_acp_command[1:],
				timeout=10.0,
			)
			return await adapter.fetch_manifest()

		manifest = asyncio.run(_run())
		assert manifest["server_name"] == "FakeACP"
		assert manifest["protocol_version"] == 1

	def test_create_run(self, fake_acp_command: list[str]) -> None:
		async def _run() -> dict[str, Any]:
			adapter = AcpStdioAdapter(
				connection_name="test",
				launch_command=fake_acp_command[0],
				launch_args=fake_acp_command[1:],
				timeout=10.0,
			)
			return await adapter.create_run("default", {"prompt": "Say hello."})

		result = asyncio.run(_run())
		assert result["status"] == "success"
		assert "Hello from fake ACP" in result["response"]
		assert "call_chain" in result

	def test_create_run_with_existing_chain_extends_it(self, fake_acp_command: list[str]) -> None:
		async def _run() -> dict[str, Any]:
			adapter = AcpStdioAdapter(
				connection_name="test",
				launch_command=fake_acp_command[0],
				launch_args=fake_acp_command[1:],
				timeout=10.0,
				call_chain=["huf:siteA:agent1"],
			)
			return await adapter.create_run("default", {"prompt": "Say hello."})

		result = asyncio.run(_run())
		assert result["status"] == "success"
		assert "huf:siteA:agent1" in result["call_chain"]
		assert "acp:test:default" in result["call_chain"]

	def test_create_run_detects_recursion(self, fake_acp_command: list[str]) -> None:
		async def _run() -> dict[str, Any]:
			adapter = AcpStdioAdapter(
				connection_name="test",
				launch_command=fake_acp_command[0],
				launch_args=fake_acp_command[1:],
				timeout=10.0,
				call_chain=["huf:siteA:agent1", "acp:test:default"],
			)
			return await adapter.create_run("default", {"prompt": "Say hello."})

		result = asyncio.run(_run())
		assert result["status"] == "error"
		assert result["error"] == "recursive_call"

	def test_cancel_run(self, fake_acp_command: list[str]) -> None:
		async def _run() -> dict[str, Any]:
			adapter = AcpStdioAdapter(
				connection_name="test",
				launch_command=fake_acp_command[0],
				launch_args=fake_acp_command[1:],
				timeout=10.0,
			)
			await adapter.create_run("default", {"prompt": "Say hello."})
			return await adapter.cancel_run(adapter._session_id or "x")

		cancel = asyncio.run(_run())
		assert cancel["status"] == "cancelled"


class TestGetAdapter:
	def test_get_acp_stdio_adapter(self):
		adapter = get_adapter("acp_stdio", connection_name="x", launch_command="kimi")
		assert isinstance(adapter, AcpStdioAdapter)

	def test_unsupported_protocol_raises(self):
		with pytest.raises(RemoteAgentNotImplementedError):
			get_adapter("huf_native")


class TestRemoteAgentAdapterABC:
	def test_abstract_methods(self):
		with pytest.raises(TypeError):
			RemoteAgentAdapter()
