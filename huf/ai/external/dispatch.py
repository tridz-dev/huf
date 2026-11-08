"""JSON-RPC dispatch for the external (MCP-facing) agent surface.

``handle_rpc`` takes a parsed JSON-RPC request and the External Agent Session document that the
caller's token already authorised. Identity comes only from ``session_doc``: no handler reads the
user, agent or run from the request arguments, and no response carries the session token.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable

import frappe

from huf.ai.external import mailbox, sessions
from huf.ai.external.core.capabilities import (
	HUB_TIERS,
	hub_tier_required,
	is_hub_capability,
	list_for_mcp,
)
from huf.ai.external.core.jsonrpc import (
	INVALID_PARAMS,
	METHOD_NOT_FOUND,
	JsonRpcError,
	is_notification,
	make_error,
	make_result,
	parse_request,
)
from huf.ai.external.core.policy import classify_tool, decide
from huf.ai.external.core.states import ACTIVE, COMPLETED, FAILED, WAITING_INPUT, can_transition
from huf.ai.external.invoke import (
	BLOCKED_TOOL_TYPES,
	DESKTOP_FUNCTION_PATH_PREFIX,
	external_invoke,
)

PROTOCOL_VERSION = "2025-03-26"
SERVER_INFO = {"name": "huf", "version": "1"}
INSTRUCTIONS = (
	"Use huf_discover to list the tools this connection may run, and huf_context to read the "
	"conversation or agent. Run tools with huf_invoke. Use huf_wait to receive messages from the "
	"user; it returns early when events arrive and reports timed_out otherwise. When huf_wait returns "
	"a task_assigned event, do that task with the available tools, report with huf_report, and finish "
	"with huf_complete. Send progress with huf_report and finish with huf_complete."
)

LEASE_OWNER = "mcp"
LEASE_TTL_SECONDS = 120

CONNECTION_DOCTYPE = "External Agent Connection"
EVENT_DOCTYPE = "External Agent Event"
SESSION_DOCTYPE = "External Agent Session"
RUN_DOCTYPE = "Agent Run"
AGENT_DOCTYPE = "Agent"
AGENT_TOOL_CHILD_DOCTYPE = "Agent Tool"
TOOL_DOCTYPE = "Agent Tool Function"
TOOL_PARAMS_DOCTYPE = "Agent Function Params"
MESSAGE_DOCTYPE = "Agent Message"

SURFACE_REALTIME = "huf_external_surface"
CONTEXT_SCOPES = ("conversation", "agent")
CONTEXT_LIMIT_DEFAULT = 20
CONTEXT_LIMIT_MAX = 50
REPORT_KINDS = ("progress", "observation", "artifact")
COMPLETE_STATUSES = ("success", "failed")
ERROR_STATUSES = ("error", "denied")
HUB_TIER_OFF = "Off"
HUB_TIER_ADMIN = "Admin"


def handle_rpc(request: dict, session_doc) -> dict | None:
	"""Answer one parsed JSON-RPC request for an authorised External Agent Session.

	Returns the response dict, or None for notifications (requests without an ``id``).
	"""
	request_id = request.get("id") if isinstance(request, dict) else None
	try:
		normalized = parse_request(request)
		if is_notification(normalized):
			return None
		request_id = normalized["id"]
		return make_result(request_id, _dispatch(normalized["method"], normalized["params"], session_doc))
	except JsonRpcError as exc:
		return exc.to_response(request_id)


def _dispatch(method: str, params: dict, session_doc) -> dict:
	if method == "initialize":
		return {
			"protocolVersion": PROTOCOL_VERSION,
			"capabilities": {"tools": {}},
			"serverInfo": dict(SERVER_INFO),
			"instructions": INSTRUCTIONS,
		}
	if method == "ping":
		return {}
	if method == "tools/list":
		return {"tools": list_for_mcp(_hub_tier(session_doc))}
	if method == "tools/call":
		return _tools_call(params, session_doc)
	raise JsonRpcError(METHOD_NOT_FOUND, "Method not found", method=method)


def _tools_call(params: dict, session_doc) -> dict:
	name = params.get("name")
	arguments = params.get("arguments")
	if arguments is None:
		arguments = {}
	if not isinstance(arguments, dict):
		raise JsonRpcError(INVALID_PARAMS, "Invalid params", method="tools/call")
	if not isinstance(name, str):
		raise _unknown_tool()

	if is_hub_capability(name):
		# The tier gate runs before anything else. A hidden hub tool answers exactly like a
		# nonexistent one, so a connection cannot probe for tools above its tier.
		tier = _hub_tier(session_doc)
		if not _hub_tier_allows(name, tier):
			raise _unknown_tool()
		from huf.ai.external import hub

		result = _run_guarded(name, session_doc, lambda: hub.dispatch_hub(name, arguments, session_doc, tier))
	elif name in _HANDLERS:
		result = _run_handler(name, arguments, session_doc)
	else:
		raise _unknown_tool()

	return {
		"content": [{"type": "text", "text": json.dumps(result, default=str)}],
		"isError": result.get("status") in ERROR_STATUSES,
	}


def _unknown_tool() -> JsonRpcError:
	return JsonRpcError(INVALID_PARAMS, "Unknown tool", method="tools/call")


def _hub_tier(session_doc) -> str:
	"""Return the connection's hub tier, or Off when the stored value is missing or unrecognised."""
	tier = frappe.db.get_value(CONNECTION_DOCTYPE, session_doc.connection, "hub_tier") or HUB_TIER_OFF
	return tier if tier in HUB_TIERS else HUB_TIER_OFF


