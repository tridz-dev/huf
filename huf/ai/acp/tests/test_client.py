"""Unit tests for the ACP client role."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from huf.ai.acp.client import AcpClient, run_acp_prompt

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
	"""Command line that launches the in-process fake ACP server."""
	return [sys.executable, "-c", _FAKE_SERVER_CODE]


async def _run_client_lifecycle(command: list[str]) -> str:
	async with AcpClient(command, timeout=10.0) as client:
		await client.start()
		await client.new_session()
		return await client.prompt("Say hello.")


def test_client_prompt_against_fake_server(fake_acp_command: list[str]) -> None:
	response = asyncio.run(_run_client_lifecycle(fake_acp_command))
	assert "Hello from fake ACP" in response


async def _run_run_acp_prompt(command: list[str]) -> str:
	return await run_acp_prompt(command, "Say hello.", timeout=10.0)


def test_run_acp_prompt_helper(fake_acp_command: list[str]) -> None:
	response = asyncio.run(_run_run_acp_prompt(fake_acp_command))
	assert "Hello from fake ACP" in response


async def _run_env_scrubbing(command: list[str]) -> AcpClient:
	client = AcpClient(
		command,
		timeout=10.0,
		env={"HUF_ACP_TARGET_TOKEN": "secret-value", "LD_PRELOAD": "nope"},
	)
	await client.start()
	# The fake server does not inspect env; we just verify _build_env filters.
	env = client._build_env()
	assert env.get("HUF_ACP_TARGET_TOKEN") == "secret-value"
	assert "LD_PRELOAD" not in env
	await client.close()
	return client


def test_client_env_scrubbing(fake_acp_command: list[str]) -> None:
	asyncio.run(_run_env_scrubbing(fake_acp_command))


@pytest.mark.skipif(shutil.which("kimi") is None, reason="kimi CLI not installed")
def test_client_prompt_against_real_kimi() -> None:
	async def _run() -> str:
		return await run_acp_prompt(["kimi", "acp"], "Say hello and stop.", timeout=60.0)

	try:
		response = asyncio.run(_run())
	except Exception as exc:
		pytest.skip(f"kimi acp not functional in this environment: {exc}")

	assert isinstance(response, str)
	assert response.strip()
