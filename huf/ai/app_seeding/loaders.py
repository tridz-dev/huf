import json

import frappe

from huf.ai.prompts.lineage import find_seed_target

# Seed-owned fields = every key in the seed payload except provenance/meta.
# `seed_snapshot` (hidden JSON on the doc) records the values last written by
# the seeder; a field whose current value differs from its snapshot was edited
# by an admin and is not overwritten on re-seed. Docs without a snapshot
# (first adoption) take the seed values.
_SEED_META_KEYS = {"source_app", "source_file", "doctype", "name", "seed_snapshot"}


def _norm(value):
    if isinstance(value, list):
        return [dict(r) if isinstance(r, dict) else r for r in value]
    return value


def _seed_values(data: dict) -> dict:
    return {k: _norm(v) for k, v in data.items() if k not in _SEED_META_KEYS}


def _current(doc, key, seeded):
    cur = doc.get(key)
    if isinstance(seeded, list):
        rows = []
        for i, srow in enumerate(seeded):
            row = cur[i] if i < len(cur or []) else None
            if row is None:
                return None
            rows.append({k: row.get(k) for k in srow})
        return rows if len(cur or []) == len(seeded) else None
    return cur


# Only-tighten security fields: a re-seed (or first adoption of an existing doc) may never
# loosen them. value = the tight value for Check fields.
_TIGHT_CHECKS = {"requires_confirmation": 1, "is_outbound": 1, "allowed_for_guest": 0}
_ROLE_TEXT_FIELDS = ("required_roles",)
_ROLE_TABLE_FIELDS = ("allowed_roles",)


def _split_roles(raw) -> list:
    return [r.strip() for r in str(raw or "").replace("\n", ",").split(",") if r.strip()]


def _table_roles(rows) -> list:
    out = []
    for r in rows or []:
        name = r.get("role") if hasattr(r, "get") else r
        if name and name not in out:
            out.append(name)
    return out


def _snapshot_security(doc) -> dict:
    snap = {}
    for k in _TIGHT_CHECKS:
        if doc.meta.has_field(k):
            snap[k] = int(doc.get(k) or 0)
    for k in _ROLE_TEXT_FIELDS:
        if doc.meta.has_field(k):
            snap[k] = _split_roles(doc.get(k))
    for k in _ROLE_TABLE_FIELDS:
        if doc.meta.has_field(k):
            snap[k] = _table_roles(doc.get(k))
    return snap


def _enforce_only_tighten(doc, before: dict, data: dict) -> list:
    """Restore the stricter of existing/seed for security fields. Returns warning strings."""
    warnings = []
    label = f"{doc.doctype} {doc.name}"
    for k, tight in _TIGHT_CHECKS.items():
        if k not in before or k not in data:
            continue
        old, new = before[k], int(doc.get(k) or 0)
        if old == tight and new != tight:
            doc.set(k, old)
            warnings.append(f"{label}: ignored seed loosening of {k} ({old} -> {new})")
    for k in _ROLE_TEXT_FIELDS + _ROLE_TABLE_FIELDS:
        if k not in before or k not in data:
            continue
        existing = before[k]
        if not existing:
            continue  # unrestricted so far: the seed list applies as-is (it tightens)
        is_table = k in _ROLE_TABLE_FIELDS
        seeded = _table_roles(doc.get(k)) if is_table else _split_roles(doc.get(k))
        final = [r for r in existing if r in seeded]
        if not final:
            final = list(existing)
            warnings.append(f"{label}: ignored seed {k} {seeded} (no overlap with existing {existing}); kept existing")
        elif set(seeded) - set(existing):
            warnings.append(f"{label}: ignored seed additions to {k} {sorted(set(seeded) - set(existing))}")
        if final != seeded:
            doc.set(k, [{"role": r} for r in final] if is_table else ", ".join(final))
    for w in warnings:
        frappe.logger("huf").warning("[app_seeding] %s", w)
    return warnings