def _hub_tier_allows(name: str, tier: str) -> bool:
	if tier == HUB_TIER_OFF:
		return False
	return tier == HUB_TIER_ADMIN or hub_tier_required(name) != HUB_TIER_ADMIN


def _run_handler(name: str, arguments: dict, session_doc) -> dict:
	return _run_guarded(name, session_doc, lambda: _HANDLERS[name](session_doc, arguments))


def _run_guarded(name: str, session_doc, run: Callable[[], dict]) -> dict:
	try:
		sessions.renew_lease(session_doc.name, owner=LEASE_OWNER, ttl_seconds=LEASE_TTL_SECONDS)
		return run()
	except frappe.PermissionError:
		frappe.db.rollback()
		return {"status": "denied", "error": "Not permitted"}
	except Exception:  # noqa: BLE001 - tool failures are reported to the caller, never tracebacks
		frappe.db.rollback()
		frappe.log_error(title="External agent MCP tool failed", message=f"tool={name}")
		return {"status": "error", "error": "Internal error"}


# Capability handlers. Each takes the authorised session document and the model-supplied
# arguments. Only ``session_doc`` supplies identity; arguments carry content only.


def _invalid(message: str) -> dict:
	return {"status": "error", "error": message}


def _int_arg(arguments: dict, key: str, default: int, low: int, high: int) -> int:
	value = arguments.get(key, default)
	if isinstance(value, bool):
		return default
	try:
		number = int(value)
	except (TypeError, ValueError):
		return default
	return max(low, min(number, high))


def _discover(session_doc, arguments: dict) -> dict:
	agent_tools = frappe.get_all(
		AGENT_TOOL_CHILD_DOCTYPE,
		filters={"parent": session_doc.agent, "parenttype": AGENT_DOCTYPE, "parentfield": "agent_tool"},
		fields=["tool"],
		order_by="idx asc",
	)
	names = [row.tool for row in agent_tools if row.tool]
	if not names:
		return {"status": "ok", "tools": []}

	tool_rows = frappe.get_all(
		TOOL_DOCTYPE,
		filters={"name": ["in", names]},
		fields=["name", "tool_name", "description", "types", "function_path"],
	)
	by_name = {row.name: row for row in tool_rows}

	param_rows = frappe.get_all(
		TOOL_PARAMS_DOCTYPE,
		filters={"parent": ["in", names], "parenttype": TOOL_DOCTYPE, "parentfield": "parameters"},
		fields=["parent", "fieldname", "type", "required", "description"],
		order_by="idx asc",
	)
	params_by_tool: dict[str, list[dict]] = defaultdict(list)
	for param in param_rows:
		params_by_tool[param.parent].append(
			{
				"name": param.fieldname,
				"type": param.type,
				"description": param.description or "",
				"required": bool(param.required),
			}
		)

	policy = (
		frappe.db.get_value(
			CONNECTION_DOCTYPE,
			session_doc.connection,
			["read_policy", "write_policy", "communicate_policy"],
			as_dict=True,
		)
		or {}
	)

	tools = []
	for name in names:
		tool = by_name.get(name)
		if tool is None or not tool.tool_name:
			continue
		# Tools that external_invoke would always refuse are not offered at all.
		if tool.types in BLOCKED_TOOL_TYPES or (
			tool.function_path and tool.function_path.startswith(DESKTOP_FUNCTION_PATH_PREFIX)
		):
			continue
		action_class = classify_tool(tool.types, tool.function_path)
		tools.append(
			{
				"name": tool.tool_name,
				"description": tool.description or "",
				"types": tool.types,
				"action_class": action_class,
				"decision": decide(policy, action_class),
				"parameters": params_by_tool.get(name, []),
			}
		)
	return {"status": "ok", "tools": tools}


