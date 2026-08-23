"""Lazy tool discovery handlers.

Lets an agent with a large tool surface discover tools on demand instead of
having every tool's schema loaded into context up front: list_tool_groups ->
describe_tool_group -> load_tools, or search_tools -> load_tools directly.
"""

import json

import frappe

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.conversation_data_tools import _load_state
from huf.ai.graph.procedure_binding import (
    get_bound_procedures_for_agent,
    _tool_name_for as _procedure_tool_name,
)

logger = frappe.logger("huf")

# Bound Agent Procedures (T-31/T-34) are grouped separately from atomic tools -- they
# are not mixed into a "service"/provider_app group, they get their own named group so
# the model can tell "run one of these procedures" apart from "call this atomic tool."
PROCEDURE_GROUP_NAME = "Procedures"


def _resolve_agent_doc(kwargs):
    """Resolve the calling Agent doc the same way sdk_tools handlers do: via the
    ``agent_name`` injected into kwargs from the huf run context."""
    agent_name = kwargs.get("agent_name")
    if not agent_name:
        return None
    try:
        return frappe.get_cached_doc("Agent", agent_name)
    except (frappe.DoesNotExistError, frappe.ValidationError):
        return None


def _tool_group(tool_doc) -> str:
    return tool_doc.service or tool_doc.provider_app or "General"


def _summarize(description: str) -> str:
    if not description:
        return ""
    period_idx = description.find(". ")
    if period_idx != -1:
        return description[:period_idx + 1].strip()
    return description[:120].strip()


def _bound_procedures(agent):
    """Re-resolve the calling agent's bound procedures at read time.

    Always goes through ``get_bound_procedures_for_agent`` -- which itself re-checks
    ``is_read_only`` (I8) and re-applies the per-agent cap on every call -- rather than
    caching or trusting anything computed earlier in the conversation. Discovery can
    never see (let alone unlock) a binding that a permission check would reject; there
    is no separate procedure "index" that could drift from that check (I1).
    """
    agent_name = getattr(agent, "name", None)
    return get_bound_procedures_for_agent(agent_name)


def _procedure_description(bound) -> str:
    return (
        f"Run the '{bound.procedure_name}' procedure (deterministic, read-only). "
        f"Bound via Agent Procedure Binding {bound.binding_name}."
    )


def _procedure_group_entry(agent):
    bound_procedures = _bound_procedures(agent)
    if not bound_procedures:
        return None

    summary = ""
    for bound in bound_procedures:
        summary = _procedure_description(bound)
        break

    return {
        "service": PROCEDURE_GROUP_NAME,
        "tool_count": len(bound_procedures),
        "summary": summary,
    }


def handle_list_tool_groups(**kwargs):
    """Group the calling agent's allowed tools by service (or provider_app/"General").

    Bound Agent Procedures (T-34) are advertised as one extra group,
    ``PROCEDURE_GROUP_NAME`` -- only the group name/summary/count, never the individual
    procedures' ``input_schema``, which is the entire point of lazy discovery: the full
    schema loads only via ``describe_tool_group``/``load_tools`` on demand.
    """
    agent = _resolve_agent_doc(kwargs)
    if not agent:
        return json.dumps([])

    allowed_tools = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)

    groups = {}
    order = []
    for tool_doc in allowed_tools:
        group = _tool_group(tool_doc)
        if group not in groups:
            groups[group] = []
            order.append(group)
        groups[group].append(tool_doc)

    result = []
    for group in order:
        tool_docs = groups[group]
        summary = ""
        for tool_doc in tool_docs:
            summary = _summarize(tool_doc.description)
            if summary:
                break
        result.append({
            "service": group,
            "tool_count": len(tool_docs),
            "summary": summary,
        })

    procedure_entry = _procedure_group_entry(agent)
    if procedure_entry:
        result.append(procedure_entry)

    return json.dumps(result)


def handle_search_tools(query, limit=10, **kwargs):
    """Search discoverable tools, filtered to what the calling agent is permitted to use."""
    agent = _resolve_agent_doc(kwargs)
    if not agent:
        return json.dumps([])

    limit = int(limit) if limit else 10

    allowed_tools = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)
    allowed_by_name = {tool_doc.tool_name: tool_doc for tool_doc in allowed_tools}

    # Call the underlying implementation directly, not the api.py wrapper —
    # that wrapper admin-gates capability discovery (it exposes raw app
    # manifests/function paths), but here results are already filtered down
    # to the calling agent's own allowed tools before anything is returned,
    # so the admin gate would just make this always return nothing for
    # ordinary agents.
    from huf.ai.capability_discovery.actions import search_app_actions

    seen_apps = set()
    matches = []
    for tool_doc in allowed_tools:
        app_name = tool_doc.provider_app
        if not app_name or app_name in seen_apps:
            continue
        seen_apps.add(app_name)

        try:
            descriptors = search_app_actions(app_name, query, limit)
        except (frappe.PermissionError, frappe.ValidationError, ValueError) as e:
            # search_app_actions is admin-gated; a non-admin caller simply gets no
            # results for that app rather than the whole discovery call failing.
            logger.debug(f"handle_search_tools: skipping app {app_name}: {e!s}")
            continue

        for descriptor in descriptors:
            tool_name = descriptor.get("title")
            allowed_tool_doc = allowed_by_name.get(tool_name)
            if not allowed_tool_doc:
                continue
            matches.append({
                "tool_name": tool_name,
                "service": _tool_group(allowed_tool_doc),
                "description": descriptor.get("description") or "",
            })
            if len(matches) >= limit:
                return json.dumps(matches[:limit])

    if len(matches) < limit:
        query_lower = (query or "").lower()
        for bound in _bound_procedures(agent):
            if len(matches) >= limit:
                break
            haystack = f"{bound.procedure_name} {bound.procedure_id}".lower()
            if query_lower and query_lower not in haystack:
                continue
            matches.append({
                "tool_name": _procedure_tool_name(bound),
                "service": PROCEDURE_GROUP_NAME,
                "description": _procedure_description(bound),
            })

    return json.dumps(matches[:limit])


