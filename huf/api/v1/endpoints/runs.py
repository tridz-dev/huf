"""Run endpoints for the Huf public developer API (v1).

Provides read access to Agent Run documents via the public v1 shape.
Ownership checks ensure callers can only access runs from conversations
they own, with the same no-existence-leak pattern as conversations.py.
"""

import frappe

from huf.api.v1.context import RequestContext
from huf.api.v1.errors import NotFoundError
from huf.api.v1.scopes import require_scope


def _owns_run(run_doc, user: str) -> bool:
	"""Whether `user` is the owner of the run's conversation (or a System Manager).

	Agent Runs are owned via their parent conversation. Mirrors the ownership
	check in `_owns_conversation`, returning a bool instead of raising so
	callers can convert a failure into `NotFoundError` (no existence leak).
	"""
	if "System Manager" in frappe.get_roles():
		return True

	if not run_doc.conversation:
		return False

	conversation_doc = frappe.get_doc("Agent Conversation", run_doc.conversation)
	return conversation_doc.owner == user


def _to_public_shape(run_doc) -> dict:
	"""Build the public, stable shape for a single Agent Run.

	Maps the internal status to canonical public states:
	- Queued -> queued
	- Started -> running
	- Success -> completed
	- Failed -> failed

	Note: The doctype currently supports Queued/Started/Success/Failed.
	The public API defines requires_action and cancelled as possible future states,
	but they are not yet mapped from internal statuses.
	"""
	status_map = {
		"Queued": "queued",
		"Started": "running",
		"Success": "completed",
		"Failed": "failed",
	}

	internal_status = run_doc.status or ""
	canonical_status = status_map.get(internal_status, internal_status.lower())

	return {
		"id": run_doc.name,
		"agent_id": run_doc.agent,
		"conversation_id": run_doc.conversation,
		"status": canonical_status,
		"output": run_doc.response,
		"created_at": run_doc.creation,
	}


def handle_get_run(context: RequestContext, run_id: str) -> dict:
	"""GET /huf/api/v1/runs/{run_id} - a single run the caller owns.

	The caller must own the run's parent conversation; otherwise `NotFoundError`
	is raised with no existence leak, same as `_get_owned_conversation`.
	"""
	require_scope(context, "conversations:read")

	if not frappe.db.exists("Agent Run", run_id):
		raise NotFoundError(f"Run '{run_id}' was not found.")

	run_doc = frappe.get_doc("Agent Run", run_id)

	if not _owns_run(run_doc, context.user):
		raise NotFoundError(f"Run '{run_id}' was not found.")

	return _to_public_shape(run_doc)
