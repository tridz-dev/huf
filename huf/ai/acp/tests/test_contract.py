"""Contract tests using recorded ACP transcript fixtures from REVIEWS/.

These tests replay the captured ``kimi acp`` wire fixtures against Huf's ACP
implementation to confirm message shapes are parsed and handled correctly. They
do not require ``kimi`` to be installed.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import pytest

from huf.ai.acp.protocol import (
	METHOD_EXIT,
	METHOD_INITIALIZE,
	METHOD_INITIALIZED,
	METHOD_SESSION_DELETE,
	METHOD_SESSION_NEW,
	METHOD_SESSION_PROMPT,
	JsonRpcRequest,
	parse_message,
	serialize_message,
)
from huf.ai.acp.server import AcpServer
from huf.ai.acp.transport import AcpTransport

REVIEWS_DIR = Path(__file__).resolve().parent / "fixtures"


class _FakeWriter:
	"""Records bytes written by the transport."""

	def __init__(self) -> None:
		self.buffer = io.BytesIO()
		self.closed = False

	def write(self, data: bytes) -> None:
		self.buffer.write(data)

	async def drain(self) -> None:
		pass

	def close(self) -> None:
		self.closed = True

	async def wait_closed(self) -> None:
		self.closed = True

	def is_closing(self) -> bool:
		return self.closed


def _fixture_pairs() -> list[tuple[str, Path, Path]]:
	"""Return (name, request_path, response_path) tuples for paired fixtures."""
	pairs: list[tuple[str, Path, Path]] = []
	for req_path in sorted(REVIEWS_DIR.glob("*_request.raw")):
		resp_path = req_path.with_name(req_path.name.replace("_request.raw", "_response.raw"))
		if resp_path.exists():
			pairs.append((req_path.stem.replace("_request", ""), req_path, resp_path))
	return pairs


@pytest.mark.parametrize("name,req_path,resp_path", _fixture_pairs())
def test_fixture_pair_parses(name: str, req_path: Path, resp_path: Path) -> None:
	"""Every paired fixture must contain valid JSON-RPC messages."""
	req_lines = [line for line in req_path.read_text(encoding="utf-8").splitlines() if line.strip()]
	resp_lines = [line for line in resp_path.read_text(encoding="utf-8").splitlines() if line.strip()]

	for line in req_lines:
		msg = parse_message(json.loads(line))
		assert isinstance(msg, JsonRpcRequest) or "method" in msg.to_dict()

	for line in resp_lines:
		raw = json.loads(line)
		assert raw.get("jsonrpc") == "2.0"
		# Responses must have an id; notifications must have a method.
		assert "id" in raw or "method" in raw


def _make_server() -> tuple[AcpServer, AcpTransport, asyncio.StreamReader, _FakeWriter]:
	reader = asyncio.StreamReader()
	writer = _FakeWriter()
	transport = AcpTransport(reader, writer)
	server = AcpServer(
		transport,
		site="http://test.local",
		api_key="k",
		api_secret="s",
		default_agent="TestAgent",
	)
	# Avoid making real REST calls. Return the response directly so _huf_chat
	# short-circuits without polling get_agent_run_status.
	server._huf_chat_enqueue_sync = lambda prompt, conversation_id, create_new, agent_name: {
		"conversation_id": "conv_123",
		"response": "Fixture response",
	}
	server._huf_resolve_policy_sync = lambda requested_agent: {
		"resolved_agent": requested_agent,
		"allowed_agents": [requested_agent],
	}
	return server, transport, reader, writer


def _run_server_with_lines(lines: list[str]) -> list[dict[str, Any]]:
	async def _run() -> list[dict[str, Any]]:
		_server, transport, reader, writer = _make_server()
		for line in lines:
			if line.strip():
				reader.feed_data((line + "\n").encode())
		reader.feed_eof()
		await transport._read_loop()

		writer.buffer.seek(0)
		text = writer.buffer.read().decode("utf-8")
		return [json.loads(line) for line in text.splitlines() if line.strip()]

	return asyncio.run(_run())


@pytest.mark.parametrize("name,req_path,resp_path", _fixture_pairs())
def test_server_accepts_fixture_shape(name: str, req_path: Path, resp_path: Path) -> None:
	"""The ACP server accepts each fixture request shape without a protocol error.

	State-changing fixtures (session/*) are preceded by an initialize handshake
	so the server is in a ready state. Notifications (exit, initialized) produce
	no output by design.
	"""
	fixture_lines = [line for line in req_path.read_text(encoding="utf-8").splitlines() if line.strip()]
	msg = parse_message(json.loads(fixture_lines[0]))

	if msg.method in {METHOD_EXIT, METHOD_INITIALIZED}:
		# Pure notifications: just verify the server does not crash.
		_run_server_with_lines(fixture_lines)
		# No response expected for notifications.
		return

	# Prepend initialize so stateful requests are accepted.
	setup = [
		serialize_message(JsonRpcRequest(method=METHOD_INITIALIZE, id=1, params={"protocolVersion": 1, "capabilities": {}})),
	]
	all_lines = setup + fixture_lines
	result_lines = _run_server_with_lines(all_lines)

	# We should get at least the initialize response and one result.
	assert result_lines

	# For fixtures that reference a session id created by the captured peer,
	# our server correctly reports the session is unknown. That is still a
	# valid JSON-RPC/ACP response shape.
	if msg.method in {METHOD_SESSION_PROMPT, METHOD_SESSION_DELETE}:
		fixture_msg = parse_message(json.loads(fixture_lines[0]))
		responses = [line for line in result_lines if line.get("id") == fixture_msg.id]
		assert responses
		resp = responses[0]
		if resp.get("error"):
			assert resp["error"]["code"] == -32602
			assert "sessionId" in resp["error"].get("data", {})
		else:
			assert "result" in resp
		return

	# No JSON-RPC errors should be emitted for other valid fixture shapes.
	error_lines = [line for line in result_lines if line.get("error")]
	assert not error_lines, f"fixture {name} produced errors: {error_lines}"


def test_all_raw_fixtures_are_known_message_types() -> None:
	"""Every NDJSON line in REVIEWS/*.raw is a recognized JSON-RPC message."""
	for raw_path in sorted(REVIEWS_DIR.glob("*.raw")):
		for line in raw_path.read_text(encoding="utf-8").splitlines():
			if not line.strip():
				continue
			parse_message(json.loads(line))


def test_session_prompt_fixture_matches_expected_shape() -> None:
	"""The captured session/prompt fixture has the array-of-blocks prompt shape."""
	path = REVIEWS_DIR / "session_prompt_text_request.raw"
	if not path.exists():
		pytest.skip("session_prompt_text_request.raw not found")

	line = path.read_text(encoding="utf-8").strip()
	msg = parse_message(json.loads(line))
	assert msg.method == METHOD_SESSION_PROMPT
	prompt = msg.params.get("prompt")
	assert isinstance(prompt, list)
	assert prompt[0].get("type") == "text"
