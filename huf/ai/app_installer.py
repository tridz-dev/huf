import frappe
from huf.huf.doctype.huf_data_table.api import create_data_table

@frappe.whitelist()
def install_huf_app(manifest: str) -> dict:
    """
    Install a Huf App from a JSON manifest.
    Returns {"success": True, "app_id": "...", "agent": "...", "tables_created": [...]}
    """
    data = frappe.parse_json(manifest)
    _validate_manifest(data)

    app_id = data["app_id"]
    if frappe.db.exists("Huf App", app_id):
        frappe.throw(f"App '{app_id}' already installed.")

    # Step 1: Create HUF tables
    table_map = {}  # {"Student": "HF Student"}
    for tdef in data.get("tables", []):
        result = create_data_table(
            table_name=tdef["table_name"],
            fields=tdef["fields"],
            description=tdef.get("description", ""),
        )
        doctype_name = result["data"]["doctype_name"]  # e.g. "HF Student"
        table_map[tdef["table_name"]] = doctype_name

    # Step 2: Create Agent Tool Functions (5 CRUD ops per table)
    tool_names = _create_crud_tools(app_id, table_map)

    # Step 3: Resolve model + provider
    provider, model = _resolve_model(data.get("agent", {}))

    # Step 4: Create Agent
    agent_def = data["agent"]
    agent_doc = frappe.get_doc({
        "doctype": "Agent",
        "agent_name": agent_def["agent_name"],
        "provider": provider,
        "model": model,
        "instructions": agent_def["instructions"],
        "allow_chat": 1,
        "persist_conversation": 1,
    })
    for tool_name in tool_names:
        agent_doc.append("agent_tool", {"tool": tool_name})
    agent_doc.insert(ignore_permissions=True)

    # Step 5: Create Knowledge Sources + Inputs; link to agent
    for ks_def in data.get("knowledge", []):
        ks_doc = frappe.get_doc({
            "doctype": "Knowledge Source",
            "source_name": ks_def["source_name"],
            "knowledge_type": ks_def.get("knowledge_type", "sqlite_fts"),
            "scope": "Site",
        })
        ks_doc.insert(ignore_permissions=True)
        for inp in ks_def.get("inputs", []):
            frappe.get_doc({
                "doctype": "Knowledge Input",
                "knowledge_source": ks_doc.name,
                "input_type": inp["input_type"],
                "text": inp.get("text", ""),
                "file": inp.get("file", ""),
                "url": inp.get("url", ""),
            }).insert(ignore_permissions=True)
        agent_doc.reload()
        agent_doc.append("agent_knowledge", {
            "knowledge_source": ks_doc.name,
            "mode": "Optional",
            "max_chunks": 5,
        })
        agent_doc.save()

    # Step 6: Create Huf App record
    frappe.get_doc({
        "doctype": "Huf App",
        "app_id": app_id,
        "label": data["label"],
        "description": data.get("description", ""),
        "icon": data.get("icon", ""),
        "shell": data["shell"],
        "agent": agent_doc.name,
        "manifest_json": frappe.as_json(data),
        "status": "Active",
    }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {
        "success": True,
        "app_id": app_id,
        "agent": agent_doc.name,
        "tables_created": list(table_map.keys()),
    }


def _create_crud_tools(app_id: str, table_map: dict) -> list[str]:
    """Create one Agent Tool Function per CRUD operation per table. Returns list of tool names."""
    ops = [
        ("Get Document",    "Fetch a single {t} record by name"),
        ("Get List",        "List {t} records with optional filters"),
        ("Create Document", "Create a new {t} record"),
        ("Update Document", "Update fields on an existing {t} record"),
        ("Delete Document", "Delete a {t} record by name"),
    ]
    names = []
    for table_name, doctype_name in table_map.items():
        slug = table_name.lower().replace(" ", "_")
        for op_type, desc_tpl in ops:
            tool_name = f"app_{app_id}_{slug}_{op_type.lower().replace(' ', '_')}"
            if not frappe.db.exists("Agent Tool Function", tool_name):
                frappe.get_doc({
                    "doctype": "Agent Tool Function",
                    "tool_name": tool_name,
                    "types": op_type,
                    "reference_doctype": doctype_name,
                    "description": desc_tpl.format(t=table_name),
                }).insert(ignore_permissions=True)
            names.append(tool_name)
    return names


def _resolve_model(agent_def: dict) -> tuple[str, str]:
    """
    Returns (provider_name, model_name).
    Priority:
      1. manifest provider + model if provider key exists in AI Provider
      2. first AI Provider with a non-empty api_key
      3. frappe.throw() asking user to add a provider key
    """
    requested_provider = agent_def.get("provider")
    requested_model = agent_def.get("model")

    if requested_provider and requested_model:
        if frappe.db.get_value("AI Provider", requested_provider, "api_key"):
            return requested_provider, requested_model

    # Fall back to any available provider
    providers = frappe.get_all("AI Provider", filters={"disabled": 0}, fields=["name", "api_key"])
    for p in providers:
        if p.get("api_key"):
            # Pick first model from this provider
            model = frappe.get_value("AI Model", {"provider": p["name"], "disabled": 0}, "name")
            if model:
                return p["name"], model

    frappe.throw(
        "No AI provider key found. Go to AI Providers and add an API key before installing apps."
    )


def _validate_manifest(data: dict):
    required = ["app_id", "label", "tables", "agent", "shell", "views"]
    for field in required:
        if not data.get(field):
            frappe.throw(f"Manifest missing required field: '{field}'")
    valid_shells = ("chat", "dashboard", "list")
    if data["shell"] not in valid_shells:
        frappe.throw(f"shell must be one of: {valid_shells}")


@frappe.whitelist()
def delete_huf_app(app_id: str) -> dict:
    """
    Remove a Huf App and its agent. Does NOT delete HUF tables or their data.
    Returns {"success": True}
    """
    app = frappe.get_doc("Huf App", app_id)
    if app.agent:
        frappe.delete_doc("Agent", app.agent, ignore_permissions=True)
    frappe.delete_doc("Huf App", app_id, ignore_permissions=True)
    frappe.db.commit()
    return {"success": True}


@frappe.whitelist()
def get_huf_app(app_id: str) -> dict:
    """Return full manifest JSON for a Huf App."""
    doc = frappe.get_doc("Huf App", app_id)
    return frappe.parse_json(doc.manifest_json)
