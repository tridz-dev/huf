"""Whitelisted read APIs for Channel Conversations (Activity viewer)."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.channels.conversation import is_within_24h

_MAX_LIMIT = 100
_STATUSES = ("ai", "handed_off", "closed")
_LIST_FIELDS = [
	"name", "gateway", "channel", "contact_handle", "contact_name", "contact", "status", "lead_doctype",
	"lead_name", "handoff_doctype", "handoff_name", "solution", "agent", "last_inbound_at",
	"last_outbound_at", "last_message_preview", "message_count", "modified",
]


def _require_manage() -> None:
	from huf.ai.whatsapp.management import _can_manage_integrations

	if not _can_manage_integrations():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _clamp(value: Any, default: int, high: int) -> int:
	try:
		n = int(value)
	except (TypeError, ValueError):
		n = default
	return max(0, min(n, high))


@frappe.whitelist()
def list_conversations(gateway: str, status: str | None = None, search: str | None = None, limit: int = 50, start: int = 0) -> dict[str, Any]:
	"""Conversations of one gateway, most recently active first."""
	_require_manage()
	if not gateway:
		return {"success": False, "error": "gateway_required"}
	if status and status not in _STATUSES:
		return {"success": False, "error": "invalid_status"}
	filters: dict[str, Any] = {"gateway": gateway}
	if status:
		filters["status"] = status
	or_filters = None
	if search and search.strip():
		pat = f"%{search.strip()}%"
		or_filters = [
			["contact_handle", "like", pat],
			["contact_name", "like", pat],
			["last_message_preview", "like", pat],
		]
	limit = max(1, _clamp(limit, 50, _MAX_LIMIT))
	rows = frappe.get_all(
		"Channel Conversation",
		filters=filters,
		or_filters=or_filters,
		fields=_LIST_FIELDS,
		order_by="modified desc, name desc",
		limit_start=_clamp(start, 0, 10**9),
		limit_page_length=limit + 1,
	)
	has_more = len(rows) > limit
	rows = rows[:limit]
	for r in rows:
		r["within_24h"] = is_within_24h(r)
	return {"success": True, "items": rows, "has_more": has_more}


@frappe.whitelist()
def get_conversation(name: str) -> dict[str, Any]:
	"""One conversation with its messages (from Gateway Events) and agent tool calls, oldest first."""
	_require_manage()
	if not name or not frappe.db.exists("Channel Conversation", name):
		return {"success": False, "error": "not_found"}
	conv = frappe.get_doc("Channel Conversation", name).as_dict()
	conv["within_24h"] = is_within_24h(conv)
	events = frappe.get_all(
		"Gateway Event",
		filters={"channel_conversation": name},
		fields=[
			"name", "creation", "received_at", "provider_event_id", "sender_id", "message_text", "status",
			"error_message", "target_agent", "agent_run", "reply_message_id", "reply_status", "delivery_error",
		],
		order_by="creation asc, name asc",
		limit_page_length=500,
	)
	messages: list[dict[str, Any]] = []
	runs: list[str] = []
	for e in events:
		messages.append(
			{
				"direction": "in", "event": e["name"], "message_id": e["provider_event_id"],
				"text": e["message_text"] or "", "status": e["status"], "error": e["error_message"] or None,
				"creation": e["received_at"] or e["creation"], "agent": e["target_agent"],
				"agent_run": e["agent_run"], "sent_by": "customer",
			}
		)
		if e["reply_message_id"]:
			messages.append(
				{
					"direction": "out", "event": e["name"], "message_id": e["reply_message_id"], "text": "",
					"status": e["reply_status"] or "", "error": e["delivery_error"] or None,
					"creation": e["creation"], "agent": e["target_agent"], "agent_run": e["agent_run"],
					"sent_by": "agent",
				}
			)
		if e["agent_run"] and e["agent_run"] not in runs:
			runs.append(e["agent_run"])
	tool_calls = []
	if runs:
		tool_calls = frappe.get_all(
			"Agent Tool Call",
			filters={"agent_run": ["in", runs]},
			fields=["name", "agent_run", "tool", "status", "creation"],
			order_by="creation asc",
			limit_page_length=500,
		)
	return {"success": True, "conversation": conv, "messages": messages, "tool_calls": tool_calls}
