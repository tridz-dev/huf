"""Handoff: move one chat (gateway + space_key) to another solution.

``reassign`` rewrites the Conversation Assignment pin and, optionally, drops the last N messages
of the source solution's conversation into the target solution's conversation as ONE system note
(each solution keeps its own history, A7). Flow targets only change the assignment (A14); the
gateway keeps routing by pin. Nothing here sends a message to the contact.

``space_key`` is the pin key: the sender for a 1:1 chat, the group id for a group (A18).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint

from huf.ai.solutions import assignment, loader

MAX_NOTE_MESSAGES = 20
_NOTE_CHARS = 400


class HandoffError(Exception):
	def __init__(self, code, message=""):
		super().__init__(message or code)
		self.code = code
		self.message = message or code


def _target_row(solution):
	name = str(solution or "").strip()
	row = None
	if name:
		row = frappe.db.get_value(
			"Solution",
			name,
			["name", "title", "status", "test_mode", "primary_target_type", "primary_agent"],
			as_dict=True,
		)
	if not row:
		raise HandoffError("not_found", _("Solution not found"))
	if row.status != "Live" or row.test_mode:
		raise HandoffError("invalid_payload", _("Target solution must be Live"))
	return row


def _require_on_gateway(gateway, solution):
	"""The target must have an enabled binding on this chat's gateway (never re-pin across gateways)."""
	if not frappe.db.exists(
		"Gateway Binding", {"gateway": gateway, "solution": solution, "is_enabled": 1}
	):
		raise HandoffError("not_on_gateway", _("Target solution is not available on this gateway"))


def _primary_agent(solution):
	if not solution:
		return None
	row = frappe.db.get_value("Solution", solution, ["primary_target_type", "primary_agent"], as_dict=True)
	if row and row.primary_target_type == "Agent" and row.primary_agent:
		return row.primary_agent
	return None


def _session_id(gateway, space_key):
	return f"gateway:{gateway}:{str(space_key).strip()}"


def _source_messages(agent, gateway, space_key, limit):
	conv = frappe.get_all(
		"Agent Conversation",
		filters={"agent": agent, "session_id": _session_id(gateway, space_key), "is_active": 1},
		order_by="creation desc",
		limit=1,
		pluck="name",
	)
	if not conv:
		return []
	rows = frappe.get_all(
		"Agent Message",
		filters={"conversation": conv[0], "role": ["in", ["user", "agent"]], "kind": "Message"},
		fields=["role", "content"],
		order_by="conversation_index desc",
		limit=limit,
	)
	return list(reversed(rows))


def _build_note(source_title, rows):
	lines = []
	for r in rows:
		who = "Customer" if r.role == "user" else "Assistant"
		text = " ".join(str(r.content or "").split())
		if len(text) > _NOTE_CHARS:
			text = text[:_NOTE_CHARS] + "..."
		lines.append(f"{who}: {text}")
	head = f"Handoff note: this chat was handed over from {source_title or 'another solution'}. Last messages there:"
	return head + "\n" + "\n".join(lines)


def _inject_note(gateway, space_key, target, source_solution, count):
	"""Returns (added, skipped_reason)."""
	agent = target.primary_agent if target.primary_target_type == "Agent" else None
	if not agent:
		return False, "target_has_no_primary_agent"
	src_agent = _primary_agent(source_solution)
	if not src_agent:
		return False, "no_source_conversation"
	rows = _source_messages(src_agent, gateway, space_key, count)
	if not rows:
		return False, "no_source_messages"
	from huf.ai.conversation_manager import ConversationManager

	cm = ConversationManager(agent_name=agent, channel=f"gateway:{gateway}", external_id=str(space_key).strip())
	conversation = cm.get_or_create_conversation()
	agent_doc = frappe.db.get_value("Agent", agent, ["provider", "model"], as_dict=True) or {}
	source_title = frappe.db.get_value("Solution", source_solution, "title")
	cm.add_message(
		conversation,
		"system",
		_build_note(source_title, rows),
		agent_doc.get("provider"),
		agent_doc.get("model"),
		agent,
	)
	return True, None


def reassign(gateway, space_key, solution, note_messages=0, set_by="handoff", actor=None):
	"""Point the pin of (gateway, space_key) at ``solution``. Raises HandoffError."""
	space_key = str(space_key or "").strip()
	if not gateway or not space_key:
		raise HandoffError("invalid_payload", _("gateway and contact are required"))
	if not frappe.db.exists("Gateway", gateway):
		raise HandoffError("not_found", _("Gateway not found"))
	target = _target_row(solution)
	_require_on_gateway(gateway, target.name)
	count = max(0, min(cint(note_messages), MAX_NOTE_MESSAGES))
	previous = assignment.current_solution(gateway, space_key)
	ttl = loader.load_gateway_settings(gateway)["pin_ttl_hours"]
	pin = assignment.set_pin(gateway, space_key, target.name, set_by, ttl_hours=ttl)
	out = {"pin": {"solution": pin["solution"], "expires_at": pin["expires_at"]}, "note_added": False}
	if count:
		added, reason = False, None
		if previous == target.name:
			reason = "same_solution"
		else:
			added, reason = _inject_note(gateway, space_key, target, previous, count)
		out["note_added"] = added
		if reason:
			out["note_skipped_reason"] = reason
	return out


def _error(code, message=""):
	# contract shape, same as read_models._error
	return {"error": {"code": code, "message": message}}


@frappe.whitelist()
def reassign_conversation(gateway, contact, solution, note_messages=0):
	from huf.ai.whatsapp.management import _can_manage_integrations, _gateway_write_allowed

	gateway = str(gateway or "").strip()
	if not frappe.db.exists("Gateway", gateway):
		return _error("not_found", _("Gateway not found"))
	if not (_can_manage_integrations() and _gateway_write_allowed(gateway)):
		return _error("not_permitted", _("Not permitted"))
	try:
		result = reassign(gateway, contact, solution, cint(note_messages), set_by="handoff", actor=frappe.session.user)
	except HandoffError as exc:
		return _error(exc.code, exc.message)
	return result
