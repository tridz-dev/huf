"""Contract tests that replay captured ``kimi acp`` transcripts.

The fixtures under ``tests/fixtures/`` are the ground-truth wire format,
captured live against a real ``kimi acp`` process. These tests replay them
against our own transport, server, and client implementations without
requiring ``kimi`` to be installed or a live subprocess at test time.
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
	serialize_message,
)
from huf.ai.acp.server import AcpServer
from huf.ai.acp.transport import AcpTransport

REVIEWS_DIR = Path(__file__).resolve().parent / "fixtures"


def _fixture_pairs() -> list[tuple[str, Path, Path]]:
	pairs: list[tuple[str, Path, Path]] = []
	for request_path in sorted(REVIEWS_DIR.glob("*_request.raw")):
		response_path = REVIEWS_DIR / request_path.name.replace("_request.raw", "_response.raw")
		if response_path.exists():
			name = request_path.name.replace("_request.raw", "")
			pairs.append((name, request_path, response_path))
	return pairs


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


def _lines_from_raw(path: Path) -> list[str]:
	if path.stat().st_size == 0:
		return []
	return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_written_lines(writer: _FakeWriter) -> list[dict[str, Any]]:
	writer.buffer.seek(0)
	text = writer.buffer.read().decode("utf-8")
	return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture(params=_fixture_pairs(), ids=lambda item: item[0])
def fixture_pair(request: pytest.FixtureRequest) -> tuple[str, Path, Path]:
	return request.param


def test_fixture_pair_parses(fixture_pair: tuple[str, Path, Path]) -> None:
	"""Every captured request/response pair is valid JSON-RPC."""
	_name, request_path, response_path = fixture_pair
	for line in _lines_from_raw(request_path):
		raw = json.loads(line)
		assert raw.get("jsonrpc") == "2.0"
	for line in _lines_from_raw(response_path):
		raw = json.loads(line)
		assert raw.get("jsonrpc") == "2.0"


def test_transport_replays_fixture_pair(fixture_pair: tuple[str, Path, Path]) -> None:
	"""Replay each request against a stub server that echoes the captured response."""
	_name, request_path, response_path = fixture_pair
	request_lines = _lines_from_raw(request_path)
	response_lines = _lines_from_raw(response_path)

	async def _run() -> list[dict[str, Any]]:
		server_reader = asyncio.StreamReader()
		server_writer = _FakeWriter()
		client_reader = asyncio.StreamReader()
		client_writer = _FakeWriter()

		server = AcpTransport(server_reader, server_writer)
		client = AcpTransport(client_reader, client_writer)

		# Server replays the captured response sequence for this request.
		response_queue = list(response_lines)

		async def _handler(request: JsonRpcRequest) -> dict[str, Any]:
			# For notifications (no id) we don't send a response.
			if request.id is None:
				return {}
			while response_queue:
				line = response_queue.pop(0)
				raw = json.loads(line)
				# Notifications are emitted as server-initiated updates; keep
				# consuming until we hit the id-correlated response.
				if "id" not in raw:
					await server.notify(raw["method"], raw.get("params", {}))
					continue
				return raw.get("result", {})
			return {"ok": True}

		server.request_handler = _handler

		# Wire bytes written by each side to the other's reader.
		orig_server_write = server.writer.write
		orig_client_write = client.writer.write

		def _server_write(data: bytes) -> None:
			orig_server_write(data)
			client_reader.feed_data(data)

		def _client_write(data: bytes) -> None:
			orig_client_write(data)
			server_reader.feed_data(data)

		server.writer.write = _server_write  # type: ignore[method-assign]
		client.writer.write = _client_write  # type: ignore[method-assign]

		server_task = asyncio.create_task(server._read_loop())
		client.start()

		try:
			for line in request_lines:
				raw = json.loads(line)
				method = raw.get("method")
				params = raw.get("params", {})
				if "id" in raw:
					await client.call(method, params)
				else:
					await client.notify(method, params)
				# Give the server a tick to process and echo.
				await asyncio.sleep(0)

			# Drain any trailing server-initiated notifications from the fixture.
			while response_queue:
				line = response_queue.pop(0)
				raw = json.loads(line)
				if "method" in raw:
					await server.notify(raw["method"], raw.get("params", {}))
				await asyncio.sleep(0)
		finally:
			client_reader.feed_eof()
			server_reader.feed_eof()
			server_task.cancel()
			try:
				await server_task
			except asyncio.CancelledError:
				pass

		return _parse_written_lines(server_writer)

	written = asyncio.run(_run())
	# The server should have emitted at least the captured response lines.
	assert len(written) >= len(response_lines)


def test_server_handles_full_transcript() -> None:
	"""Replay the full captured transcript through the ACP server."""
	async def _run() -> list[dict[str, Any]]:
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

		# Mock Huf so the prompt produces deterministic text. Return the final
		# response directly so _huf_chat short-circuits without polling.
		server._huf_chat_enqueue_sync = lambda prompt, conversation_id, create_new, agent_name: {
			"conversation_id": "conv_123",
			"run_id": "run_456",
			"response": "Hello from Huf",
		}

		init_request = REVIEWS_DIR / "initialize_request.raw"
		new_request = REVIEWS_DIR / "session_new_request.raw"
		prompt_request = REVIEWS_DIR / "session_prompt_text_request.raw"
		delete_request = REVIEWS_DIR / "session_delete_request.raw"
		exit_request = REVIEWS_DIR / "exit_notification_request.raw"

		requests = []
		for path in (init_request, new_request, prompt_request, delete_request, exit_request):
			requests.extend(_lines_from_raw(path))

		# The prompt request references a captured session id; replace with placeholder
		# because we can't predict the server-generated id.
		for i, line in enumerate(requests):
			raw = json.loads(line)
			params = raw.get("params", {})
			if params.get("sessionId", "").startswith("session_"):
				raw["params"]["sessionId"] = "REPLACE"
				requests[i] = json.dumps(raw)

		reader.feed_data("\n".join(requests).encode())
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	ids = [line.get("id") for line in lines if "id" in line]
	assert 1 in ids
	assert 2 in ids
	assert 3 in ids
	assert 4 in ids
