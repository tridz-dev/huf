"""``gateway_reply``: let a Flow (or Agent) answer the conversation that started it.

The destination is never an argument. It is derived from the Flow Run's
trigger payload (``gateway_event``) and confirmed against the Gateway Event's
own ``flow_run`` link, so the tool can only reply to the originating
conversation/thread of the gateway event that triggered this run.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

MAX_REPLY_CHARS = 3000
_TRUNCATION_MARK = "..."

GATEWAY_REPLY_TOOLS = [
	{
		"tool_name": "gateway_reply",
		"description": (
			"Send a text reply to the chat conversation (and thread) that triggered this flow run. "
			"Only works inside a flow started by a gateway message; the destination cannot be chosen."
		),
		"function_path": "huf.ai.tools.gateway_reply.handle_gateway_reply",
		"category": "Communication Tools",
		"parameters": [
			{
				"label": "Text",
				"fieldname": "text",
				"type": "string",
				"required": 1,
				"description": f"Reply text (plain text, max {MAX_REPLY_CHARS} characters)",
			},
			{
				"label": "Flow Run Id",
				"fieldname": "flow_run_id",
				"type": "string",
				"required": 0,
				"description": "The current Flow Run ID (usually filled in from the run context)",
			},
		],
	},
]


def safe_text(text: Any, limit: int = MAX_REPLY_CHARS) -> str:
	"""Slack-safe plain text: escape control characters (<, >, &) so no mass pings or links, then cap."""
	value = "" if text is None else str(text)
	value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()
	if len(value) > limit:
		value = value[: limit - len(_TRUNCATION_MARK)] + _TRUNCATION_MARK
	return value


def _result(ok: bool, **extra) -> str:
	return json.dumps({"success": ok, **extra})


def resolve_origin(flow_run_id: str | None = None, agent_run_id: str | None = None):
	"""Return ``(gateway, event, flow_run_name)`` for a gateway-triggered run, or ``None``."""
	if not flow_run_id and agent_run_id:
		flow_run_id = frappe.db.get_value("Agent Run", agent_run_id, "flow_run")
	if not flow_run_id:
		return None
	row = frappe.db.get_value("Flow Run", flow_run_id, ["trigger_payload"], as_dict=True)
	if not row:
		return None
	try:
		payload = json.loads(row.get("trigger_payload") or "{}")
	except (TypeError, ValueError):
		return None
	event_name = payload.get("gateway_event") if isinstance(payload, dict) else None
	if not event_name:
		return None
	event = frappe.get_doc("Gateway Event", event_name)
	if getattr(event, "flow_run", None) != flow_run_id:
		return None
	gateway = frappe.get_doc("Gateway", event.gateway)
	return gateway, event, flow_run_id


def handle_gateway_reply(
	text: str = "",
	flow_run_id: str | None = None,
	agent_run_id: str | None = None,
	**_ignored,
) -> str:
	"""Tool handler. Returns a JSON string; never raises."""
	try:
		body = safe_text(text)
		if not body:
			return _result(False, error="Reply text is empty.")
		origin = resolve_origin(flow_run_id, agent_run_id)
		if not origin:
			return _result(False, error="No gateway conversation is attached to this run.")
		gateway, event, _run = origin
		if not getattr(event, "conversation_id", None):
			return _result(False, error="The originating event has no conversation.")
		from huf.ai.gateway_webhook import send_gateway_reply

		send_gateway_reply(gateway, event, body)
		return _result(True, gateway_event=event.name, sent_chars=len(body))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "gateway_reply tool failed")
		return _result(False, error="Could not send the reply.")
