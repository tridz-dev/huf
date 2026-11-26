"""Who owns the personal memory of a run.

The subject is always derived from the run's conversation owner. It never
reads ``frappe.session.user``, because background jobs (extraction, queued
drains, sweeper-woken drainers) do not necessarily run as the chatting user.
"""

import frappe

from huf.ai.tools.support.run_context import _frappe_run_context_dict

MEMORY_EXTRACTION_RUN_KIND = "memory_extraction"
MEMORY_EXTRACTION_CHANNEL = "memory_extraction"
MANAGER_ROLES = {"System Manager", "Huf Manager"}
MEMORY_TOOL_TYPES = frozenset(
	{
		"Save Memory Record",
		"Search Memory Records",
		"Get Memory Record",
		"Archive Memory Record",
		"Promote Memory to Knowledge",
	}
)


def resolve_memory_subject(conversation_id=None, run_id=None):
	"""Return the Frappe user whose personal memory this run reads and writes, or None."""
	run_conversation = None
	if run_id:
		run_conversation = frappe.db.get_value("Agent Run", run_id, "conversation")
		if conversation_id and run_conversation and run_conversation != conversation_id:
			return None
	conversation = conversation_id or run_conversation
	if not conversation:
		return None
	row = frappe.db.get_value("Agent Conversation", conversation, ["owner", "channel"], as_dict=True)
	if not row:
		return None
	if row.get("channel") == MEMORY_EXTRACTION_CHANNEL:
		return None
	owner = row.get("owner")
	if not owner or owner == "Guest":
		return None
	if not frappe.db.get_value("User", owner, "enabled"):
		return None
	return owner


def caller_may_act_for(subject) -> bool:
	"""True when the session user is the subject or holds a manager role."""
	user = frappe.session.user
	if not subject or user == "Guest":
		return False
	if user == subject:
		return True
	return bool(set(frappe.get_roles(user)) & MANAGER_ROLES)


def pin_memory_run_context(args_dict, ctx):
	"""Overwrite run identity keys from the server-side run context (the model cannot choose them)."""
	huf_ctx = _frappe_run_context_dict(ctx)
	for key in ("conversation_id", "agent_run_id", "agent_name"):
		if huf_ctx.get(key):
			args_dict[key] = huf_ctx[key]
	return args_dict