def _apply_seed_preserving_edits(doc, data: dict) -> list:
    """Apply seed values; returns warnings about ignored security-loosening changes."""
    before = _snapshot_security(doc)
    new = _seed_values(data)
    try:
        old = json.loads(doc.get("seed_snapshot") or "null")
    except ValueError:
        old = None
    for key, value in new.items():
        if old is not None and key in old:
            cur = _current(doc, key, old[key])
            if cur != old[key]:
                continue  # admin edited this field since last seed: keep it
        doc.set(key, data[key])
    doc.source_app = data.get("source_app")
    doc.source_file = data.get("source_file")
    warnings = _enforce_only_tighten(doc, before, data)
    doc.seed_snapshot = json.dumps(new)
    return warnings


def _validate_row_link_refs(child_doctype: str, row: dict, row_index: int) -> list:
    """Validate Link and Dynamic Link fields in a single child table row."""
    missing = []
    child_meta = frappe.get_meta(child_doctype)

    for field in child_meta.get_link_fields():
        value = row.get(field.fieldname)
        if not value:
            continue
        target_doctype = field.options
        if not frappe.db.exists(target_doctype, value):
            missing.append(f"{child_doctype}[{row_index}].{target_doctype}:{value}")

    for field in child_meta.get_dynamic_link_fields():
        value = row.get(field.fieldname)
        if not value:
            continue
        target_doctype = row.get(field.options)
        if not target_doctype:
            continue
        if not frappe.db.exists(target_doctype, value):
            missing.append(f"{child_doctype}[{row_index}].{target_doctype}:{value}")

    return missing


def _validate_link_refs(doctype: str, data: dict) -> list:
    """
    Validate that all Link-field values in `data` reference existing documents.

    Covers main-doc Link fields, child-table Link fields, Table MultiSelect
    fields, and Dynamic Link fields.

    Returns a flat list of missing reference strings:
      - Main doc Link: "<Target Doctype>:<missing name>"
      - Dynamic Link: "<Target Doctype>:<missing name>"
      - Child table / Table MultiSelect: "<Child Doctype>[<row_index>].<Target Doctype>:<missing name>"
    """
    missing = []

    meta = frappe.get_meta(doctype)

    # Main doc Link fields
    for field in meta.get_link_fields():
        value = data.get(field.fieldname)
        if not value:
            continue
        target_doctype = field.options
        if not frappe.db.exists(target_doctype, value):
            missing.append(f"{target_doctype}:{value}")

    # Main doc Dynamic Link fields
    for field in meta.get_dynamic_link_fields():
        value = data.get(field.fieldname)
        if not value:
            continue
        target_doctype = data.get(field.options)
        if not target_doctype:
            continue
        if not frappe.db.exists(target_doctype, value):
            missing.append(f"{target_doctype}:{value}")

    # Standard child table Link and Dynamic Link fields
    for table_field in meta.get_table_fields():
        rows = data.get(table_field.fieldname)
        if not isinstance(rows, list):
            continue
        child_doctype = table_field.options
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            missing.extend(_validate_row_link_refs(child_doctype, row, row_index))

    # Table MultiSelect fields
    for field in meta.fields:
        if field.fieldtype != "Table MultiSelect":
            continue
        rows = data.get(field.fieldname)
        if not isinstance(rows, list):
            continue
        child_doctype = field.options
        child_meta = frappe.get_meta(child_doctype)
        link_fields = child_meta.get_link_fields()
        if not link_fields:
            continue
        for row_index, row in enumerate(rows):
            if isinstance(row, str):
                row = {link_fields[0].fieldname: row}
            if not isinstance(row, dict):
                continue
            missing.extend(_validate_row_link_refs(child_doctype, row, row_index))

    return missing


def _upsert_doc(doctype: str, key_field: str, data: dict, source_app: str, source_file: str) -> tuple:
    """
    Generic upsert for a seed document.
    """
    key_val = data.get(key_field)
    if not key_val:
        return False, f"Missing {key_field}"

    missing_refs = _validate_link_refs(doctype, data)
    if missing_refs:
        return False, {"reason": "missing_refs", "missing_refs": missing_refs}

    docname = find_seed_target(doctype, key_field, key_val)

    # Add provenance fields
    data["source_app"] = source_app
    data["source_file"] = source_file

    warnings = []
    try:
        tracks = bool(frappe.get_meta(doctype).get_field("seed_snapshot"))
        if docname:
            doc = frappe.get_doc(doctype, docname)
            if tracks:
                warnings = _apply_seed_preserving_edits(doc, data)
            else:
                doc.update(data)
            doc.save(ignore_permissions=True)
        else:
            data["doctype"] = doctype
            doc = frappe.get_doc(data)
            if tracks:
                doc.seed_snapshot = json.dumps(_seed_values(data))
            doc.insert(ignore_permissions=True)
        return True, ({"warnings": warnings} if warnings else None)
    except Exception as e:
        return False, str(e)

