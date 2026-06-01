import json

import frappe
from frappe import _

MANAGER_ROLES = {"System Manager", "Huf Manager"}
WRITE_BLOCKED_SCOPES_FOR_NON_MANAGER = {"Role", "Workspace", "Site", "Global"}


def _is_manager() -> bool:
    return bool(set(frappe.get_roles(frappe.session.user)) & MANAGER_ROLES)


def _json_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, default=str)


def _resolve_scope_key(scope_type, provided_scope_key=None, conversation_id=None, agent_name=None):
    if provided_scope_key:
        return provided_scope_key
    return {
        "Conversation": conversation_id,
        "User": frappe.session.user,
        "Agent": agent_name,
        "Site": frappe.local.site,
        "Global": "global",
    }.get(scope_type)


def _can_read_memory(row, conversation_id=None, agent_name=None) -> bool:
    if _is_manager():
        return True

    if frappe.session.user == "Guest":
        return False

    getter = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)
    row_scope_type = getter("scope_type")
    row_scope_key = getter("scope_key")
    row_visibility = getter("visibility") or "Private"

    if row_scope_type == "Conversation":
        return bool(conversation_id and row_scope_key == conversation_id)
    if row_scope_type == "User":
        return row_scope_key == frappe.session.user
    if row_scope_type == "Role":
        return row_visibility == "Shared with Role" and row_scope_key in frappe.get_roles(frappe.session.user)
    if row_scope_type == "Agent":
        return bool(agent_name and row_scope_key == agent_name and row_visibility in {"Private", "Shared with Agent"})
    if row_scope_type == "Site":
        return row_visibility == "Site" and row_scope_key == frappe.local.site
    if row_scope_type == "Global":
        return row_visibility == "Global" and row_scope_key == "global"
    return False


def _can_write_memory(scope_type, scope_key_value=None, agent_name=None) -> bool:
    if _is_manager():
        return True
    if frappe.session.user == "Guest":
        return False
    if scope_type in WRITE_BLOCKED_SCOPES_FOR_NON_MANAGER:
        return False
    if scope_type == "User":
        return scope_key_value == frappe.session.user
    if scope_type == "Agent":
        return bool(agent_name and scope_key_value == agent_name)
    if scope_type == "Conversation":
        return True
    return False


