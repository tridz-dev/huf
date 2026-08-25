"""Unit tests for the ACP server role."""

from __future__ import annotations

import asyncio
import io
import json
from typing import Any

import pytest

from huf.ai.acp import server as server_module
from huf.ai.acp.protocol import (
	ERROR_INTERNAL_ERROR,
	METHOD_EXIT,
	METHOD_INITIALIZE,
	METHOD_SESSION_DELETE,
	METHOD_SESSION_NEW,
	METHOD_SESSION_PROMPT,
	METHOD_SESSION_UPDATE,
	JsonRpcRequest,
	serialize_message,
)
from huf.ai.acp.server import AcpServer
from huf.ai.acp.transport import AcpTransport


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


def _make_transport() -> tuple[AcpTransport, asyncio.StreamReader, _FakeWriter]:
	reader = asyncio.StreamReader()
	writer = _FakeWriter()
	return AcpTransport(reader, writer), reader, writer


def _parse_written_lines(writer: _FakeWriter) -> list[dict[str, Any]]:
	writer.buffer.seek(0)
	text = writer.buffer.read().decode("utf-8")
	return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_initialize_returns_capabilities() -> None:
	async def _run() -> list[dict[str, Any]]:
		transport, reader, writer = _make_transport()
		_server = AcpServer(
			transport,
			site="http://test.local",
			api_key="test_key",
			api_secret="test_secret",
			default_agent="TestAgent",
		)

		reader.feed_data(
			(
				serialize_message(
					JsonRpcRequest(
						method=METHOD_INITIALIZE,
						id=1,
						params={
							"protocolVersion": 1,
							"capabilities": {},
							"clientInfo": {"name": "test", "version": "0.1"},
						},
					)
				)
				+ "\n"
			).encode()
		)
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	assert len(lines) == 1
	assert lines[0]["id"] == 1
	assert lines[0]["result"]["protocolVersion"] == 1
	assert lines[0]["result"]["agentInfo"]["name"] == "Huf"


def test_initialize_rejects_string_protocol_version() -> None:
	async def _run() -> list[dict[str, Any]]:
		transport, reader, writer = _make_transport()
		_server = AcpServer(
			transport,
			site="http://test.local",
			api_key="k",
			api_secret="s",
			default_agent="TestAgent",
		)

		reader.feed_data(
			(
				serialize_message(
					JsonRpcRequest(
						method=METHOD_INITIALIZE,
						id=1,
						params={"protocolVersion": "1", "capabilities": {}},
					)
				)
				+ "\n"
			).encode()
		)
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	assert lines[0]["error"]["code"] == -32602


def test_session_lifecycle_with_mocked_huf() -> None:
	async def _run() -> list[dict[str, Any]]:
		transport, reader, writer = _make_transport()
		server = AcpServer(
			transport,
			site="http://test.local",
			api_key="k",
			api_secret="s",
			default_agent="TestAgent",
		)

		# Patch the REST calls and UUID so no real Huf site is needed and we know
		# the session id before sending the prompt. The mock returns the final
		# response directly, so _huf_chat short-circuits without polling.
		server._huf_chat_enqueue_sync = lambda prompt, conversation_id, create_new, agent_name: {
			"conversation_id": "conv_123",
			"run_id": "run_456",
			"response": "Hello from Huf",
		}
		server._huf_resolve_policy_sync = lambda requested_agent: {
			"resolved_agent": requested_agent,
			"allowed_agents": [requested_agent],
		}
		server_module.uuid.uuid4 = lambda: "test_123"

		messages = [
			JsonRpcRequest(method=METHOD_INITIALIZE, id=1, params={"protocolVersion": 1, "capabilities": {}}),
			JsonRpcRequest(
				method=METHOD_SESSION_NEW,
				id=2,
				params={"cwd": "/tmp", "mcpServers": []},
			),
			JsonRpcRequest(
				method=METHOD_SESSION_PROMPT,
				id=3,
				params={"sessionId": "session_test_123", "prompt": [{"type": "text", "text": "Hi"}]},
			),
			JsonRpcRequest(method=METHOD_SESSION_DELETE, id=4, params={"sessionId": "session_test_123"}),
		]

		lines = (serialize_message(msg) + "\n" for msg in messages)
		reader.feed_data("".join(lines).encode())
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	# initialize response + session/new response + prompt notifications + prompt result + delete response
	assert len(lines) >= 4

	initialize_resp = next(line for line in lines if line.get("id") == 1)
	assert "result" in initialize_resp

	new_resp = next(line for line in lines if line.get("id") == 2)
	assert new_resp["result"]["sessionId"] == "session_test_123"

	prompt_result = next(line for line in lines if line.get("id") == 3)
	assert prompt_result["result"]["stopReason"] == "end_turn"

	chunks = [
		line
		for line in lines
		if "method" in line
		and line["method"] == METHOD_SESSION_UPDATE
		and line.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
	]
	assert chunks

	delete_resp = next(line for line in lines if line.get("id") == 4)
	assert delete_resp["result"]["deleted"] is True


