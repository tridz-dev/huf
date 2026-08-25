"""ACP (Agent Client Protocol) message types and JSON-RPC 2.0 helpers.

This module is intentionally free of Frappe/Bench imports so it can be used by
standalone CLI entry points (``huf-acp``) and subprocess-spawning workers alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# -----------------------------------------------------------------------------
# Protocol constants
# -----------------------------------------------------------------------------

ACP_PROTOCOL_VERSION = 1
"""ACP protocol version Huf advertises and accepts."""

JSONRPC_VERSION = "2.0"


# -----------------------------------------------------------------------------
# JSON-RPC 2.0 base types
# -----------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class JsonRpcError:
	"""JSON-RPC 2.0 error object."""

	code: int
	message: str
	data: dict[str, Any] | None = None

	def to_dict(self) -> dict[str, Any]:
		out: dict[str, Any] = {"code": self.code, "message": self.message}
		if self.data is not None:
			out["data"] = self.data
		return out

	@classmethod
	def from_dict(cls, raw: dict[str, Any]) -> JsonRpcError:
		return cls(
			code=int(raw["code"]),
			message=str(raw["message"]),
			data=raw.get("data"),
		)


@dataclass(frozen=True, slots=True)
class JsonRpcRequest:
	"""JSON-RPC 2.0 request object."""

	method: str
	id: int | str | None = None
	params: dict[str, Any] = field(default_factory=dict)
	jsonrpc: str = JSONRPC_VERSION

	def to_dict(self) -> dict[str, Any]:
		out: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
		if self.params:
			out["params"] = self.params
		if self.id is not None:
			out["id"] = self.id
		return out

	@classmethod
	def from_dict(cls, raw: dict[str, Any]) -> JsonRpcRequest:
		return cls(
			method=str(raw["method"]),
			id=raw.get("id"),
			params=dict(raw.get("params") or {}),
			jsonrpc=str(raw.get("jsonrpc", JSONRPC_VERSION)),
		)


@dataclass(frozen=True, slots=True)
class JsonRpcResponse:
	"""JSON-RPC 2.0 response object."""

	id: int | str
	result: Any = None
	error: JsonRpcError | None = None
	jsonrpc: str = JSONRPC_VERSION

	def to_dict(self) -> dict[str, Any]:
		out: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
		if self.error is not None:
			out["error"] = self.error.to_dict()
		else:
			out["result"] = self.result
		return out

	@classmethod
	def from_dict(cls, raw: dict[str, Any]) -> JsonRpcResponse:
		error = raw.get("error")
		return cls(
			id=raw["id"],
			result=raw.get("result"),
			error=JsonRpcError.from_dict(error) if error else None,
			jsonrpc=str(raw.get("jsonrpc", JSONRPC_VERSION)),
		)


@dataclass(frozen=True, slots=True)
class JsonRpcNotification:
	"""JSON-RPC 2.0 notification object (no ``id``)."""

	method: str
	params: dict[str, Any] = field(default_factory=dict)
	jsonrpc: str = JSONRPC_VERSION

	def to_dict(self) -> dict[str, Any]:
		out: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
		if self.params:
			out["params"] = self.params
		return out

	@classmethod
	def from_dict(cls, raw: dict[str, Any]) -> JsonRpcNotification:
		return cls(
			method=str(raw["method"]),
			params=dict(raw.get("params") or {}),
			jsonrpc=str(raw.get("jsonrpc", JSONRPC_VERSION)),
		)


JsonRpcMessage = JsonRpcRequest | JsonRpcResponse | JsonRpcNotification


# -----------------------------------------------------------------------------
# ACP method names
# -----------------------------------------------------------------------------

METHOD_INITIALIZE = "initialize"
METHOD_INITIALIZED = "initialized"
METHOD_SESSION_NEW = "session/new"
METHOD_SESSION_PROMPT = "session/prompt"
METHOD_SESSION_CANCEL = "session/cancel"
METHOD_SESSION_DELETE = "session/delete"
METHOD_SESSION_UPDATE = "session/update"
METHOD_SESSION_LIST = "session/list"
METHOD_SESSION_RESUME = "session/resume"
METHOD_EXIT = "exit"

SERVER_METHODS: frozenset[str] = frozenset(
	{
		METHOD_INITIALIZE,
		METHOD_SESSION_NEW,
		METHOD_SESSION_PROMPT,
		METHOD_SESSION_CANCEL,
		METHOD_SESSION_DELETE,
	}
)
"""Methods an ACP server is expected to handle in V1."""


# -----------------------------------------------------------------------------
# JSON-RPC standard error codes
# -----------------------------------------------------------------------------

ERROR_PARSE_ERROR = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL_ERROR = -32603


# -----------------------------------------------------------------------------
# Content blocks
# -----------------------------------------------------------------------------

CONTENT_TYPE_TEXT = "text"


@dataclass(frozen=True, slots=True)
class TextContentBlock:
	"""ACP text content block, used inside ``session/prompt`` prompts and
	``agent_*_chunk`` update contents.
	"""

	text: str
	type: str = CONTENT_TYPE_TEXT

	def to_dict(self) -> dict[str, str]:
		return {"type": self.type, "text": self.text}

	@classmethod
	def from_dict(cls, raw: dict[str, Any]) -> TextContentBlock:
		return cls(text=str(raw.get("text", "")), type=str(raw.get("type", CONTENT_TYPE_TEXT)))


def make_text_content(text: str) -> dict[str, str]:
	"""Return a plain-text ACP content block dict."""
	return {"type": CONTENT_TYPE_TEXT, "text": text}


def make_text_prompt(text: str) -> list[dict[str, str]]:
	"""Wrap a plain string prompt into the array of content blocks ACP expects."""
	return [make_text_content(text)]


# -----------------------------------------------------------------------------
# Capability helpers
# -----------------------------------------------------------------------------

def make_client_capabilities() -> dict[str, Any]:
	"""Return an empty capability dict for the client side of ``initialize``.

	ACP is bidirectional; declaring zero capabilities prevents a remote agent
	from requesting file/terminal access back into Huf.
	"""
	return {}


def make_server_capabilities(
	*,
	agent_name: str = "Huf",
	agent_version: str = "1.0.0",
) -> dict[str, Any]:
	"""Return Huf's ACP server capability payload for ``initialize`` result.

	V1 exposes a minimal, honest capability set. Tool-result blocks, images,
	audio, and persistent session state are intentionally omitted.
	"""
	return {
		"protocolVersion": ACP_PROTOCOL_VERSION,
		"agentCapabilities": {
			"loadSession": False,
			"promptCapabilities": {
				"image": False,
				"audio": False,
				"embeddedContext": False,
			},
			"sessionCapabilities": {
				"list": {},
				"resume": {},
				"close": {},
				"delete": {},
			},
			"mcpCapabilities": {"http": False, "sse": False},
			"auth": {"logout": {}},
		},
		"authMethods": [],
		"agentInfo": {"name": agent_name, "version": agent_version},
	}


# -----------------------------------------------------------------------------
# Utility helpers
# -----------------------------------------------------------------------------

def is_valid_protocol_version(value: Any) -> bool:
	"""ACP ``protocolVersion`` must be an integer."""
	return isinstance(value, int) and not isinstance(value, bool)


def jsonrpc_error_response(
	request_id: int | str | None,
	code: int,
	message: str,
	data: dict[str, Any] | None = None,
) -> dict[str, Any]:
	"""Build a JSON-RPC error response dict."""
	out: dict[str, Any] = {
		"jsonrpc": JSONRPC_VERSION,
		"error": {"code": code, "message": message},
	}
	if data is not None:
		out["error"]["data"] = data
	if request_id is not None:
		out["id"] = request_id
	return out


def parse_message(raw: dict[str, Any]) -> JsonRpcMessage:
	"""Parse a raw JSON-RPC dict into the appropriate dataclass.

	Raises ValueError for messages that cannot be classified as a valid
	JSON-RPC request, response, or notification.
	"""
	if not isinstance(raw, dict):
		raise TypeError("JSON-RPC message must be a JSON object")
	if raw.get("jsonrpc") != JSONRPC_VERSION:
		raise ValueError(f"Unsupported jsonrpc version: {raw.get('jsonrpc')!r}")

	has_id = "id" in raw
	has_method = "method" in raw
	has_result = "result" in raw
	has_error = "error" in raw

	if has_result or has_error:
		if not has_id:
			raise ValueError("JSON-RPC response must have an 'id'")
		return JsonRpcResponse.from_dict(raw)

	if has_method:
		if has_id:
			return JsonRpcRequest.from_dict(raw)
		return JsonRpcNotification.from_dict(raw)

	raise ValueError(
		"JSON-RPC message is neither request, response, nor notification"
	)


def serialize_message(msg: JsonRpcRequest | JsonRpcResponse | JsonRpcNotification | dict[str, Any]) -> str:
	"""Serialize an ACP message or plain JSON-RPC dict to a single NDJSON line."""
	if isinstance(msg, dict):
		return json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
	return json.dumps(msg.to_dict(), ensure_ascii=False, separators=(",", ":"))
