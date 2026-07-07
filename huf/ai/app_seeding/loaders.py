import frappe


def _validate_link_refs(doctype: str, data: dict) -> list:
    """
    Validate that all Link-field values in `data` reference existing documents.

    Returns a flat list of missing reference strings:
      - Main doc: "<Target Doctype>:<missing name>"
      - Child table: "<Child Doctype>[<row_index>].<Target Doctype>:<missing name>"
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

    # Child table Link fields
    for table_field in meta.get_table_fields():
        rows = data.get(table_field.fieldname)
        if not isinstance(rows, list):
            continue
        child_doctype = table_field.options
        child_meta = frappe.get_meta(child_doctype)
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            for field in child_meta.get_link_fields():
                value = row.get(field.fieldname)
                if not value:
                    continue
                target_doctype = field.options
                if not frappe.db.exists(target_doctype, value):
                    missing.append(
                        f"{child_doctype}[{row_index}].{target_doctype}:{value}"
                    )

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
        return False, "Missing reference(s): " + ", ".join(missing_refs)

    docname = frappe.db.get_value(doctype, {key_field: key_val})

    # Add provenance fields
    data["source_app"] = source_app
    data["source_file"] = source_file

    try:
        if docname:
            doc = frappe.get_doc(doctype, docname)
            doc.update(data)
            doc.save(ignore_permissions=True)
        else:
            data["doctype"] = doctype
            frappe.get_doc(data).insert(ignore_permissions=True)
        return True, None
    except Exception as e:
        return False, str(e)

def upsert_agent(data: dict, source_app: str, source_file: str) -> tuple:
    data = data.copy()
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
    "Set Conversation Data", "Load Conversation Data"
]

def upsert_tool(data: dict, source_app: str, source_file: str) -> tuple:
    data = data.copy()
    if data.get("types") not in VALID_TYPES:
        data["types"] = "App Provided"
        
    tool_type = data.get("tool_type")
    if tool_type and not frappe.db.exists("Agent Tool Type", tool_type):
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
