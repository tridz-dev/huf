"""Hub tools for external agent sessions: find and build Huf agents, tools, tables and apps.

``dispatch_hub`` maps a hub capability to an existing, permission-checked builder function. The
acting identity is always ``frappe.session.user`` (the authorised session user); user and agent
identity are never read from the arguments. Every write needs a fresh approval, whatever the
connection policy says, and the builder is only called (with its confirm flag set) after that
approval has been consumed.

| Capability        | Wrapped function(s)                                        | Tier         | Huf capability       |
|-------------------|------------------------------------------------------------|--------------|----------------------|
| huf_find_agents   | hub_triage.find_existing_agents, builder.list_agents       | Build, Admin | agent.use            |
| huf_find_tools    | hub_triage.discover_site_capabilities, Agent Tool Function | Build, Admin | tools.use            |
| huf_find_tables   | Huf Data Table registry (per-doctype read permission)      | Build, Admin | none (doc perms)     |
| huf_create_agent  | builder.draft_agent, attach_agent_tools, publish_agent     | Build, Admin | agent.create         |
| huf_create_tool   | builder.create_agent_tool                                  | Build, Admin | tools.create         |
| huf_create_table  | builder.create_huf_table                                   | Build, Admin | data.tables.manage   |
| huf_build_app     | builder.draft_app / update_app / install_app (by action)   | Admin        | agent.create         |

The builder functions enforce their own role and document-permission checks; those are not
bypassed here. Nothing in this module creates scripts, runs code, reaches a shell, passes through
to generic client calls, or manages users, roles or secrets.
"""

from __future__ import annotations

import json
from typing import Any

import frappe

from huf.ai.external import approvals
from huf.permissions import has_capability

TIER_OFF = "Off"
TIER_BUILD = "Build"
TIER_ADMIN = "Admin"

DENIED_ERROR = "Not permitted"
FAILED_ERROR = "Hub action failed"

_MAX_LIMIT = 50

# capability -> (is_write, minimum tier, required Huf capability or None)
_HUB_TOOLS: dict[str, tuple[bool, str, str | None]] = {
	"huf_find_agents": (False, TIER_BUILD, "agent.use"),
	"huf_find_tools": (False, TIER_BUILD, "tools.use"),
	"huf_find_tables": (False, TIER_BUILD, None),
	"huf_create_agent": (True, TIER_BUILD, "agent.create"),
	"huf_create_tool": (True, TIER_BUILD, "tools.create"),
	"huf_create_table": (True, TIER_BUILD, "data.tables.manage"),
	"huf_build_app": (True, TIER_ADMIN, "agent.create"),
}

_APP_ACTIONS = ("create", "update", "install")


def _denied() -> dict:
	return {"status": "denied", "error": DENIED_ERROR}


def _tier_allows(tier: str | None, minimum: str) -> bool:
	if tier == TIER_ADMIN:
		return True
	return tier == TIER_BUILD and minimum == TIER_BUILD


def _clean(value: Any) -> Any:
	"""Convert docs, rows and dates into plain JSON-serialisable data."""
	return json.loads(json.dumps(value, default=str))


def _limit(arguments: dict, default: int = 10) -> int:
	try:
		value = int(arguments.get("limit", default))
	except (TypeError, ValueError):
		value = default
	return max(1, min(value, _MAX_LIMIT))


def _query(arguments: dict) -> str:
	return str(arguments.get("query") or "").strip()


# ---------------------------------------------------------------------------
# Read-only tools
# ---------------------------------------------------------------------------


def _find_agents(arguments: dict) -> dict:
	from huf.ai.agent.access import check_agent_access
	from huf.ai.tools import builder, hub_triage

	limit = _limit(arguments)
	query = _query(arguments)
	user = frappe.session.user

	matches = hub_triage.find_existing_agents(query, limit=limit).get("matches", [])
	listed = builder.list_agents(limit=limit).get("agents", [])

	seen: set[str] = set()
	agents: list[dict] = []
	for row in list(matches) + list(listed):
		agent_name = row.get("agent_name")
		if not agent_name or agent_name in seen or row.get("is_system"):
			continue
		try:
			doc = frappe.get_doc("Agent", agent_name)
			if not check_agent_access(doc, user):
				continue
		except Exception:  # noqa: BLE001, S112 - an unreadable agent is simply not listed
			continue
		seen.add(agent_name)
		agents.append(
			{
				"agent_name": agent_name,
				"description": (row.get("description") or "")[:200],
				"tools": row.get("tools") or [],
				"disabled": bool(row.get("disabled", 0)),
			}
		)
		if len(agents) >= limit:
			break
	return {"agents": agents, "query": query}


def _find_tools(arguments: dict) -> dict:
	from huf.ai.tools import hub_triage

	limit = _limit(arguments)
	query = _query(arguments)

	site = hub_triage.discover_site_capabilities(query, limit=min(limit, 8))

	tools: list[dict] = []
	if frappe.has_permission("Agent Tool Function", "read"):
		tokens = [t for t in query.lower().split() if len(t) >= 3]
		for row in frappe.get_list(
			"Agent Tool Function",
			fields=["name", "tool_name", "description", "types", "reference_doctype"],
			limit_page_length=200,
			order_by="modified desc",
		):
			haystack = f"{row.get('tool_name') or ''} {row.get('description') or ''}".lower()
			if tokens and not any(t in haystack for t in tokens):
				continue
			tools.append(
				{
					"name": row.get("name"),
					"description": (row.get("description") or "")[:200],
					"type": row.get("types"),
					"reference_doctype": row.get("reference_doctype"),
				}
			)
			if len(tools) >= limit:
				break

	return {
		"tools": tools,
		"reports": site.get("reports", []),
		"resources": site.get("resources", []),
		"installed_apps": site.get("installed_apps", []),
		"catalogue_matches": site.get("catalogue_matches", []),
		"query": query,
	}


