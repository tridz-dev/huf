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


def run_initiator(run_id=None):
	"""Return the user who started this run, falling back to the session user outside a run.

	The Agent Run keeps its requester when the sweeper drains it as "Administrator".
	"""
	run_id = run_id or getattr(frappe.flags, "huf_current_agent_run_id", None)
	if not run_id:
		return frappe.session.user
	row = frappe.db.get_value("Agent Run", run_id, ["owner", "requester_user"], as_dict=True)
	if not row:
		return None
	return row.get("requester_user") or row.get("owner")


def may_recall_for(subject, run_id=None) -> bool:
	"""True when the subject's memory may reach this chat.

	The subject must have started the run. The session must be the subject too, or
	"Administrator" (the system drain of queued runs). An Administrator or manager
	chatting in someone else's conversation does not recall their memory.
	"""
	if not subject or frappe.session.user not in (subject, "Administrator"):
		return False
	return run_initiator(run_id) == subject


def is_foreign_owner_write(scope_key, conversation_id=None, run_id=None) -> bool:
	"""True when someone else's run would write into the conversation owner's memory."""
	if not scope_key or scope_key != resolve_memory_subject(conversation_id, run_id):
		return False
	return run_initiator(run_id) != scope_key


def pin_memory_run_context(args_dict, ctx):
	"""Overwrite run identity keys from the server-side run context (the model cannot choose them)."""
	huf_ctx = _frappe_run_context_dict(ctx)
	for key in ("conversation_id", "agent_run_id", "agent_name"):
		if huf_ctx.get(key):
			args_dict[key] = huf_ctx[key]
	return args_dict
