"""Inbound MCP HTTP endpoint for external agents.

Served at ``/api/method/huf.ai.external.gateway.mcp``. Each request is a JSON-RPC 2.0 message
from a client acting for one External Agent Connection of the signed-in user.

Authentication: the caller must send a Frappe API token in the ``Authorization`` header, using the
``token`` or ``bearer`` scheme (``Authorization: token <key>:<secret>``). Cookie sessions and Guest
are refused, so a browser that happens to be logged in cannot be driven to call this endpoint.
OAuth is a planned follow-up.

Session selection: ``Mcp-Session-Id`` header carries the session token. When it is present, the
session is loaded from it and its connection is derived from the session; ``X-Huf-Connection`` and
the ``connection`` parameter are ignored. Without it, ``initialize`` opens a new session and any
other method reuses the user's newest non-terminal session on the connection, creating one if none
exists. The connection is chosen by ``X-Huf-Connection`` header or ``connection`` form parameter;
when neither is given, the user's single enabled connection is used.

Responses are JSON-RPC objects written as the whole response body. Notifications are processed for
their side effects only: errors are logged, never returned, and the response is HTTP 202 with no
body. Permission failures are reported with a generic message and never leak exception text.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from huf.ai.external import dispatch, jsonrpc, sessions
from huf.ai.external.states import TERMINAL_STATES

CONNECTION_HEADER = "X-Huf-Connection"
SESSION_HEADER = "Mcp-Session-Id"
INITIALIZE_METHOD = "initialize"
MCP_RATE_LIMIT = 240
MCP_RATE_WINDOW_SECONDS = 60
NOT_PERMITTED = "Not permitted"
AUTH_SCHEMES = ("token", "bearer")


def _get_header(name: str) -> str | None:
	return frappe.get_request_header(name)


def _respond(payload: dict | None, status: int = 200) -> None:
	"""Write the JSON-RPC payload as the response body, or no body for a notification."""
	frappe.local.response["http_status_code"] = status
	if payload is not None:
		frappe.local.response.update(payload)


def _require_token_auth() -> None:
	"""Refuse Guest and cookie sessions; require an ``Authorization`` header with a token or bearer scheme."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	header = _get_header("Authorization")
	if not header:
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	pieces = header.split()
	scheme = pieces[0].lower() if pieces else ""
	if scheme not in AUTH_SCHEMES:
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)


def _load_connection(connection_name: str):
	connection = frappe.db.get_value(
		sessions.CONNECTION_DOCTYPE,
		connection_name,
		["name", "user", "enabled"],
		as_dict=True,
	)
	if not connection or not connection.enabled or connection.user != frappe.session.user:
		frappe.throw(NOT_PERMITTED, frappe.PermissionError)
	return connection


def _resolve_connection():
	requested = (_get_header(CONNECTION_HEADER) or frappe.form_dict.get("connection") or "").strip()
	if requested:
		return _load_connection(requested)

	candidates = frappe.get_all(
		sessions.CONNECTION_DOCTYPE,
		filters={"user": frappe.session.user, "enabled": 1},
		pluck="name",
		limit=2,
	)
	if not candidates:
		raise jsonrpc.JsonRpcError(jsonrpc.INVALID_PARAMS, "No connection")
	if len(candidates) > 1:
		raise jsonrpc.JsonRpcError(jsonrpc.INVALID_PARAMS, "Specify a connection")
	return _load_connection(candidates[0])


def _newest_open_session(connection):
	newest = frappe.get_all(
		sessions.SESSION_DOCTYPE,
		filters={
			"connection": connection.name,
			"user": frappe.session.user,
			"state": ["not in", list(TERMINAL_STATES)],
		},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	if newest:
		return frappe.get_doc(sessions.SESSION_DOCTYPE, newest[0])
	return None


def _resolve_context(request: dict, create_allowed: bool = True):
	"""Return ``(connection, session)`` for a request.

	With an ``Mcp-Session-Id`` header the session comes first and the connection is derived from it.
	Without one, the connection is resolved from header, parameter or the single enabled connection,
	and the session is the ``initialize`` session, the newest open one, or a new one. When
	``create_allowed`` is False, no new session is created for a non-initialize request and the
	session is ``None`` if none is open.
	"""
	token = _get_header(SESSION_HEADER)
	if token:
		session = sessions.get_session_for_token(token.strip())
		return _load_connection(session.connection), session

	connection = _resolve_connection()
	if request.get("method") == INITIALIZE_METHOD:
		created = sessions.create_session(connection.name)
		return connection, frappe.get_doc(sessions.SESSION_DOCTYPE, created["session"])

	session = _newest_open_session(connection)
	if session is None and create_allowed:
		created = sessions.create_session(connection.name)
		session = frappe.get_doc(sessions.SESSION_DOCTYPE, created["session"])
	return connection, session


def _handle_notification(request: dict) -> None:
	"""Process a notification for its side effects. Errors are logged, never returned."""
	try:
		connection, session_doc = _resolve_context(request, create_allowed=False)
		if session_doc is None:
			return
		sessions.touch_connection(connection.name)
		dispatch.handle_rpc(request, session_doc)
	except Exception:  # noqa: BLE001 -- no response body for notifications; error is logged instead
		frappe.log_error(title="External agent MCP notification failed")


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=MCP_RATE_LIMIT, seconds=MCP_RATE_WINDOW_SECONDS)
def mcp() -> None:
	_require_token_auth()

	try:
		request = jsonrpc.parse_request(frappe.request.get_data())
	except jsonrpc.JsonRpcError as exc:
		_respond(jsonrpc.make_error(None, exc.code, exc.message))
		return

	if jsonrpc.is_notification(request):
		_handle_notification(request)
		_respond(None, status=202)
		return

	request_id = request.get("id")
	try:
		connection, session_doc = _resolve_context(request)
		sessions.touch_connection(connection.name)
		response = dispatch.handle_rpc(request, session_doc)
	except jsonrpc.JsonRpcError as exc:
		_respond(jsonrpc.make_error(request_id, exc.code, exc.message))
		return
	except frappe.PermissionError:
		_respond(jsonrpc.make_error(request_id, jsonrpc.HUF_DENIED, NOT_PERMITTED))
		return

	if response is None:
		_respond(None, status=202)
		return
	_respond(response)
