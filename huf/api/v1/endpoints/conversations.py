"""Conversation endpoints for the Huf public developer API (v1).

Thin wrappers around the existing conversation machinery in
`huf.ai.conversation_manager.ConversationManager` and
`huf.ai.agent_chat.get_history` - ownership checks and history retrieval
are delegated entirely to that existing code, not reimplemented here.
"""

import frappe

from huf.ai.agent_access import assert_agent_access
from huf.ai.agent_chat import get_history
from huf.ai.conversation_manager import ConversationManager
from huf.api.v1.context import RequestContext
from huf.api.v1.errors import NotFoundError
from huf.api.v1.scopes import require_agent_allowed, require_scope


def _to_public_shape(conv_doc) -> dict:
	"""Build the public, stable shape for a single Agent Conversation."""
	return {
		"id": conv_doc.name,
		"agent_id": conv_doc.agent,
		"title": conv_doc.title,
		"created_at": conv_doc.created_at,
		"status": conv_doc.status,
	}


def _owns_conversation(conv_doc, user: str) -> bool:
	"""Whether `user` is the owner of `conv_doc` (or a System Manager).

	Mirrors `huf.ai.agent_chat._assert_owns_conversation` / the ownership
	check in `huf.ai.agent_chat.get_history`, but returns a bool instead of
	raising so callers can convert a failure into `NotFoundError` (no
	existence leak) rather than a `PermissionError`.
	"""
	return conv_doc.owner == user or "System Manager" in frappe.get_roles()


def _get_owned_conversation(conversation_id: str, user: str):
	"""Fetch an Agent Conversation the caller owns, or raise `NotFoundError`.

	Missing and not-owned conversations are indistinguishable to the
	caller, so existence is never leaked.
	"""
	if not frappe.db.exists("Agent Conversation", conversation_id):
		raise NotFoundError(f"Conversation '{conversation_id}' was not found.")

	conv_doc = frappe.get_doc("Agent Conversation", conversation_id)

	if not _owns_conversation(conv_doc, user):
		raise NotFoundError(f"Conversation '{conversation_id}' was not found.")

	return conv_doc


def handle_create_conversation(context: RequestContext, agent_id: str, title: str = None) -> dict:
	"""POST /huf/api/v1/conversations - create a new conversation with an agent."""
	require_scope(context, "conversations:write")
	require_agent_allowed(context, agent_id)

	agent_doc = frappe.get_doc("Agent", agent_id)
	assert_agent_access(agent_doc, user=context.user)

	cm = ConversationManager(agent_name=agent_id)
	conv_doc = cm.create_new_conversation(title=title)

	return _to_public_shape(conv_doc)


def handle_list_conversations(context: RequestContext, agent_id: str = None) -> dict:
	"""GET /huf/api/v1/conversations - the calling user's own conversations."""
	require_scope(context, "conversations:read")

	filters = {"owner": context.user}
	if agent_id:
		filters["agent"] = agent_id

	conversation_names = frappe.get_all(
		"Agent Conversation",
		filters=filters,
		order_by="creation desc",
		pluck="name",
	)
	conversations = [_to_public_shape(frappe.get_doc("Agent Conversation", name)) for name in conversation_names]

	return {"conversations": conversations}


def handle_get_conversation(context: RequestContext, conversation_id: str) -> dict:
	"""GET /huf/api/v1/conversations/{conversation_id} - a single owned conversation."""
	require_scope(context, "conversations:read")

	conv_doc = _get_owned_conversation(conversation_id, context.user)
	return _to_public_shape(conv_doc)


def handle_list_messages(context: RequestContext, conversation_id: str) -> dict:
	"""GET /huf/api/v1/conversations/{conversation_id}/messages - a conversation's history."""
	require_scope(context, "conversations:read")

	_get_owned_conversation(conversation_id, context.user)

	messages = get_history(conversation_id=conversation_id)
	public_messages = [
		{
			"id": message.get("conversation_index"),
			"role": message.get("role"),
			"content": message.get("content"),
			"created_at": message.get("creation"),
		}
		for message in messages
	]

	return {"messages": public_messages}