def _find_tables(arguments: dict) -> dict:
	from huf.ai.tools.builder import _require_builder_capability

	_require_builder_capability()
	limit = _limit(arguments)
	query = _query(arguments).lower()

	if not frappe.has_permission("Huf Data Table", "read"):
		return {"tables": [], "query": query}

	tables: list[dict] = []
	for row in frappe.get_list(
		"Huf Data Table",
		fields=["table_name", "doctype_name", "description"],
		limit_page_length=200,
		order_by="modified desc",
	):
		doctype = row.get("doctype_name")
		if not doctype or not frappe.has_permission(doctype, "read"):
			continue
		haystack = f"{row.get('table_name') or ''} {row.get('description') or ''}".lower()
		if query and not any(t in haystack for t in query.split()):
			continue
		fields = [
			{"fieldname": df.fieldname, "label": df.label, "fieldtype": df.fieldtype}
			for df in frappe.get_meta(doctype).fields
			if df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "HTML", "Button")
		]
		tables.append(
			{
				"table": row.get("table_name"),
				"doctype": doctype,
				"description": (row.get("description") or "")[:200],
				"fields": fields,
			}
		)
		if len(tables) >= limit:
			break
	return {"tables": tables, "query": query}


# ---------------------------------------------------------------------------
# Writes (run only after an approval has been consumed)
# ---------------------------------------------------------------------------


def _pick(arguments: dict, keys: tuple[str, ...]) -> dict:
	return {k: arguments[k] for k in keys if k in arguments}


def _create_agent(arguments: dict) -> dict:
	from huf.ai.tools import builder

	draft = builder.draft_agent(
		confirm=True,
		**_pick(
			arguments,
			("agent_name", "provider", "model", "instructions", "description", "allow_chat"),
		),
	)
	result: dict[str, Any] = {"draft": draft}
	agent_name = draft.get("agent")
	if not agent_name:
		return result
	if arguments.get("tool_names"):
		result["tools"] = builder.attach_agent_tools(agent_name, arguments["tool_names"], confirm=True)
	if builder._as_bool(arguments.get("publish", True)):
		result["publish"] = builder.publish_agent(agent_name, confirm=True)
	return result


def _create_tool(arguments: dict) -> dict:
	from huf.ai.tools import builder

	return builder.create_agent_tool(
		confirm=True,
		**_pick(
			arguments,
			("tool_name", "description", "types", "reference_doctype", "tool_type", "parameters"),
		),
	)


def _create_table(arguments: dict) -> dict:
	from huf.ai.tools import builder

	return builder.create_huf_table(
		confirm=True,
		**_pick(
			arguments,
			("table_name", "fields", "description", "icon", "autoname_method", "title_field"),
		),
	)


def _build_app(arguments: dict) -> dict:
	from huf.ai.tools import builder

	action = str(arguments.get("action") or "create").lower()
	if action not in _APP_ACTIONS:
		frappe.throw("Unknown app action", frappe.ValidationError)
	app_id = arguments.get("app_id")
	if action == "create":
		return builder.draft_app(
			confirm=True,
			**_pick(arguments, ("app_id", "title", "agent_name", "description", "route", "category")),
		)
	if action == "update":
		fields = arguments.get("fields") or {}
		if not isinstance(fields, dict):
			frappe.throw("fields must be an object", frappe.ValidationError)
		return builder.update_app(app_id, confirm=True, **fields)
	return builder.install_app(app_id, confirm=True)


_HANDLERS = {
	"huf_find_agents": _find_agents,
	"huf_find_tools": _find_tools,
	"huf_find_tables": _find_tables,
	"huf_create_agent": _create_agent,
	"huf_create_tool": _create_tool,
	"huf_create_table": _create_table,
	"huf_build_app": _build_app,
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_hub(name: str, arguments: dict | None, session_doc, tier: str | None) -> dict:
	"""Run one hub capability for the authorised session.

	Returns ``{"status": "ok"|"error"|"denied"|"approval_required", ...}``. ``tier`` is the
	connection's hub tier (Off, Build or Admin); Off is always denied.
	"""
	spec = _HUB_TOOLS.get(name)
	if spec is None:
		return {"status": "error", "error": "Unknown hub tool"}
	is_write, minimum_tier, required_capability = spec

	if not _tier_allows(tier, minimum_tier):
		return _denied()

	arguments = dict(arguments) if isinstance(arguments, dict) else {}
	user = frappe.session.user

	try:
		if required_capability and not has_capability(user, required_capability):
			return _denied()

		if is_write:
			if not approvals.consume_approval(session_doc.name, name, arguments):
				approval = approvals.request_approval(session_doc.name, name, "write", arguments)
				return {"status": "approval_required", "approval": approval, "action_class": "write"}

		result = _HANDLERS[name](arguments)
		return {"status": "ok", "result": _clean(result)}
	except frappe.PermissionError:
		return _denied()
	except Exception:  # noqa: BLE001 - failures are logged, never leaked to the agent
		frappe.log_error(f"Hub action {name} failed", "External Hub")
		return {"status": "error", "error": FAILED_ERROR}
