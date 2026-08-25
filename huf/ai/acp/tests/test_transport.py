"""Unit tests for the shared ACP NDJSON transport."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Any

import pytest

from huf.ai.acp.protocol import (
	JsonRpcNotification,
	JsonRpcRequest,
	JsonRpcResponse,
	serialize_message,
)
from huf.ai.acp.transport import AcpRpcError, AcpTransport, AcpTransportClosed

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class _FakeWriter:
	"""Async-writer stand-in that records bytes to an in-memory buffer."""

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


class _MemoryTransportPair:
	"""Pair of transports connected by an in-memory byte stream."""

	def __init__(self) -> None:
		self.server_reader = asyncio.StreamReader()
		self.server_writer = _FakeWriter()
		self.client_reader = asyncio.StreamReader()
		self.client_writer = _FakeWriter()

		self.server = AcpTransport(self.server_reader, self.server_writer)
		self.client = AcpTransport(self.client_reader, self.client_writer)

	def client_to_server(self, data: bytes) -> None:
		self.server_reader.feed_data(data)

	def server_to_client(self, data: bytes) -> None:
		self.client_reader.feed_data(data)

	def close(self) -> None:
		self.server_reader.feed_eof()
		self.client_reader.feed_eof()


@pytest.fixture(params=sorted(FIXTURES_DIR.glob("*.raw")))
def raw_fixture(request: pytest.FixtureRequest) -> Path:
	return request.param


def test_all_fixture_lines_are_valid_json(raw_fixture: Path) -> None:
	"""Every line in every REVIEWS/*.raw fixture must be parseable JSON-RPC."""
	lines = raw_fixture.read_text(encoding="utf-8").splitlines()
	# Some response fixtures are intentionally empty (e.g. exit notifications).
	if not lines:
		return
	for line in lines:
		if not line.strip():
			continue
		raw = json.loads(line)
		assert isinstance(raw, dict)
		assert raw.get("jsonrpc") == "2.0"
		# Ensure our parser accepts the parsed dict.
		from huf.ai.acp.protocol import parse_message

		parse_message(raw)


def test_fixture_line_classification(raw_fixture: Path) -> None:
	"""Classify fixture lines into request/response/notification shapes."""
	for line in raw_fixture.read_text(encoding="utf-8").splitlines():
		if not line.strip():
			continue
		raw = json.loads(line)
		has_id = "id" in raw
		has_method = "method" in raw
		if has_id and has_method:
			JsonRpcRequest.from_dict(raw)
		elif has_id:
			JsonRpcResponse.from_dict(raw)
		elif has_method:
			JsonRpcNotification.from_dict(raw)


def test_request_response_correlation() -> None:
	"""A call on the client transport receives the server-sent response."""

	async def _run() -> dict[str, Any]:
		pair = _MemoryTransportPair()
		pair.client.start()

		# Drive the server's read loop in a background task so requests are handled.
		server_task = asyncio.create_task(pair.server._read_loop())

		# Wire bytes written by each side to the other's reader.
		original_server_write = pair.server.writer.write
		original_client_write = pair.client.writer.write

		def _server_write(data: bytes) -> None:
			original_server_write(data)
			pair.server_to_client(data)

		def _client_write(data: bytes) -> None:
			original_client_write(data)
			pair.client_to_server(data)

		pair.server.writer.write = _server_write  # type: ignore[method-assign]
		pair.client.writer.write = _client_write  # type: ignore[method-assign]

		# Server echoes the request params back as the result.
		async def _handler(request: JsonRpcRequest) -> dict[str, Any]:
			return {"echo": request.method, "params": request.params}

		pair.server.request_handler = _handler

		try:
			result = await pair.client.call("session/new", {"cwd": "/tmp", "mcpServers": []})
		finally:
			pair.close()
			await asyncio.sleep(0)
			server_task.cancel()
			try:
				await server_task
			except asyncio.CancelledError:
				pass

		return result

	result = asyncio.run(_run())
	assert result == {"echo": "session/new", "params": {"cwd": "/tmp", "mcpServers": []}}


def test_notification_dispatch() -> None:
	"""Incoming notifications are dispatched to the registered handler."""

	async def _run() -> list[JsonRpcNotification]:
		reader = asyncio.StreamReader()
		writer = _FakeWriter()
		received: list[JsonRpcNotification] = []

		transport = AcpTransport(
			reader,
			writer,
			notification_handler=lambda n: received.append(n),
		)

		reader.feed_data(
			(json.dumps({"jsonrpc": "2.0", "method": "initialized", "params": {}}) + "\n").encode()
		)
		reader.feed_eof()
		await transport._read_loop()
		return received

	received = asyncio.run(_run())
	assert len(received) == 1
	assert received[0].method == "initialized"


def test_call_raises_on_peer_error() -> None:
	"""A JSON-RPC error response is converted to an AcpRpcError."""

	async def _run() -> None:
		reader = asyncio.StreamReader()
		writer = _FakeWriter()
		transport = AcpTransport(reader, writer)
		transport.start()

		reader.feed_data(
			(
				json.dumps(
					{
						"jsonrpc": "2.0",
						"id": 1,
						"error": {"code": -32602, "message": "Invalid params"},
					}
				)
				+ "\n"
			).encode()
		)
		reader.feed_eof()

		with pytest.raises(AcpRpcError) as exc_info:
			await transport.call("initialize", {"protocolVersion": "bad"})

		assert exc_info.value.code == -32602
		assert "Invalid params" in exc_info.value.message
		assert exc_info.value.request_id == 1

	asyncio.run(_run())


def test_eof_closes_pending_call() -> None:
	"""EOF on stdin closes the transport and fails pending calls."""

	async def _run() -> None:
		reader = asyncio.StreamReader()
		writer = _FakeWriter()
		transport = AcpTransport(reader, writer)
		transport.start()

		# Feed EOF from a background task so the call is already pending.
		async def _feed_eof() -> None:
			await asyncio.sleep(0.01)
			reader.feed_eof()

		asyncio.create_task(_feed_eof())

		with pytest.raises(AcpTransportClosed):
			await transport.call("session/new", {})

	asyncio.run(_run())


def test_transcript_recorder(tmp_path: Path) -> None:
	"""Record NDJSON traffic to a file and replay it through the transport."""

	async def _run() -> list[JsonRpcNotification]:
		transcript_path = tmp_path / "capture.raw"
		writer = _FakeWriter()

		# Record some traffic.
		record_transport = AcpTransport(asyncio.StreamReader(), writer)
		await record_transport.notify("initialized", {})
		await record_transport.send_response(1, {"ok": True})

		transcript_path.write_bytes(writer.buffer.getvalue())

		# Replay the recorded bytes.
		reader = asyncio.StreamReader()
		reader.feed_data(transcript_path.read_bytes())
		reader.feed_eof()

		notifications: list[JsonRpcNotification] = []

		async def _handler(request: JsonRpcRequest) -> Any:
			return None

		replay = AcpTransport(
			reader,
			_FakeWriter(),
			request_handler=_handler,
			notification_handler=lambda n: notifications.append(n),
		)
		await replay._read_loop()
		return notifications

	notifications = asyncio.run(_run())
	assert len(notifications) == 1
	assert notifications[0].method == "initialized"