def test_session_prompt_polls_queued_run() -> None:
	"""Queue-first runs are polled until get_agent_run_status reports Success."""

	async def _run() -> list[dict[str, Any]]:
		transport, reader, writer = _make_transport()
		server = AcpServer(
			transport,
			site="http://test.local",
			api_key="k",
			api_secret="s",
			default_agent="TestAgent",
			request_timeout=2.0,
			poll_interval=0.05,
		)

		server._huf_chat_enqueue_sync = lambda prompt, conversation_id, create_new, agent_name: {
			"conversation_id": "conv_123",
			"agent_run_id": "run_456",
			"status": "Queued",
			"queued": True,
		}

		poll_calls: list[str] = []

		def _fake_status(run_id: str) -> dict[str, Any]:
			poll_calls.append(run_id)
			if len(poll_calls) < 3:
				return {"status": "Started", "queued": True}
			return {
				"status": "Success",
				"response": "Hello after polling",
				"queued": False,
			}

		server._huf_get_run_status_sync = _fake_status
		server._huf_resolve_policy_sync = lambda requested_agent: {
			"resolved_agent": requested_agent,
			"allowed_agents": [requested_agent],
		}
		server_module.uuid.uuid4 = lambda: "test_123"

		messages = [
			JsonRpcRequest(method=METHOD_INITIALIZE, id=1, params={"protocolVersion": 1, "capabilities": {}}),
			JsonRpcRequest(
				method=METHOD_SESSION_NEW,
				id=2,
				params={"cwd": "/tmp", "mcpServers": []},
			),
			JsonRpcRequest(
				method=METHOD_SESSION_PROMPT,
				id=3,
				params={"sessionId": "session_test_123", "prompt": [{"type": "text", "text": "Hi"}]},
			),
		]

		lines = (serialize_message(msg) + "\n" for msg in messages)
		reader.feed_data("".join(lines).encode())
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	prompt_result = next(line for line in lines if line.get("id") == 3)
	assert prompt_result["result"]["stopReason"] == "end_turn"

	chunks = [
		line
		for line in lines
		if "method" in line
		and line["method"] == METHOD_SESSION_UPDATE
		and line.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
	]
	chunk_text = "".join(c["params"]["update"]["content"]["text"] for c in chunks)
	assert "Hello after polling" in chunk_text


def test_session_prompt_reports_failed_run() -> None:
	"""A failed Huf run surfaces as an internal JSON-RPC error."""

	async def _run() -> list[dict[str, Any]]:
		transport, reader, writer = _make_transport()
		server = AcpServer(
			transport,
			site="http://test.local",
			api_key="k",
			api_secret="s",
			default_agent="TestAgent",
			request_timeout=2.0,
			poll_interval=0.05,
		)

		server._huf_chat_enqueue_sync = lambda prompt, conversation_id, create_new, agent_name: {
			"conversation_id": "conv_123",
			"agent_run_id": "run_456",
			"status": "Queued",
			"queued": True,
		}
		server._huf_get_run_status_sync = lambda run_id: {
			"status": "Failed",
			"error": "Something went wrong",
			"queued": False,
		}
		server._huf_resolve_policy_sync = lambda requested_agent: {
			"resolved_agent": requested_agent,
			"allowed_agents": [requested_agent],
		}
		server_module.uuid.uuid4 = lambda: "test_123"

		messages = [
			JsonRpcRequest(method=METHOD_INITIALIZE, id=1, params={"protocolVersion": 1, "capabilities": {}}),
			JsonRpcRequest(
				method=METHOD_SESSION_NEW,
				id=2,
				params={"cwd": "/tmp", "mcpServers": []},
			),
			JsonRpcRequest(
				method=METHOD_SESSION_PROMPT,
				id=3,
				params={"sessionId": "session_test_123", "prompt": [{"type": "text", "text": "Hi"}]},
			),
		]

		lines = (serialize_message(msg) + "\n" for msg in messages)
		reader.feed_data("".join(lines).encode())
		reader.feed_eof()
		await transport._read_loop()
		return _parse_written_lines(writer)

	lines = asyncio.run(_run())
	prompt_result = next(line for line in lines if line.get("id") == 3)
	assert prompt_result.get("error", {}).get("code") == ERROR_INTERNAL_ERROR


def test_exit_notification_closes_server() -> None:
	async def _run() -> None:
		transport, reader, _writer = _make_transport()
		_server = AcpServer(
			transport,
			site="http://test.local",
			api_key="k",
			api_secret="s",
			default_agent="TestAgent",
		)

		reader.feed_data(
			(
				serialize_message(
					JsonRpcRequest(
						method=METHOD_INITIALIZE,
						id=1,
						params={"protocolVersion": 1, "capabilities": {}},
					)
				)
				+ "\n"
				+ serialize_message(JsonRpcRequest(method=METHOD_EXIT, id=None, params={}))
				+ "\n"
			).encode()
		)
		reader.feed_eof()
		await transport._read_loop()

	asyncio.run(_run())