def _context(session_doc, arguments: dict) -> dict:
	scope = arguments.get("scope", "conversation")
	if scope not in CONTEXT_SCOPES:
		return _invalid("Unknown scope")

	if scope == "agent":
		agent = frappe.db.get_value(
			AGENT_DOCTYPE,
			session_doc.agent,
			["name", "description", "instructions"],
			as_dict=True,
		)
		if not agent:
			return _invalid("Agent not found")
		return {
			"status": "ok",
			"scope": scope,
			"agent": {
				"name": agent.name,
				"description": agent.description or "",
				"instructions": agent.instructions or "",
			},
		}

	limit = _int_arg(arguments, "limit", CONTEXT_LIMIT_DEFAULT, 1, CONTEXT_LIMIT_MAX)
	rows = frappe.get_all(
		MESSAGE_DOCTYPE,
		filters={"conversation": session_doc.conversation},
		fields=["role", "content", "creation"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	messages = [
		{"role": row.role, "content": row.content, "creation": row.creation} for row in reversed(rows)
	]
	return {"status": "ok", "scope": scope, "messages": messages}


def _invoke(session_doc, arguments: dict) -> dict:
	tool_name = arguments.get("tool_name")
	if not isinstance(tool_name, str) or not tool_name:
		return _invalid("tool_name is required")
	tool_args = arguments.get("arguments")
	if tool_args is None:
		tool_args = {}
	if not isinstance(tool_args, dict):
		return _invalid("arguments must be an object")
	client_call_id = arguments.get("client_call_id")
	if client_call_id is not None and not isinstance(client_call_id, str):
		return _invalid("client_call_id must be a string")
	return external_invoke(session_doc, tool_name, tool_args, client_call_id)


def _surface(session_doc, arguments: dict) -> dict:
	action = arguments.get("action")
	if action not in ("create", "update"):
		return _invalid("action must be create or update")
	spec = arguments.get("spec")
	if not isinstance(spec, dict):
		return _invalid("spec must be an object")
	surface_id = arguments.get("surface_id")
	if surface_id is None or surface_id == "":
		surface_id = frappe.generate_hash(length=10)
	elif not isinstance(surface_id, str) or len(surface_id) > 64:
		return _invalid("Invalid surface_id")
	payload = {"action": action, "surface_id": surface_id, "spec": spec}

	mailbox.post_event(session_doc.name, "from_agent", "surface", payload)
	frappe.publish_realtime(
		SURFACE_REALTIME,
		{"session": session_doc.name, **payload},
		user=session_doc.user,
	)
	return {"status": "ok", "surface_id": surface_id}


def _wait(session_doc, arguments: dict) -> dict:
	_ack_delivered(session_doc.name)
	if _session_state(session_doc.name) == ACTIVE:
		sessions.transition(session_doc.name, WAITING_INPUT)
	# The wait polls in fresh transactions, which would discard uncommitted lease, ack and state
	# writes, so persist them first.
	frappe.db.commit()  # nosemgrep: release the snapshot so the wait loop sees new events

	events = mailbox.wait_for_events(session_doc.name, arguments.get("timeout_seconds"))

	if _session_state(session_doc.name) == WAITING_INPUT:
		sessions.transition(session_doc.name, ACTIVE)
	return {"status": "ok", "events": events, "timed_out": not events}


def _ack_delivered(session_name: str) -> None:
	"""Acknowledge every event already handed to the agent by a previous wait."""
	rows = frappe.db.sql(
		"""
		SELECT MAX(`seq`) FROM `tabExternal Agent Event`
		WHERE `session` = %s AND `direction` = %s AND `status` = %s
		""",
		(session_name, "to_agent", "Delivered"),
	)
	max_seq = rows[0][0] if rows else None
	if max_seq:
		mailbox.ack(session_name, int(max_seq))


def _session_state(session_name: str) -> str | None:
	return frappe.db.get_value(SESSION_DOCTYPE, session_name, "state")


def _report(session_doc, arguments: dict) -> dict:
	message = arguments.get("message")
	if not isinstance(message, str) or not message:
		return _invalid("message is required")
	kind = arguments.get("kind", "progress")
	if kind not in REPORT_KINDS:
		return _invalid("Unknown report kind")
	data = arguments.get("data")
	if data is not None and not isinstance(data, dict):
		return _invalid("data must be an object")

	mailbox.post_event(
		session_doc.name,
		"from_agent",
		"report",
		{"kind": kind, "message": message, "data": data or {}},
	)
	return {"status": "ok"}


def _complete(session_doc, arguments: dict) -> dict:
	status = arguments.get("status")
	if status not in COMPLETE_STATUSES:
		return _invalid("status must be success or failed")
	result = arguments.get("result") or ""
	if not isinstance(result, str):
		return _invalid("result must be a string")

	target = COMPLETED if status == "success" else FAILED
	if not can_transition(_session_state(session_doc.name), target):
		return _invalid("Session cannot be completed from its current state")

	sessions.transition(session_doc.name, target)
	mailbox.post_event(
		session_doc.name,
		"from_agent",
		"complete",
		{"status": status, "result": result},
	)
	if status == "success":
		frappe.db.set_value(RUN_DOCTYPE, session_doc.agent_run, "response", result)
	return {"status": "ok"}


_HANDLERS = {
	"huf_discover": _discover,
	"huf_context": _context,
	"huf_invoke": _invoke,
	"huf_surface": _surface,
	"huf_wait": _wait,
	"huf_report": _report,
	"huf_complete": _complete,
}