@frappe.whitelist()
def save_memory_record(
    title,
    summary_text,
    record_type="Fact",
    scope_type="Conversation",
    scope_key=None,
    data_json=None,
    status="Draft",
    visibility="Private",
    tags=None,
    confidence=0,
    importance_score=0,
    source_type="Manual",
    conversation_id=None,
    agent_run_id=None,
    agent_name=None,
    promote_to_knowledge=False,
    knowledge_source=None,
    raw_context_excerpt=None,
    **kwargs,
):
    if conversation_id and not scope_type:
        scope_type = "Conversation"

    resolved_scope_key = _resolve_scope_key(scope_type, scope_key, conversation_id, agent_name)
    if not resolved_scope_key or not _can_write_memory(scope_type, resolved_scope_key, agent_name):
        frappe.throw(_("Memory write blocked"))

    if promote_to_knowledge and not _is_manager():
        frappe.throw(_("Knowledge promotion blocked"))

    # Apply Memory Policy rules if Agent has a policy
    if agent_name:
        agent_policy = frappe.db.get_value("Agent", agent_name, "memory_policy")
        if agent_policy:
            policy = frappe.get_doc("Memory Policy", agent_policy)
            
            # Record type validation
            if policy.allowed_record_types:
                allowed = [t.strip() for t in policy.allowed_record_types.split("\n") if t.strip()]
                if allowed and record_type not in allowed:
                    frappe.throw(_("Record type {0} is not allowed by policy {1}").format(record_type, policy.name))
                    
            # Status override
            if policy.approval_required:
                status = "Draft"
            elif status == "Draft" and policy.default_status == "Active":
                status = "Active"
                
            # Auto-promote
            if policy.auto_promote_to_knowledge and not promote_to_knowledge:
                if float(confidence or 0) >= policy.promotion_min_confidence and float(importance_score or 0) >= policy.promotion_min_importance:
                    promote_to_knowledge = True
                    if not knowledge_source:
                        knowledge_source = policy.knowledge_source

    tag_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
    doc = frappe.get_doc(
        {
            "doctype": "Memory Record",
            "title": title,
            "summary_text": summary_text,
            "record_type": record_type,
            "scope_type": scope_type,
            "scope_key": resolved_scope_key,
            "status": status,
            "visibility": visibility,
            "tags": tag_text,
            "confidence": float(confidence or 0),
            "importance_score": float(importance_score or 0),
            "source_type": source_type,
            "conversation": conversation_id if scope_type == "Conversation" else None,
            "run": agent_run_id,
            "agent": agent_name,
            "data_json": _json_value(data_json),
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


def get_injected_memory_text(agent_name, policy, conversation_id=None):
    """Fetch memories to inject into system prompt based on policy."""
    if not policy or policy.inject_mode != "Always":
        return None
        
    limit = policy.max_records or 5
    budget = policy.token_budget or 1000
    
    # Use search to get active memories the agent is allowed to read
    # We query with no keyword so it just gets recent/important ones
    res = search_memory_records(
        query=None,
        status="Active",
        limit=limit * 2, # Fetch more in case we hit token limits
        conversation_id=conversation_id,
        agent_name=agent_name
    )
    
    if not res.get("success") or not res.get("results"):
        return None
        
    # Build text up to token budget (rough estimate: 1 word ~ 1.3 tokens)
    lines = []
    current_words = 0
    max_words = int(budget / 1.3)
    
    for row in res.get("results", []):
        if len(lines) >= limit:
            break
            
        line = f"[{row.get('record_type')} - {row.get('title')}] {row.get('summary_text')}"
        words_in_line = len(line.split())
        
        if current_words + words_in_line > max_words:
            break
            
        lines.append(line)
        current_words += words_in_line
        
    if lines:
        return "\n".join(lines)
    return None


@frappe.whitelist()
def get_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not _can_read_memory(doc, conversation_id, agent_name):
        frappe.throw(_("Memory read blocked"))
    return doc.as_dict()


@frappe.whitelist()
def search_memory_records(query=None, record_type=None, scope_type=None, status="Active", limit=10, conversation_id=None, agent_name=None, **kwargs):
    max_rows = min(max(int(limit or 10), 1), 50)
    filters = {}
    if status:
        filters["status"] = status
    if record_type:
        filters["record_type"] = record_type
    if scope_type:
        filters["scope_type"] = scope_type

    rows = frappe.get_all(
        "Memory Record",
        filters=filters,
        fields=["name", "title", "record_type", "scope_type", "scope_key", "visibility", "status", "summary_text", "confidence", "importance_score", "tags", "agent", "conversation", "knowledge_source", "projection_status", "modified"],
        order_by="importance_score desc, modified desc",
        limit_page_length=max_rows * 4,
    )

    query_lower = (query or "").strip().lower()
    results = []
    for row in rows:
        if not _can_read_memory(row, conversation_id, agent_name):
            continue
        haystack = " ".join(str(row.get(field) or "") for field in ["title", "summary_text", "record_type", "tags"]).lower()
        if query_lower and query_lower not in haystack:
            continue
        results.append(row)
        if len(results) >= max_rows:
            break

    return {"success": True, "results": results}


@frappe.whitelist()
def archive_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not _can_read_memory(doc, conversation_id, agent_name):
        frappe.throw(_("Memory archive blocked"))
    if not _can_write_memory(doc.scope_type, doc.scope_key, agent_name):
        frappe.throw(_("Memory archive blocked"))
    doc.status = "Archived"
    doc.save(ignore_permissions=False)
    return {"success": True, "memory_record": doc.name, "status": doc.status}


@frappe.whitelist()
def promote_memory_to_knowledge(memory_record, knowledge_source=None, **kwargs):
    if not _is_manager():
        frappe.throw(_("Knowledge promotion blocked"))

    doc = frappe.get_doc("Memory Record", memory_record)
    if knowledge_source:
        doc.knowledge_source = knowledge_source
    doc.promote_to_knowledge = 1
    if doc.status != "Active":
        doc.status = "Active"
    doc.save(ignore_permissions=False)
    return doc.queue_knowledge_projection()


handle_save_memory_record = save_memory_record
handle_get_memory_record = get_memory_record
handle_search_memory_records = search_memory_records
handle_archive_memory_record = archive_memory_record
handle_promote_memory_to_knowledge = promote_memory_to_knowledge