def upsert_agent(data: dict, source_app: str, source_file: str) -> tuple:
    data = data.copy()
    # `is_system` is intentionally a pass-through field so seed files can
    # mark reserved agents; _upsert_doc will preserve it via doc.update().
    if "tools" in data and isinstance(data["tools"], list):
        data["agent_tool"] = [{"tool": t} for t in data["tools"]]
        del data["tools"]
    if "knowledge" in data and isinstance(data["knowledge"], list):
        data["agent_knowledge"] = [{"knowledge_source": k} for k in data["knowledge"]]
        del data["knowledge"]
    return _upsert_doc("Agent", "agent_name", data, source_app, source_file)

VALID_TYPES = [
    "Get Document", "Get Multiple Documents", "Get List", "Create Document",
    "Create Multiple Documents", "Update Document", "Update Multiple Documents",
    "Delete Document", "Delete Multiple Documents", "Submit Document",
    "Cancel Document", "Get Amended Document", "Custom Function", "App Provided",
    "Attach File to Document", "Get Report Result", "Get Value", "Set Value",
    "GET", "POST", "Run Agent", "Client Side Tool", "Get Conversation Data",
    "Set Conversation Data", "Load Conversation Data", "Perplexity Search"
]

def upsert_tool(data: dict, source_app: str, source_file: str) -> tuple:
    data = data.copy()
    from huf.huf.doctype.agent_tool_function.agent_tool_function import is_otp_tool_path

    if is_otp_tool_path(data.get("function_path")):
        return False, "OTP functions cannot be seeded as agent tools"
    if data.get("types") not in VALID_TYPES:
        data["types"] = "App Provided"
        
    # Agent Tool Function.tool_type is mandatory; external apps rarely know the category taxonomy.
    tool_type = data.get("tool_type") or "Miscellaneous"
    data["tool_type"] = tool_type
    if not frappe.db.exists("Agent Tool Type", tool_type):
        try:
            frappe.get_doc({
                "doctype": "Agent Tool Type",
                "name1": tool_type
            }).insert(ignore_permissions=True)
        except Exception as e:
            return False, f"Failed to create Agent Tool Type '{tool_type}': {str(e)}"
            
    return _upsert_doc("Agent Tool Function", "tool_name", data, source_app, source_file)

def upsert_prompt(data: dict, source_app: str, source_file: str) -> tuple:
    # Prompt key is usually 'title'
    return _upsert_doc("Agent Prompt", "title", data, source_app, source_file)

def upsert_knowledge(data: dict, source_app: str, source_file: str) -> tuple:
    data = data.copy()
    # Map legacy/documentation storage_modes to the current schema
    if data.get("storage_mode") == "SQLite (FTS)":
        data["storage_mode"] = "Frappe File"
        data["knowledge_type"] = "sqlite_fts"
    elif data.get("storage_mode") == "SQLite (Vector)":
        data["storage_mode"] = "Frappe File"
        data["knowledge_type"] = "sqlite_vec"
    
    if not data.get("knowledge_type"):
        data["knowledge_type"] = "sqlite_fts"
        
    return _upsert_doc("Knowledge Source", "source_name", data, source_app, source_file)

def upsert_trigger(data: dict, source_app: str, source_file: str) -> tuple:
    return _upsert_doc("Agent Trigger", "trigger_name", data, source_app, source_file)


def upsert_event_alias(data: dict, source_app: str, source_file: str) -> tuple:
    """Seed an Event Alias. Name is `{app}.{key}`; admin edits survive re-seed (snapshot semantics)."""
    data = data.copy()
    if not data.get("app") or not data.get("key"):
        return False, "Missing app or key"
    data["name"] = f"{data['app']}.{data['key']}"
    return _upsert_doc("Event Alias", "name", data, source_app, source_file)