def handle_describe_tool_group(service, **kwargs):
    """List every allowed tool whose service (or provider_app/"General" fallback) matches.

    ``service == PROCEDURE_GROUP_NAME`` is where a bound procedure's full
    ``input_schema`` first becomes visible to the caller (via a subsequent
    ``load_tools`` call) -- this is on-demand by design, never part of the initial
    ``list_tool_groups`` payload.
    """
    agent = _resolve_agent_doc(kwargs)
    if not agent:
        return json.dumps([])

    if service == PROCEDURE_GROUP_NAME:
        return json.dumps([
            {"tool_name": _procedure_tool_name(bound), "description": _procedure_description(bound)}
            for bound in _bound_procedures(agent)
        ])

    allowed_tools = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)

    result = [
        {"tool_name": tool_doc.tool_name, "description": tool_doc.description or ""}
        for tool_doc in allowed_tools
        if _tool_group(tool_doc) == service
    ]

    return json.dumps(result)


def _get_conversation_data(conversation_id):
    if not conversation_id:
        return {"version": 1, "scope": {}, "items": []}
    data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
    return _load_state(data_json)


def _set_conversation_data(conversation_id, state):
    frappe.db.set_value(
        "Agent Conversation", conversation_id, "conversation_data",
        json.dumps(state, ensure_ascii=False, indent=2),
    )


def _get_lazy_tools_item(state):
    """Find (or create) the "_lazy_tools" entry in the items list.

    conversation_data stores values as {"items": [{"name", "value", ...}]}
    (see handle_get_conversation_data / handle_set_conversation_data) rather
    than as top-level keys, so this must update an items-list entry to stay
    visible to that same reader (huf.ai.sdk_tools._get_lazy_discovered_tool_names).
    """
    for item in state["items"]:
        if item.get("name") == "_lazy_tools":
            item.setdefault("value", {})
            return item
    item = {"name": "_lazy_tools", "value": {}}
    state["items"].append(item)
    return item


def handle_load_tools(tool_names, **kwargs):
    """Grant the requesting conversation access to previously-discovered tools.

    Re-validates permissions here (rather than trusting the model's request)
    because this is the actual permission boundary: it is what decides which
    tools create_agent_tools() will build for later turns of this conversation.
    """
    agent = _resolve_agent_doc(kwargs)
    if not agent:
        return json.dumps({"accepted": [], "rejected": tool_names if isinstance(tool_names, list) else []})

    if isinstance(tool_names, str):
        try:
            tool_names = json.loads(tool_names)
        except (json.JSONDecodeError, TypeError):
            tool_names = [tool_names]
    if not isinstance(tool_names, list):
        tool_names = []

    allowed_tools = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)
    allowed_by_name = {tool_doc.tool_name: tool_doc for tool_doc in allowed_tools}
    # Re-resolved here too (I1) -- a procedure name the model asks to load is only ever
    # accepted if it is still a currently-bound, still-read-only procedure for this
    # agent, not because it appeared in some earlier discovery response.
    procedure_by_name = {_procedure_tool_name(bound): bound for bound in _bound_procedures(agent)}

    accepted_names = []
    rejected_names = []
    for name in tool_names:
        is_known = name in allowed_by_name or name in procedure_by_name
        if is_known and name not in accepted_names:
            accepted_names.append(name)
        elif not is_known:
            rejected_names.append(name)

    conversation_id = kwargs.get("conversation_id")
    if conversation_id and accepted_names:
        state = _get_conversation_data(conversation_id)
        item = _get_lazy_tools_item(state)
        discovered = item["value"].setdefault("discovered", [])
        for name in accepted_names:
            if name not in discovered:
                discovered.append(name)
        _set_conversation_data(conversation_id, state)

    accepted = []
    for name in accepted_names:
        if name in allowed_by_name:
            tool_doc = allowed_by_name[name]
            try:
                parameters = json.loads(tool_doc.params) if tool_doc.params else {}
            except (json.JSONDecodeError, TypeError):
                parameters = {}
            accepted.append({
                "tool_name": name,
                "description": tool_doc.description or "",
                "parameters": parameters,
            })
        else:
            bound = procedure_by_name[name]
            accepted.append({
                "tool_name": name,
                "description": _procedure_description(bound),
                "parameters": bound.input_schema,
            })

    return json.dumps({"accepted": accepted, "rejected": rejected_names})
