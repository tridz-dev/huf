"""Unit tests for the remote_agents adapter seam."""

from __future__ import annotations

import asyncio
import shutil
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


class TestAcpStdioAdapterAgainstRealPeer:
	"""Real E2E for the production adapter class (not the raw AcpClient, not a fake server).

	This is the exact class huf.ai.remote_agents.tool_handler / execute_remote_tool
	constructs when a Remote Agent Connection resolves to protocol_type=acp_stdio — so a
	pass here is real evidence the P3.2 client-side code path works against a live,
	independent ACP implementation, not just against our own fake-server test double.

	Uses opencode acp rather than kimi acp: kimi's account backing this workspace hit its
	billing-cycle usage limit (see test_client.py's now-skipping
	test_client_prompt_against_real_kimi), so this is the peer that's actually available.
	"""

	@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode CLI not installed")
	def test_fetch_manifest_against_real_opencode(self):
		adapter = AcpStdioAdapter(
			connection_name="e2e-opencode",
			launch_command="opencode",
			launch_args=["acp"],
			timeout=30,
		)

		async def _run():
			return await adapter.fetch_manifest()

		manifest = asyncio.run(_run())
		assert manifest["server_name"] == "OpenCode"
		assert manifest["protocol_version"] == 1
		assert manifest["raw_manifest"]["agentInfo"]["name"] == "OpenCode"

	@pytest.mark.skipif(shutil.which("opencode") is None, reason="opencode CLI not installed")
	def test_recursion_guard_rejects_before_spawning_real_process(self):
		"""The recursion guard must reject a self-referential call chain BEFORE spawning
		the external process — not after. Passing call_chain=[the hop we're about to make]
		simulates "this call already happened once" and asserts create_run() short-circuits
		to a structured error dict rather than actually launching a second opencode process."""
		adapter = AcpStdioAdapter(
			connection_name="e2e-opencode",
			launch_command="opencode",
			launch_args=["acp"],
			timeout=30,
			call_chain=["acp:e2e-opencode:default"],
		)

		async def _run():
			return await adapter.create_run("default", {"prompt": "should never reach opencode"})

		result = asyncio.run(_run())
		assert result["status"] == "error"
		assert result["error"] == "recursive_call"
		assert result["run_id"] is None
