"""``gateway_handoff``: generic human handoff (assign a Frappe ToDo and notify).

Used by agents/flows when the AI cannot resolve a request. The assignee uses the same
recipient grammar as ``gateway_send`` but only ``user`` and ``role`` are accepted. A role
creates one ToDo per enabled user holding it, capped at ``MAX_ASSIGNEES``. ToDos are created
as the current run user with normal permission checks (no ``ignore_permissions``). Linked
assignees are pinged in Slack through the ``gateway_send`` machinery and, when the run came
from a gateway event, a short acknowledgement is posted in the originating thread through the
``gateway_reply`` machinery. Idempotent per (gateway event, assignee).
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any

import frappe

from huf.ai.gateways.slack import recipients as rcp
from huf.ai.tools.gateways import reply as _reply
from huf.ai.tools.gateways import send as _send

MAX_ASSIGNEES = 5
MAX_SUMMARY_CHARS = 500
MAX_REASON_CHARS = 300
MAX_DUE_DAYS = 365
_KEY_PREFIX = "huf_gateway_handoff:"
_TRUNCATION_MARK = "..."

GATEWAY_HANDOFF_TOOLS = [
	{
		"tool_name": "gateway_handoff",
		"description": (
			"Hand a request you cannot resolve to a human: creates a ToDo assigned to a user or to every "
			"user with a role (max 5), notifies them in Slack if they linked their account, and tells the "
			"requester in the conversation that it was handed over. Assignee is JSON: "
			"{\"user\": \"a@b.com\"} or {\"role\": \"Support Manager\"}."
		),
		"function_path": "huf.ai.tools.gateways.handoff.handle_gateway_handoff",
		"category": "Communication Tools",
		"parameters": [
			{"label": "Assignee", "fieldname": "assignee", "type": "string", "required": 1,
				"description": "JSON assignee spec: {\"user\": ...} or {\"role\": ...}"},
			{"label": "Summary", "fieldname": "summary", "type": "string", "required": 1,
				"description": f"What the human needs to do (plain text, max {MAX_SUMMARY_CHARS} characters)"},
			{"label": "Reason", "fieldname": "reason", "type": "string", "required": 0,
				"description": f"Why the AI could not resolve it (max {MAX_REASON_CHARS} characters)"},
			{"label": "Due In Days", "fieldname": "due_in_days", "type": "number", "required": 0,
				"description": "Days from today until the ToDo is due"},
			{"label": "Flow Run Id", "fieldname": "flow_run_id", "type": "string", "required": 0,
				"description": "The current Flow Run ID (usually filled in from the run context)"},
		],
	},
]


def _result(ok: bool, **extra) -> str:
	return json.dumps({"success": ok, **extra})


def _plain(text: Any, limit: int) -> str:
	"""Bounded single-block plain text (stored in the ToDo; escaped only when sent to Slack)."""
	value = " ".join(("" if text is None else str(text)).split())
	if len(value) > limit:
		value = value[: limit - len(_TRUNCATION_MARK)] + _TRUNCATION_MARK
	return value


def _due_date(due_in_days: Any):
	if due_in_days in (None, ""):
		return None
	try:
		days = int(float(due_in_days))
	except (TypeError, ValueError):
		return None
	days = max(0, min(days, MAX_DUE_DAYS))
	return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


def _assignees(assignee: Any):
	"""Return ``(users, skipped)`` or raise ValueError for an unsupported spec."""
	specs = rcp.parse_specs(assignee)
	users: list[str] = []
	skipped: list[dict] = []
	for spec in specs:
		if "user" in spec:
			candidates = [str(spec["user"] or "").strip()]
		elif "role" in spec:
			role = str(spec["role"] or "").strip()
			candidates = sorted(set(
				frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent") or []
			))
			if not candidates:
				skipped.append({"recipient": f"role:{role}", "reason": "no users with this role"})
		else:
			raise ValueError("Assignee must be {\"user\": ...} or {\"role\": ...}.")
		for user in candidates:
			if not rcp._usable_user(user):
				skipped.append({"recipient": user, "reason": "user not found or disabled"})
			elif user not in users:
				users.append(user)
	for user in users[MAX_ASSIGNEES:]:
		skipped.append({"recipient": user, "reason": f"over the {MAX_ASSIGNEES} assignee cap"})
	return users[:MAX_ASSIGNEES], skipped


def _origin(flow_run_id, agent_run_id):
	try:
		return _reply.resolve_origin(flow_run_id, agent_run_id)
	except Exception:
		return None


def _description(summary: str, reason: str, event_name: str | None) -> str:
	parts = [summary]
	if reason:
		parts.append(f"Reason: {reason}")
	if event_name:
		parts.append(f"Gateway Event: {event_name}")
	return "\n\n".join(parts)


def _existing_todo(event_name: str, user: str):
	rows = frappe.get_all(
		"ToDo",
		filters={"reference_type": "Gateway Event", "reference_name": event_name,
			"allocated_to": user, "status": "Open"},
		pluck="name",
		limit=1,
	)
	return rows[0] if rows else None


def _display_name(user: str) -> str:
	try:
		return _plain(frappe.db.get_value("User", user, "full_name") or user, 80)
	except Exception:
		return _plain(user, 80)


def _notify(gateway, user: str, todo: str, summary: str) -> str | None:
	"""Send the Slack ping. Returns a skip reason, or None when sent."""
	if gateway is None or str(getattr(gateway, "provider", "")).lower() != "slack":
		return "no Slack gateway for this run"
	slack_id = rcp.slack_id_for_user(gateway.name, user)
	if not slack_id:
		return "no linked Slack identity"
	try:
		api = _send.get_slack_api(gateway)
		channel = api.conversations_open([slack_id])
		if not channel:
			return "could not open a direct message"
		api.post_message(channel, _send.safe_text(f"You were assigned a handoff ({todo}): {summary}"))
	except Exception:
		return "Slack notification failed"
	return None


def handle_gateway_handoff(
	assignee: Any = None,
	summary: str = "",
	reason: str | None = None,
	due_in_days: Any = None,
	flow_run_id: str | None = None,
	agent_run_id: str | None = None,
	**_ignored,
) -> str:
	"""Tool handler. Returns a JSON string; never raises."""
	try:
		summary_text = _plain(summary, MAX_SUMMARY_CHARS)
		if not summary_text:
			return _result(False, error="Summary is empty.")
		reason_text = _plain(reason, MAX_REASON_CHARS)
		try:
			users, skipped = _assignees(assignee)
		except ValueError as exc:
			return _result(False, error=str(exc))
		if not users:
			return _result(False, todos=[], notified=[], skipped=skipped, error="No valid assignee.")
		if not frappe.has_permission("ToDo", "create"):
			return _result(False, todos=[], notified=[], skipped=skipped,
				error="You do not have permission to create ToDos.")

		origin = _origin(flow_run_id, agent_run_id)
		gateway, event = (origin[0], origin[1]) if origin else (None, None)
		event_name = getattr(event, "name", None)
		date = _due_date(due_in_days)

		todos, notified, handed = [], [], []
		for user in users:
			claim = None
			if event_name:
				existing = _existing_todo(event_name, user)
				if existing:
					skipped.append({"recipient": user, "reason": f"already handed off ({existing})"})
					continue
			digest = hashlib.sha256(f"{event_name or summary_text}|{user}".encode()).hexdigest()[:32]
			claim = _KEY_PREFIX + digest
			if not _send._claim(claim, _send.DEFAULT_DEDUPE_TTL_SECONDS):
				skipped.append({"recipient": user, "reason": "already handed off"})
				continue
			doc = {
				"doctype": "ToDo",
				"allocated_to": user,
				"description": _description(summary_text, reason_text, event_name),
				"priority": "Medium",
				"status": "Open",
			}
			if date:
				doc["date"] = date
			if event_name:
				doc["reference_type"] = "Gateway Event"
				doc["reference_name"] = event_name
			try:
				todo = frappe.get_doc(doc).insert()
			except frappe.PermissionError:
				_send._release(claim)
				skipped.append({"recipient": user, "reason": "no permission to create this ToDo"})
				continue
			except Exception:
				_send._release(claim)
				skipped.append({"recipient": user, "reason": "could not create the ToDo"})
				continue
			todos.append(todo.name)
			handed.append((user, todo.name))
			why = _notify(gateway, user, todo.name, summary_text)
			if why:
				skipped.append({"recipient": user, "reason": f"not notified: {why}"})
			else:
				notified.append(user)

		acked = False
		if handed and origin and getattr(event, "conversation_id", None):
			names = ", ".join(_display_name(u) for u, _ in handed)
			refs = ", ".join(t for _, t in handed)
			try:
				from huf.ai.gateway_webhook import send_gateway_reply

				send_gateway_reply(gateway, event, _reply.safe_text(
					f"I've handed this to {names}; ref {refs}"))
				acked = True
			except Exception:
				acked = False
		return _result(bool(todos) or bool(skipped and not todos and any(
			"already handed off" in s["reason"] for s in skipped)),
			todos=todos, notified=notified, skipped=skipped, acknowledged=acked)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "gateway_handoff tool failed")
		return _result(False, error="Could not hand this off.")
