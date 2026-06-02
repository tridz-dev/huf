import frappe

def _upsert_doc(doctype: str, key_field: str, data: dict, source_app: str, source_file: str) -> tuple:
    """
    Generic upsert for a seed document.
    """
    key_val = data.get(key_field)
    if not key_val:
        return False, f"Missing {key_field}"
        
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
    return _upsert_doc("Agent", "agent_name", data, source_app, source_file)

def upsert_tool(data: dict, source_app: str, source_file: str) -> tuple:
    # Ensure types is set, default to App Provided if not Custom Function
    if data.get("types") not in ["Custom Function", "App Provided"]:
        data["types"] = "App Provided"
    return _upsert_doc("Agent Tool Function", "tool_name", data, source_app, source_file)

def upsert_prompt(data: dict, source_app: str, source_file: str) -> tuple:
    # Prompt key is usually 'title'
    return _upsert_doc("Agent Prompt", "title", data, source_app, source_file)

def upsert_knowledge(data: dict, source_app: str, source_file: str) -> tuple:
    return _upsert_doc("Knowledge Source", "source_name", data, source_app, source_file)

def upsert_trigger(data: dict, source_app: str, source_file: str) -> tuple:
    return _upsert_doc("Agent Trigger", "trigger_name", data, source_app, source_file)
