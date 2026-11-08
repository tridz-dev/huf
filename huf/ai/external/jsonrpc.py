"""Pure JSON-RPC 2.0 request parsing and response builders.

No Frappe imports: this module only deals with plain Python values so it can be
used and tested without a bench.
"""

from __future__ import annotations

import json
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
HUF_DENIED = -32001
HUF_APPROVAL_REQUIRED = -32002

JSONRPC_VERSION = "2.0"


class JsonRpcError(Exception):
	"""A JSON-RPC error that can be rendered as an error response."""

	def __init__(self, code: int, message: str, data: Any = None, method: str | None = None):
		super().__init__(message)
		self.code = code
		self.message = message
		self.data = data
		self.method = method

	def to_response(self, request_id: Any) -> dict:
		return make_error(request_id, self.code, self.message, self.data)


def parse_request(body: str | bytes | dict) -> dict:
	"""Validate a JSON-RPC 2.0 request and return its normalized form.

	``body`` may be JSON text (``str`` or ``bytes``) or an already-decoded ``dict``.
	The result always has ``jsonrpc``, ``method`` and ``params`` (``{}`` when
	omitted or ``None``); ``id`` is included only when the request carried one.

	Raises ``JsonRpcError`` with ``PARSE_ERROR``, ``INVALID_REQUEST`` or
	``INVALID_PARAMS`` when the request is malformed.
	"""
	if isinstance(body, (str, bytes)):
		try:
			req = json.loads(body)
		except ValueError as exc:
			raise JsonRpcError(PARSE_ERROR, "Parse error") from exc
	else:
		req = body

	if not isinstance(req, dict):
		raise JsonRpcError(INVALID_REQUEST, "Invalid Request")

	if req.get("jsonrpc") != JSONRPC_VERSION:
		raise JsonRpcError(INVALID_REQUEST, "Invalid Request")

	method = req.get("method")
	if not isinstance(method, str) or not method:
		raise JsonRpcError(INVALID_REQUEST, "Invalid Request")

	params = req.get("params")
	if params is None:
		params = {}
	elif not isinstance(params, dict):
		raise JsonRpcError(INVALID_PARAMS, "Invalid params", method=method)

	normalized: dict[str, Any] = {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params}
	if "id" in req:
		normalized["id"] = req["id"]
	return normalized


def make_result(request_id: Any, value: Any) -> dict:
	return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": value}


def make_error(request_id: Any, code: int, message: str, data: Any = None) -> dict:
	error: dict[str, Any] = {"code": code, "message": message}
	if data is not None:
		error["data"] = data
	return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


def is_notification(req: dict) -> bool:
	"""A request without an ``id`` member is a notification and gets no response."""
	return "id" not in req
