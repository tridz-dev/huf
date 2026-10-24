"""Agent tool: hand the current gateway chat to another solution.

The gateway and chat are derived from the current run (Agent Run -> Agent Conversation channel
``gateway:<name>`` and external_id), never from tool arguments. The tool rewrites the pin only and
sends no message.
"""

import json

import frappe

from huf.ai.solutions import handoff


def _err(code, message=""):
	return json.dumps({"success": False, "error": code, "message": message}, default=str)


def _run_chat():
	"""(gateway, space_key) of the current run, or ('', '')."""
	run_id = getattr(frappe.flags, "huf_current_agent_run_id", None)
	if not run_id:
		return "", ""
	try:
		conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		row = (
			frappe.db.get_value("Agent Conversation", conversation, ["channel", "external_id"], as_dict=True)
			if conversation
			else None
		)
	except Exception:
		return "", ""
	channel = str((row or {}).get("channel") or "")
	external = str((row or {}).get("external_id") or "").strip()
	if not channel.startswith("gateway:") or not external:
		return "", ""
	name = channel[len("gateway:"):].strip()
	if not name or not frappe.db.exists("Gateway", name):
		return "", ""
	return name, _pin_key(name, external)


def _pin_key(gateway, external):
	"""The router pins on ``conversation_id or sender_id``; the conversation external_id may be a thread id."""
	try:
		rows = frappe.get_all(
			"Gateway Event",
			filters={"gateway": gateway},
			or_filters={"thread_id": external, "conversation_id": external, "sender_id": external},
			fields=["conversation_id", "sender_id"],
			order_by="creation desc",
			limit=1,
		)
	except Exception:
		rows = []
	if rows:
		return str(rows[0].get("conversation_id") or rows[0].get("sender_id") or external)
	return external


def _resolve_solution(value):
	value = str(value or "").strip()
	if not value:
		return ""
	if frappe.db.exists("Solution", value):
		return value
	return frappe.db.get_value("Solution", {"title": value}, "name") or value


def handle_handoff_to_solution(**kwargs) -> str:
	gateway, space_key = _run_chat()
	if not gateway:
		return _err("gateway_context_required", "handoff_to_solution only works inside a gateway conversation")
	solution = _resolve_solution(kwargs.get("solution"))
	if not solution:
		return _err("invalid_payload", "solution is required")
	try:
		result = handoff.reassign(gateway, space_key, solution, note_messages=0, set_by="handoff")
	except handoff.HandoffError as exc:
		return _err(exc.code, exc.message)
	return json.dumps(
		{
			"success": True,
			"solution": result["pin"]["solution"],
			"reason": str(kwargs.get("reason") or "")[:200],
			"message": "Chat handed over. No message was sent to the contact.",
		},
		default=str,
	)
