import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now


WRITE_SCOPES_REQUIRING_MANAGER = {"Role", "Workspace", "Site", "Global"}


def _as_json_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, default=str)


def _split_tags(tags: str | list[str] | None) -> list[str]:
    if not tags:
        return []
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag).strip()]
    return [tag.strip() for tag in str(tags).replace("\n", ",").split(",") if tag.strip()]


def _has_memory_manager_permission() -> bool:
    return frappe.has_role("System Manager") or frappe.has_role("Huf Manager")


def _resolve_scope_key(scope_type: str, scope_key: str | None = None, *, conversation_id=None, agent_name=None):
    if scope_key:
        return scope_key
    if scope_type == "Conversation":
        return conversation_id
    if scope_type == "User":
        return frappe.session.user
    if scope_type == "Agent":
        return agent_name
    if scope_type == "Site":
        return frappe.local.site
    if scope_type == "Global":
        return "global"
    return scope_key


def _ensure_write_allowed(scope_type: str, scope_key: str | None = None, agent_name: str | None = None):
    if _has_memory_manager_permission():
        return

    if scope_type in WRITE_SCOPES_REQUIRING_MANAGER:
        frappe.throw(_("Only HUF managers can write {0}-scoped memory").format(scope_type))

    if scope_type == "User" and scope_key and scope_key != frappe.session.user:
        frappe.throw(_("Users can only write their own user-scoped memory"))

    if scope_type == "Agent" and scope_key and agent_name and scope_key != agent_name:
        frappe.throw(_("Agent-scoped memory can only be written for the active agent"))


def _read_scope_filters(agent_name: str | None = None, conversation_id: str | None = None) -> list[dict]:
    filters = []

    if conversation_id:
        filters.append({"scope_type": "Conversation", "scope_key": conversation_id})

    if frappe.session.user and frappe.session.user != "Guest":
        filters.append({"scope_type": "User", "scope_key": frappe.session.user})

        for role in frappe.get_roles(frappe.session.user):
            filters.append({"scope_type": "Role", "scope_key": role})

    if agent_name:
        filters.append({"scope_type": "Agent", "scope_key": agent_name})

    filters.append({"scope_type": "Site", "scope_key": frappe.local.site})
    filters.append({"scope_type": "Global", "scope_key": "global"})
    return filters


def _matches_text(doc: dict, query: str | None) -> bool:
    if not query:
        return True
    haystack = " ".join(str(doc.get(field) or "") for field in ["title", "summary_text", "record_type", "tags"])
    return query.lower() in haystack.lower()


@frappe.whitelist()
def save_memory_record(
    title: str,
    summary_text: str,
    record_type: str = "Fact",
    scope_type: str = "Conversation",
    scope_key: str | None = None,
    data_json: Any = None,
    status: str = "Draft",
    visibility: str = "Private",
    tags: str | list[str] | None = None,
    confidence: float = 0,
    importance_score: float = 0,
    source_type: str = "Manual",
    conversation_id: str | None = None,
    agent_run_id: str | None = None,
    agent_name: str | None = None,
    promote_to_knowledge: bool = False,
    knowledge_source: str | None = None,
    raw_context_excerpt: str | None = None,
    **kwargs,
):
    """Create a scoped Memory Record.

    Defaults to Conversation scope when called from an agent run. Wider scopes are
    manager-gated to avoid accidental cross-user/site memory writes.
    """
    scope_key = _resolve_scope_key(scope_type, scope_key, conversation_id=conversation_id, agent_name=agent_name)
    _ensure_write_allowed(scope_type, scope_key, agent_name=agent_name)

    if not scope_key:
        frappe.throw(_("Scope Key could not be resolved"))

    doc = frappe.get_doc(
        {
            "doctype": "Memory Record",
            "title": title,
            "summary_text": summary_text,
            "record_type": record_type,
            "scope_type": scope_type,
            "scope_key": scope_key,
            "status": status,
            "visibility": visibility,
            "tags": ", ".join(_split_tags(tags)),
            "confidence": float(confidence or 0),
            "importance_score": float(importance_score or 0),
            "source_type": source_type,
            "conversation": conversation_id if scope_type == "Conversation" and conversation_id else None,
            "run": agent_run_id,
            "agent": agent_name,
            "data_json": _as_json_string(data_json),
            "raw_context_excerpt": raw_context_excerpt,
            "promote_to_knowledge": 1 if promote_to_knowledge else 0,
            "knowledge_source": knowledge_source,
        }
    )
    doc.insert(ignore_permissions=False)

    if promote_to_knowledge and knowledge_source and doc.status == "Active":
        doc.queue_knowledge_projection()

    return {
        "success": True,
        "memory_record": doc.name,
        "status": doc.status,
        "scope_type": doc.scope_type,
        "scope_key": doc.scope_key,
        "projection_status": doc.projection_status,
    }


