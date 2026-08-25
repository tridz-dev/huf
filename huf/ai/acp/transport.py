"""ACP stdio transport: NDJSON reader/writer with async request/response correlation.

This module is intentionally free of Frappe/Bench imports so it can be used by
standalone CLI entry points (``huf-acp``) and subprocess-spawning workers alike.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)


from .protocol import (
	ERROR_INTERNAL_ERROR,
	ERROR_INVALID_PARAMS,
	ERROR_INVALID_REQUEST,
	ERROR_METHOD_NOT_FOUND,
	ERROR_PARSE_ERROR,
	JsonRpcError,
	JsonRpcNotification,
	JsonRpcRequest,
	JsonRpcResponse,
	parse_message,
	serialize_message,
)

LOGGER = logging.getLogger("huf.ai.acp.transport")


# ------------------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------------------

class AcpTransportClosed(Exception):
	"""Raised when the transport reaches EOF or is closed while a call is pending."""


class AcpRpcError(Exception):
	"""Raised by :meth:`AcpTransport.call` when the peer returns a JSON-RPC error."""

	def __init__(
		self,
		code: int,
		message: str,
		data: dict[str, Any] | None = None,
		request_id: int | str | None = None,
	):
		super().__init__(f"AcpRpcError {code}: {message}")
		self.code = code
		self.message = message
		self.data = data
		self.request_id = request_id


class AcpApplicationError(Exception):
	"""Request handlers may raise this to control the JSON-RPC error response."""

	def __init__(
		self,
		code: int = ERROR_INTERNAL_ERROR,
		message: str = "Internal error",
		data: dict[str, Any] | None = None,
	):
		self.code = code
		self.message = message
		self.data = data
		super().__init__(message)


# ------------------------------------------------------------------------------
# Writer protocol (duck-typed so tests can supply a capturing writer)
# ------------------------------------------------------------------------------

class _Writable(Protocol):
	def write(self, data: bytes) -> Any: ...
	async def drain(self) -> None: ...
	def close(self) -> None: ...
	async def wait_closed(self) -> None: ...


# ------------------------------------------------------------------------------
# Transcript recorder
# ------------------------------------------------------------------------------

class TranscriptRecorder:
	"""Record inbound/outbound ACP messages for tests and debugging.

	Records raw NDJSON lines as well as parsed messages. The raw line lists are
	compatible with the fixture format used in ``REVIEWS/``.
	"""

	def __init__(self, directory: str | None = None) -> None:
		self.directory = directory
		self.sent: list[str] = []
		self.received: list[str] = []
		self.entries: list[dict[str, Any]] = []

	def record_sent(self, line: str, message: dict[str, Any] | None = None) -> None:
		"""Record an outbound NDJSON line."""
		self.sent.append(line)
		self.entries.append({"direction": "out", "line": line, "message": message})

	def record_received(self, line: str, message: dict[str, Any] | None = None) -> None:
		"""Record an inbound NDJSON line."""
		self.received.append(line)
		self.entries.append({"direction": "in", "line": line, "message": message})

	def clear(self) -> None:
		"""Drop all recorded entries."""
		self.sent.clear()
		self.received.clear()
		self.entries.clear()

	def to_raw_lines(self, direction: str | None = None) -> list[str]:
		"""Return recorded NDJSON lines, optionally filtered by direction."""
		if direction == "out":
			return list(self.sent)
		if direction == "in":
			return list(self.received)
		lines: list[str] = []
		for entry in self.entries:
			lines.append(entry["line"])
		return lines

	def write_to(self, directory: str, prefix: str = "transcript") -> None:
		"""Persist recorded lines to NDJSON files."""
		os.makedirs(directory, exist_ok=True)
		with open(
			os.path.join(directory, f"{prefix}_sent.ndjson"), "w", encoding="utf-8"
		) as sent_f, open(
			os.path.join(directory, f"{prefix}_recv.ndjson"), "w", encoding="utf-8"
		) as recv_f:
			for line in self.sent:
				sent_f.write(line + "\n")
			for line in self.received:
				recv_f.write(line + "\n")


# ------------------------------------------------------------------------------
# Handler types
# ------------------------------------------------------------------------------

RequestHandler = Callable[[JsonRpcRequest], Awaitable[Any]]
NotificationHandler = Callable[[JsonRpcNotification], Awaitable[None]]


# ------------------------------------------------------------------------------
# Transport
# ------------------------------------------------------------------------------

class AcpTransport:
	"""Async NDJSON transport for ACP JSON-RPC messages.

	The transport is role-agnostic: it can drive the client side (sending
	requests and awaiting responses) or the server side (handling incoming
	requests and emitting notifications). Both directions share one read loop.
	"""

	def __init__(
		self,
		reader: asyncio.StreamReader,
		writer: _Writable,
		*,
		request_handler: RequestHandler | None = None,
		notification_handler: NotificationHandler | None = None,
		recorder: TranscriptRecorder | None = None,
	):
		self.reader = reader
		self.writer = writer
		self.recorder = recorder

		# Backwards-compatible single handlers, plus per-method registry.
		self.request_handler = request_handler
		self.notification_handler = notification_handler
		self._request_handlers: dict[str, RequestHandler] = {}
		self._notification_handlers: dict[str, NotificationHandler] = {}

		self._pending: dict[int | str, asyncio.Future[Any]] = {}
		self._next_id = 1
		self._reader_task: asyncio.Task[None] | None = None
		self._write_lock = asyncio.Lock()
		self._closed = False

	# --------------------------------------------------------------------------
	# Construction helpers
	# --------------------------------------------------------------------------

	@classmethod
	async def from_stdio(
		cls,
		*,
		request_handler: RequestHandler | None = None,
		notification_handler: NotificationHandler | None = None,
		recorder: TranscriptRecorder | None = None,
	) -> AcpTransport:
		"""Create a transport wired to ``sys.stdin`` / ``sys.stdout``."""
		loop = asyncio.get_event_loop()
		reader = asyncio.StreamReader(limit=2 * 1024 * 1024)
		protocol = asyncio.StreamReaderProtocol(reader)
		await loop.connect_read_pipe(lambda: protocol, sys.stdin)
		writer_transport, writer_protocol = await loop.connect_write_pipe(
			asyncio.streams.FlowControlMixin, sys.stdout
		)
		writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)
		return cls(
			reader,
			writer,
			request_handler=request_handler,
			notification_handler=notification_handler,
			recorder=recorder,
		)

	@classmethod
	def for_subprocess(
		cls,
		process: asyncio.subprocess.Process,
		*,
		request_handler: RequestHandler | None = None,
		notification_handler: NotificationHandler | None = None,
		recorder: TranscriptRecorder | None = None,
	) -> AcpTransport:
		"""Create a transport wired to an asyncio subprocess' stdin/stdout."""
		if process.stdout is None or process.stdin is None:
			raise ValueError("subprocess must be created with stdin=PIPE and stdout=PIPE")
		# The session/new response from kimi acp can exceed the default 64 KiB limit.
		process.stdout._limit = max(getattr(process.stdout, "_limit", 0), 2 * 1024 * 1024)
		return cls(
			process.stdout,
			process.stdin,
			request_handler=request_handler,
			notification_handler=notification_handler,
			recorder=recorder,
		)

	# --------------------------------------------------------------------------
	# Handler registration
	# --------------------------------------------------------------------------

	def on_request(self, method: str, handler: RequestHandler) -> None:
		"""Register a handler for incoming JSON-RPC requests."""
		self._request_handlers[method] = handler

	def on_notification(self, method: str, handler: NotificationHandler) -> None:
		"""Register a handler for incoming JSON-RPC notifications."""
		self._notification_handlers[method] = handler

	# --------------------------------------------------------------------------
	# Lifecycle
	# --------------------------------------------------------------------------

	def start(self) -> asyncio.Task[None]:
		"""Start the background read loop and return the task."""
		if self._reader_task is None or self._reader_task.done():
			self._reader_task = asyncio.create_task(self._read_loop())
		return self._reader_task

	async def stop(self) -> None:
		"""Close the transport and cancel any pending calls."""
		self._closed = True

		current = asyncio.current_task()
		if (
			self._reader_task is not None
			and not self._reader_task.done()
			and self._reader_task is not current
		):
			self._reader_task.cancel()
			try:
				await self._reader_task
			except asyncio.CancelledError:
				pass
			self._reader_task = None

		for request_id, future in list(self._pending.items()):
			if not future.done():
				future.set_exception(
					AcpTransportClosed(f"transport closed with pending request {request_id}")
				)

		if self.writer is not None:
			self.writer.close()
			try:
				await self.writer.wait_closed()
			except (Exception, asyncio.CancelledError):  # noqa: BLE001, S110
				pass

	async def close(self) -> None:
		"""Alias for :meth:`stop`."""
		await self.stop()

	@property
	def closed(self) -> bool:
		return self._closed

	# --------------------------------------------------------------------------
	# Writing
	# --------------------------------------------------------------------------

	async def _write(self, raw: dict[str, Any]) -> None:
		if self._closed:
			raise AcpTransportClosed("transport is closed")

		msg = parse_message(raw)
		line = serialize_message(msg)
		payload = (line + "\n").encode("utf-8")

		if self.recorder is not None:
			self.recorder.record_sent(line, raw)

		async with self._write_lock:
			self.writer.write(payload)
			await self.writer.drain()

	async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
		"""Send a JSON-RPC notification (alias for :meth:`send_notification`)."""
		await self.send_notification(method, params)

	async def send_notification(
		self, method: str, params: dict[str, Any] | None = None
	) -> None:
		"""Send a JSON-RPC notification."""
		await self._write(JsonRpcNotification(method=method, params=params or {}).to_dict())

	async def send_response(self, request_id: int | str | None, result: Any) -> None:
		"""Send a JSON-RPC success response."""
		if request_id is None:
			raise ValueError("JSON-RPC response requires an id")
		await self._write(JsonRpcResponse(id=request_id, result=result).to_dict())

	async def send_error(
		self,
		request_id: int | str | None,
		code: int,
		message: str,
		data: dict[str, Any] | None = None,
	) -> None:
		"""Send a JSON-RPC error response."""
		await self._write(
			JsonRpcResponse(
				id=request_id,
				error=JsonRpcError(code=code, message=message, data=data),
			).to_dict()
		)

	# --------------------------------------------------------------------------
	# Request/response correlation
	# --------------------------------------------------------------------------

	def _alloc_id(self) -> int:
		request_id = self._next_id
		self._next_id += 1
		return request_id

	async def call(
		self,
		method: str,
		params: dict[str, Any] | None = None,
		*,
		timeout: float | None = None,
	) -> Any:
		"""Alias for :meth:`send_request`."""
		return await self.send_request(method, params, timeout=timeout)

	async def send_request(
		self,
		method: str,
		params: dict[str, Any] | None = None,
		*,
		timeout: float | None = None,
	) -> Any:
		"""Send a JSON-RPC request and await the correlated response."""
		if self._closed:
			raise AcpTransportClosed("transport is closed")

		request_id = self._alloc_id()
		request = JsonRpcRequest(method=method, id=request_id, params=params or {})
		loop = asyncio.get_event_loop()
		future: asyncio.Future[Any] = loop.create_future()
		self._pending[request_id] = future

		try:
			await self._write(request.to_dict())
			response = await asyncio.wait_for(future, timeout=timeout)
		except asyncio.TimeoutError:
			self._pending.pop(request_id, None)
			raise
		except Exception:
			self._pending.pop(request_id, None)
			raise

		if response.error is not None:
			raise AcpRpcError(
				code=response.error.code,
				message=response.error.message,
				data=response.error.data,
				request_id=request_id,
			)
		return response.result

	# --------------------------------------------------------------------------
	# Reading
	# --------------------------------------------------------------------------

	async def _read_loop(self) -> None:
		try:
			while not self._closed:
				try:
					line = await self.reader.readline()
				except (ValueError, OSError) as exc:
					logger.debug("readline error: %s", exc)
					break
				if not line:
					break
				await self._handle_line(line)
		finally:
			self._closed = True
			await self.stop()

	async def _handle_line(self, line: bytes) -> None:
		text = line.decode("utf-8", errors="replace").strip()
		if not text:
			return

		try:
			raw = json.loads(text)
		except json.JSONDecodeError as exc:
			await self.send_error(None, ERROR_PARSE_ERROR, f"Parse error: {exc}")
			return

		if self.recorder is not None:
			self.recorder.record_received(text, raw)

		try:
			msg = parse_message(raw)
		except Exception as exc:  # noqa: BLE001
			request_id = raw.get("id") if isinstance(raw, dict) else None
			await self.send_error(
				request_id,
				ERROR_INVALID_REQUEST,
				f"Invalid JSON-RPC message: {exc}",
			)
			return

		if isinstance(msg, JsonRpcResponse):
			await self._handle_response(msg)
		elif isinstance(msg, JsonRpcRequest):
			if msg.id is None:
				await self._handle_notification(msg.method, msg.params)
			else:
				await self._handle_request(msg)
		elif isinstance(msg, JsonRpcNotification):
			await self._handle_notification(msg.method, msg.params)

	async def _handle_response(self, response: JsonRpcResponse) -> None:
		request_id = response.id
		future = self._pending.pop(request_id, None)
		if future is None:
			return
		if not future.done():
			future.set_result(response)

	async def _handle_request(self, request: JsonRpcRequest) -> None:
		handler = self._request_handlers.get(request.method)
		if handler is None and self.request_handler is not None:
			handler = self.request_handler
		if handler is None:
			await self.send_error(
				request.id,
				ERROR_METHOD_NOT_FOUND,
				f"Method not found: {request.method}",
			)
			return

		try:
			result = await handler(request)
		except AcpApplicationError as exc:
			await self.send_error(request.id, exc.code, exc.message, exc.data)
		except (ValueError, TypeError) as exc:
			await self.send_error(request.id, ERROR_INVALID_PARAMS, str(exc))
		except Exception as exc:  # noqa: BLE001
			await self.send_error(request.id, ERROR_INTERNAL_ERROR, str(exc))
		else:
			if isinstance(result, JsonRpcResponse):
				await self._write(result.to_dict())
			else:
				await self.send_response(request.id, result)

	async def _handle_notification(
		self, method: str, params: dict[str, Any]
	) -> None:
		handler = self._notification_handlers.get(method)
		if handler is None and self.notification_handler is not None:
			handler = self.notification_handler
		if handler is None:
			return
		notification = JsonRpcNotification(method=method, params=params)
		try:
			await handler(notification)
		except Exception:  # noqa: BLE001, S110
			# Notifications have no response channel; swallow handler errors.
			pass
