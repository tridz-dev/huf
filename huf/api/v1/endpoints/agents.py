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


MAX_PAGE_LENGTH = 50

# Fields fetched directly via `frappe.get_all` - the public shape fields
# plus the fields `check_agent_access` needs to evaluate permission
# (owner, allow_guest; allowed_users/allowed_roles are child tables and
# are bulk-fetched separately in `_fetch_agent_access_maps`).
_AGENT_LIST_FIELDS = [
	"name",
	"agent_name",
	"description",
	"agent_modality",
	"voice_enabled",
	"allow_file_upload",
	"run_immediately",
	"owner",
	"allow_guest",
]


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


def _fetch_agent_access_maps(agent_names: list[str]) -> tuple[dict, dict]:
	"""Bulk-fetch allowed_users/allowed_roles child rows for `agent_names`.

	Two queries total regardless of page size, instead of one `get_doc`
	(and its implicit child-table fetches) per row.
	"""
	if not agent_names:
		return {}, {}

	allowed_users_map: dict[str, list[str]] = {}
	for row in frappe.get_all(
		"Agent User", filters={"parenttype": "Agent", "parent": ["in", agent_names]}, fields=["parent", "user"]
	):
		allowed_users_map.setdefault(row.parent, []).append(row.user)

	allowed_roles_map: dict[str, list[str]] = {}
	for row in frappe.get_all(
		"Agent Role", filters={"parenttype": "Agent", "parent": ["in", agent_names]}, fields=["parent", "role"]
	):
		allowed_roles_map.setdefault(row.parent, []).append(row.role)

	return allowed_users_map, allowed_roles_map


def _list_accessible_agents(user: str, limit: int, offset: int) -> tuple[list, bool]:
	"""Fetch one page of Agent rows the given user may access.

	Fetches the fields the public shape and `check_agent_access` need in
	a single `frappe.get_all` call (no per-row `get_doc`), then bulk-fetches
	the allowed_users/allowed_roles child tables for the fetched page only.

	Returns `(accessible_rows, has_more)`. Because permission filtering is
	applied after the page is fetched, `has_more` reflects whether the
	underlying query returned a full page (i.e. more Agent rows exist),
	not whether more *accessible* rows exist beyond this page.
	"""
	rows = frappe.get_all(
		"Agent",
		filters={"disabled": 0},
		fields=_AGENT_LIST_FIELDS,
		order_by="name asc",
		limit_page_length=limit,
		limit_start=offset,
	)
	has_more = len(rows) == limit

	agent_names = [row.name for row in rows]
	allowed_users_map, allowed_roles_map = _fetch_agent_access_maps(agent_names)

	accessible = []
	for row in rows:
		row["allowed_users"] = allowed_users_map.get(row.name, [])
		row["allowed_roles"] = allowed_roles_map.get(row.name, [])
		if check_agent_access(row, user, for_execution=False):
			accessible.append(row)

	return accessible, has_more


def handle_list_agents(context: RequestContext) -> dict:
	"""GET /huf/api/v1/agents - agents the calling user can use.

	Paginated: accepts `limit` (capped at `MAX_PAGE_LENGTH`) and `offset`
	query params, and returns `has_more`/`cursor` so callers can page
	through the full result set.
	"""
	require_scope(context, "agents:read")

	form_dict = frappe.local.form_dict
	try:
		limit = int(form_dict.get("limit") or MAX_PAGE_LENGTH)
	except (TypeError, ValueError):
		limit = MAX_PAGE_LENGTH
	limit = max(1, min(limit, MAX_PAGE_LENGTH))

	try:
		offset = int(form_dict.get("offset") or 0)
	except (TypeError, ValueError):
		offset = 0
	offset = max(0, offset)

	rows, has_more = _list_accessible_agents(context.user, limit, offset)
	agents = [_to_public_shape(row) for row in rows]

	return {
		"agents": agents,
		"has_more": has_more,
		"cursor": offset + limit if has_more else None,
	}


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
