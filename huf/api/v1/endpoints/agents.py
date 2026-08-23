"""Agent endpoints for the Huf public developer API (v1).

Exposes read-only, safe metadata about Agents the calling user is
permitted to use. Permission filtering is delegated entirely to
`huf.ai.agent_access.check_agent_access`, the single source of truth
for "can user X access agent Y" - no authorization logic is duplicated
here.
"""

import frappe

from huf.ai.agent_access import check_agent_access
from huf.api.v1.context import RequestContext
from huf.api.v1.errors import NotFoundError
from huf.api.v1.scopes import require_agent_allowed, require_scope


def _to_public_shape(agent_doc) -> dict:
	"""Build the public, safe metadata shape for a single Agent.

	Deliberately excludes provider credentials, prompts/instructions,
	raw tool/MCP configuration, and any other internal fields - only
	the fields listed below are ever surfaced.
	"""
	return {
		"id": agent_doc.name,
		"name": agent_doc.agent_name,
		"description": agent_doc.description,
		"modality": agent_doc.agent_modality,
		"voice_enabled": bool(agent_doc.voice_enabled),
		"file_upload_supported": bool(agent_doc.allow_file_upload),
		"streaming": bool(agent_doc.run_immediately),
		"execution_mode": "immediate" if agent_doc.run_immediately else "queued",
	}


def _iter_accessible_agents(user: str):
	"""Yield full Agent docs the given user may access, skipping disabled agents."""
	agent_names = frappe.get_all("Agent", filters={"disabled": 0}, pluck="name")
	for agent_name in agent_names:
		agent_doc = frappe.get_doc("Agent", agent_name)
		if check_agent_access(agent_doc, user, for_execution=False):
			yield agent_doc


def handle_list_agents(context: RequestContext) -> dict:
	"""GET /huf/api/v1/agents - agents the calling user can use."""
	require_scope(context, "agents:read")
	agents = [_to_public_shape(agent_doc) for agent_doc in _iter_accessible_agents(context.user)]
	return {"agents": agents}


def handle_get_agent(context: RequestContext, agent_id: str) -> dict:
	"""GET /huf/api/v1/agents/{agent_id} - a single agent the calling user can use.

	Raises `NotFoundError` both when the agent does not exist and when
	the user cannot access it, so existence is never leaked.
	"""
	require_scope(context, "agents:read")
	require_agent_allowed(context, agent_id)

	if not frappe.db.exists("Agent", agent_id):
		raise NotFoundError(f"Agent '{agent_id}' was not found.")

	agent_doc = frappe.get_doc("Agent", agent_id)

	if agent_doc.disabled or not check_agent_access(agent_doc, context.user, for_execution=False):
		raise NotFoundError(f"Agent '{agent_id}' was not found.")

	return _to_public_shape(agent_doc)
