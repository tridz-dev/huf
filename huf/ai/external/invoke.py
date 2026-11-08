"""Server-side invocation of agent tools for external agent sessions.

Identity and policy are decided server-side; nothing here accepts user, agent or run identity
from the model. The acting user comes from the authenticated session, the agent and its tool
list come from the session row and the Agent doctype, and the access policy comes from the
External Agent Connection. Model-supplied args are passed through only after identity keys are
pinned by ``pin_external_identity``.

Standard-alias tools (create_document etc.) are intentionally not usable by external agents;
only tools listed on the agent are allowed.
"""

from __future__ import annotations

import json

import frappe

from huf.ai.external.core.idempotency import make_idempotency_key
from huf.ai.external.core.identity import pin_external_identity
from huf.ai.external.core.policy import classify_tool, decide
from huf.ai.tools.invocation import (
	RunContext,
	check_tool_permission,
	invoke_tool_sync,
	resolve_function_path,
	resolve_tool_doc,
)

CONNECTION_DOCTYPE = "External Agent Connection"
SESSION_DOCTYPE = "External Agent Session"
EVENT_DOCTYPE = "External Agent Event"
AGENT_TOOL_CHILD_DOCTYPE = "Agent Tool"

DENIED_ERROR = "Not permitted"
UNKNOWN_TOOL_ERROR = "Unknown tool"
POLICY_ERROR = "Blocked by access policy"
EXECUTION_ERROR = "Tool execution failed"

BLOCKED_TOOL_TYPES = frozenset({"Code Execution", "Run Agent"})
DESKTOP_FUNCTION_PATH_PREFIX = "huf.ai.tools.desktop_"


def _denied() -> dict:
	return {"status": "denied", "error": DENIED_ERROR}


def _authorize_session(session_doc) -> bool:
	"""Re-check the connection and agent access for the authenticated user."""
	from huf.ai.agent.access import assert_agent_access

	user = frappe.session.user
	try:
		connection = frappe.get_doc(CONNECTION_DOCTYPE, session_doc.connection)
		if not connection.enabled or connection.user != session_doc.user or session_doc.user != user:
			return False
		assert_agent_access(frappe.get_doc("Agent", session_doc.agent), user)
	except Exception:  # noqa: BLE001 - any failure is a denial, never a leak
		return False
	return True


def _agent_has_tool(agent_name: str, tool_docname: str) -> bool:
	return bool(
		frappe.db.exists(
			AGENT_TOOL_CHILD_DOCTYPE,
			{
				"parent": agent_name,
				"parenttype": "Agent",
				"parentfield": "agent_tool",
				"tool": tool_docname,
			},
		)
	)


def _stored_replay(session_name: str, idempotency_key: str) -> dict | None:
	"""Return the stored tool_result payload for this key, if one was already recorded."""
	filters = {
		"session": session_name,
		"idempotency_key": idempotency_key,
		"event_type": "tool_result",
		"direction": "from_agent",
	}
	if not frappe.db.exists(EVENT_DOCTYPE, filters):
		return None
	raw = frappe.db.get_value(EVENT_DOCTYPE, filters, "payload")
	try:
		payload = json.loads(raw) if raw else {}
	except (TypeError, ValueError):
		payload = {}
	if not isinstance(payload, dict):
		payload = {}
	return {**payload, "replayed": True}


def external_invoke(
	session_doc, tool_name: str, args: dict | None, client_call_id: str | None = None
) -> dict:
	"""Run ``tool_name`` for an external agent session, subject to server-side policy.

	``session_doc`` is the External Agent Session already resolved from the caller's token.
	Returns a dict with a ``status`` of "ok", "error", "denied", "approval_required" or
	"replayed" results (replays carry ``replayed: True`` on the stored payload).
	"""
	from huf.ai.external.approvals import consume_approval, request_approval
	from huf.ai.external.mailbox import post_event

	if not _authorize_session(session_doc):
		return _denied()

	tool_doc = resolve_tool_doc(tool_name)
	if not tool_doc:
		return {"status": "error", "error": UNKNOWN_TOOL_ERROR}

	if not _agent_has_tool(session_doc.agent, tool_doc["name"]):
		return _denied()

	tool_type = tool_doc.get("types")
	function_path = resolve_function_path(tool_doc)
	if tool_type in BLOCKED_TOOL_TYPES or (
		function_path and function_path.startswith(DESKTOP_FUNCTION_PATH_PREFIX)
	):
		return _denied()

	if not check_tool_permission(tool_type, allowed_for_guest=False)["allowed"]:
		return _denied()

	connection = frappe.get_doc(CONNECTION_DOCTYPE, session_doc.connection)
	action_class = classify_tool(tool_type, function_path)
	decision = decide(
		{
			"read_policy": connection.read_policy,
			"write_policy": connection.write_policy,
			"communicate_policy": connection.communicate_policy,
		},
		action_class,
	)
	if decision == "deny":
		return {"status": "denied", "error": POLICY_ERROR, "action_class": action_class}

	key = make_idempotency_key(session_doc.name, tool_name, args, client_call_id)
	# Lock the session row and keep the transaction open through policy, approval, execution and
	# post_event. A concurrent call with the same key blocks here, then hits the stored replay
	# instead of running the tool a second time.
	frappe.db.get_value(SESSION_DOCTYPE, session_doc.name, "state", for_update=True)
	replay = _stored_replay(session_doc.name, key)
	if replay is not None:
		return replay

	if decision == "approve" and not consume_approval(session_doc.name, tool_name, args):
		approval = request_approval(session_doc.name, tool_name, action_class, args)
		return {
			"status": "approval_required",
			"approval": approval["approval"],
			"action_class": action_class,
		}
	approval_consumed = decision == "approve"

	call_id = key[:40]
	try:
		pinned = pin_external_identity(
			args,
			conversation_id=session_doc.conversation,
			agent_run_id=session_doc.agent_run,
			agent_name=session_doc.agent,
			call_id=call_id,
		)
		ctx = RunContext(
			conversation_id=session_doc.conversation,
			agent_run_id=session_doc.agent_run,
			agent_name=session_doc.agent,
			call_id=call_id,
			user=frappe.session.user,
		)
		result = invoke_tool_sync(tool_name, pinned, ctx=ctx, telemetry=True)
	except Exception:  # noqa: BLE001 - never leak tracebacks to the caller
		if approval_consumed:
			try:
				from huf.ai.external import approvals

				approvals.consume_restore(session_doc.name, tool_name, args)
			except Exception:  # noqa: BLE001, S110 - restoring is best effort
				pass
		frappe.log_error(title="External agent tool invocation failed")
		return {"status": "error", "error": EXECUTION_ERROR}

	# A handler can report its own failure inside a successful call ({"success": False, ...}).
	result_dict = result.as_dict()
	inner = result_dict.get("result")
	inner_failed = isinstance(inner, dict) and inner.get("success") is False
	payload = {
		"status": "ok" if result.success and not inner_failed else "error",
		**result_dict,
		"action_class": action_class,
	}
	post_event(session_doc.name, "from_agent", "tool_result", payload, idempotency_key=key)
	return payload
