"""Response endpoints for the Huf public developer API (v1).

Wraps the existing `huf.ai.chat_api.run_agent_sync_chat` sync-chat entry
point behind the public v1 request/response shape. Ownership checks and
conversation/agent resolution are delegated entirely to existing code
(`conversations.py`'s `_get_owned_conversation`, `assert_agent_access`) -
no authorization logic is duplicated here.
"""

import frappe

from huf.ai.agent_access import assert_agent_access
from huf.ai.chat_api import run_agent_sync_chat
from huf.api.v1.context import RequestContext
from huf.api.v1.endpoints.conversations import _get_owned_conversation
from huf.api.v1.errors import NotFoundError, ValidationError
from huf.api.v1.scopes import require_agent_allowed, require_scope


def _to_public_shape(result: dict, conversation_id: str) -> dict:
	"""Map `run_agent_sync_chat`'s internal result shape onto the public one.

	`run_agent_sync_chat` is queue-first by default: it returns an
	acknowledgement (`queued=True`, `response=None`) rather than a final
	answer. Only the direct-execution path (not used here) returns a
	populated `response`. Status is reported honestly either way instead
	of inventing output text that was never produced synchronously.
	"""
	if result.get("queued"):
		status = "queued"
	elif result.get("success"):
		status = "completed"
	else:
		status = "failed"

	return {
		"response_id": result.get("agent_run_id"),
		"conversation_id": result.get("conversation_id") or conversation_id,
		"status": status,
		"output": result.get("response"),
	}


def handle_create_response(
	context: RequestContext, agent_id: str, input_text: str, conversation_id: str = None
) -> dict:
	"""POST /huf/api/v1/responses - run an agent turn (sync, queue-first).

	If `conversation_id` is given, the caller must own it; otherwise a new
	conversation is created by `run_agent_sync_chat` (`create_new=True`).
	"""
	if not agent_id:
		raise ValidationError("agent_id is required.")
	if not input_text:
		raise ValidationError("input_text is required.")

	require_scope(context, "agents:run")
	require_agent_allowed(context, agent_id)

	if not frappe.db.exists("Agent", agent_id):
		raise NotFoundError(f"Agent '{agent_id}' was not found.")

	agent_doc = frappe.get_doc("Agent", agent_id)
	assert_agent_access(agent_doc, user=context.user)

	create_new = False
	if conversation_id:
		_get_owned_conversation(conversation_id, context.user)
	else:
		create_new = True

	result = run_agent_sync_chat(
		agent_name=agent_id,
		prompt=input_text,
		conversation_id=conversation_id,
		create_new=create_new,
	)

	return _to_public_shape(result, conversation_id)
