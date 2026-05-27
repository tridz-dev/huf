import json
import frappe

MANAGER_ROLES = {"System Manager", "Huf Manager"}


def is_manager():
    return bool(set(frappe.get_roles(frappe.session.user)) & MANAGER_ROLES)


def json_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except Exception:
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False, default=str)


def resolved_key(scope_type, scope_key=None, conversation_id=None, agent_name=None):
    if scope_key:
        return scope_key
    return {"Conversation": conversation_id, "User": frappe.session.user, "Agent": agent_name, "Site": frappe.local.site, "Global": "global"}.get(scope_type)


def can_read(row, conversation_id=None, agent_name=None):
    if is_manager():
        return True
    get = row.get if isinstance(row, dict) else lambda k, d=None: getattr(row, k, d)
    scope_type = get("scope_type")
    scope_key = get("scope_key")
    visibility = get("visibility") or "Private"
    if scope_type == "Conversation":
        return conversation_id and scope_key == conversation_id
    if scope_type == "User":
        return scope_key == frappe.session.user
    if scope_type == "Role":
        return visibility == "Shared with Role" and scope_key in frappe.get_roles(frappe.session.user)
    if scope_type == "Agent":
        return agent_name and scope_key == agent_name and visibility in {"Private", "Shared with Agent"}
    if scope_type == "Site":
        return visibility == "Site" and scope_key == frappe.local.site
    if scope_type == "Global":
        return visibility == "Global" and scope_key == "global"
    return False


def can_write(scope_type, scope_key=None, agent_name=None):
    if is_manager():
        return True
    if scope_type in {"Role", "Workspace", "Site", "Global"}:
        return False
    if scope_type == "User":
        return scope_key == frappe.session.user
    if scope_type == "Agent":
        return agent_name and scope_key == agent_name
    if scope_type == "Conversation":
        return True
    return False


@frappe.whitelist()
def save_memory_record(title, summary_text, record_type="Fact", scope_type="Conversation", scope_key=None, data_json=None, status="Draft", visibility="Private", tags=None, confidence=0, importance_score=0, source_type="Manual", conversation_id=None, agent_run_id=None, agent_name=None, promote_to_knowledge=False, knowledge_source=None, raw_context_excerpt=None, **kwargs):
    key = resolved_key(scope_type, scope_key, conversation_id, agent_name)
    if not key or not can_write(scope_type, key, agent_name):
        frappe.throw("Memory write blocked")
    if promote_to_knowledge and not is_manager():
        frappe.throw("Knowledge promotion blocked")
    tag_text = ", ".join(tags) if isinstance(tags, list) else (tags or "")
    doc = frappe.get_doc({"doctype": "Memory Record", "title": title, "summary_text": summary_text, "record_type": record_type, "scope_type": scope_type, "scope_key": key, "status": status, "visibility": visibility, "tags": tag_text, "confidence": float(confidence or 0), "importance_score": float(importance_score or 0), "source_type": source_type, "conversation": conversation_id if scope_type == "Conversation" else None, "run": agent_run_id, "agent": agent_name, "data_json": json_value(data_json), "raw_context_excerpt": raw_context_excerpt, "promote_to_knowledge": 1 if promote_to_knowledge else 0, "knowledge_source": knowledge_source})
    doc.insert()
    if promote_to_knowledge and knowledge_source and doc.status == "Active":
        doc.queue_knowledge_projection()
    return {"success": True, "memory_record": doc.name, "status": doc.status, "scope_type": doc.scope_type, "scope_key": doc.scope_key, "projection_status": doc.projection_status}


@frappe.whitelist()
def get_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not can_read(doc, conversation_id, agent_name):
        frappe.throw("Memory read blocked")
    return doc.as_dict()


@frappe.whitelist()
def search_memory_records(query=None, record_type=None, scope_type=None, status="Active", limit=10, conversation_id=None, agent_name=None, **kwargs):
    scopes = []
    if conversation_id:
        scopes.append({"scope_type": "Conversation", "scope_key": conversation_id})
    if frappe.session.user != "Guest":
        scopes.append({"scope_type": "User", "scope_key": frappe.session.user})
        scopes += [{"scope_type": "Role", "scope_key": r} for r in frappe.get_roles(frappe.session.user)]
    if agent_name:
        scopes.append({"scope_type": "Agent", "scope_key": agent_name})
    scopes += [{"scope_type": "Site", "scope_key": frappe.local.site}, {"scope_type": "Global", "scope_key": "global"}]
    if scope_type:
        scopes = [s for s in scopes if s["scope_type"] == scope_type]
    results, seen, max_rows = [], set(), min(int(limit or 10), 50)
    base = {"status": status} if status else {}
    if record_type:
        base["record_type"] = record_type
    for scope in scopes:
        filters = dict(base)
        filters.update(scope)
        rows = frappe.get_all("Memory Record", filters=filters, fields=["name", "title", "record_type", "scope_type", "scope_key", "visibility", "status", "summary_text", "confidence", "importance_score", "tags", "agent", "conversation", "knowledge_source", "projection_status", "modified"], order_by="importance_score desc, modified desc", limit_page_length=max_rows)
        for row in rows:
            text = " ".join(str(row.get(f) or "") for f in ["title", "summary_text", "record_type", "tags"])
            if row.name in seen or (query and query.lower() not in text.lower()) or not can_read(row, conversation_id, agent_name):
                continue
            seen.add(row.name)
            results.append(row)
            if len(results) >= max_rows:
                return {"success": True, "results": results}
    return {"success": True, "results": results}


@frappe.whitelist()
def archive_memory_record(memory_record, conversation_id=None, agent_name=None, **kwargs):
    doc = frappe.get_doc("Memory Record", memory_record)
    if not can_write(doc.scope_type, doc.scope_key, agent_name) or not can_read(doc, conversation_id, agent_name):
        frappe.throw("Memory archive blocked")
    doc.status = "Archived"
    doc.save()
    return {"success": True, "memory_record": doc.name, "status": doc.status}


@frappe.whitelist()
def promote_memory_to_knowledge(memory_record, knowledge_source=None, **kwargs):
    if not is_manager():
        frappe.throw("Knowledge promotion blocked")
    doc = frappe.get_doc("Memory Record", memory_record)
    if knowledge_source:
        doc.knowledge_source = knowledge_source
    doc.promote_to_knowledge = 1
    if doc.status != "Active":
        doc.status = "Active"
    doc.save()
    return doc.queue_knowledge_projection()


handle_save_memory_record = save_memory_record
handle_get_memory_record = get_memory_record
handle_search_memory_records = search_memory_records
handle_archive_memory_record = archive_memory_record
handle_promote_memory_to_knowledge = promote_memory_to_knowledge