@frappe.whitelist()
def get_memory_record(memory_record: str, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not frappe.has_permission("Memory Record", "read", doc.name):
        frappe.throw(_("Not permitted to read Memory Record {0}").format(doc.name))
    return doc.as_dict()


@frappe.whitelist()
def search_memory_records(
    query: str | None = None,
    record_type: str | None = None,
    scope_type: str | None = None,
    status: str = "Active",
    limit: int = 10,
    conversation_id: str | None = None,
    agent_name: str | None = None,
    **kwargs,
):
    """Search readable scoped Memory Records using DocType filters.

    This intentionally starts with simple canonical-record search. FTS/vector
    retrieval should be provided by the optional Knowledge Projection path.
    """
    limit = min(int(limit or 10), 50)
    allowed_scopes = _read_scope_filters(agent_name=agent_name, conversation_id=conversation_id)

    results = []
    seen = set()

    base_filters = {"status": status} if status else {}
    if record_type:
        base_filters["record_type"] = record_type
    if scope_type:
        allowed_scopes = [scope for scope in allowed_scopes if scope["scope_type"] == scope_type]

    for scope_filter in allowed_scopes:
        filters = dict(base_filters)
        filters.update(scope_filter)
        rows = frappe.get_list(
            "Memory Record",
            filters=filters,
            fields=[
                "name",
                "title",
                "record_type",
                "scope_type",
                "scope_key",
                "status",
                "summary_text",
                "confidence",
                "importance_score",
                "tags",
                "agent",
                "conversation",
                "knowledge_source",
                "projection_status",
                "modified",
            ],
            order_by="importance_score desc, modified desc",
            limit_page_length=limit,
        )

        for row in rows:
            if row.name in seen or not _matches_text(row, query):
                continue
            seen.add(row.name)
            results.append(row)
            if len(results) >= limit:
                return {"success": True, "results": results}

    return {"success": True, "results": results}


@frappe.whitelist()
def archive_memory_record(memory_record: str, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    _ensure_write_allowed(doc.scope_type, doc.scope_key, agent_name=kwargs.get("agent_name"))
    doc.status = "Archived"
    doc.save(ignore_permissions=False)
    return {"success": True, "memory_record": doc.name, "status": doc.status}


@frappe.whitelist()
def promote_memory_to_knowledge(memory_record: str, knowledge_source: str | None = None, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    _ensure_write_allowed(doc.scope_type, doc.scope_key, agent_name=kwargs.get("agent_name"))

    if knowledge_source:
        doc.knowledge_source = knowledge_source
    doc.promote_to_knowledge = 1
    if doc.status != "Active":
        doc.status = "Active"
    doc.save(ignore_permissions=False)
    return doc.queue_knowledge_projection()


# Agent SDK handler aliases
handle_save_memory_record = save_memory_record
handle_get_memory_record = get_memory_record
handle_search_memory_records = search_memory_records
handle_archive_memory_record = archive_memory_record
handle_promote_memory_to_knowledge = promote_memory_to_knowledge
