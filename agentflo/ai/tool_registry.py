import importlib
import frappe

TOOL_DOCTYPE = "Agent Tool Function"

def _iter_declared_tools():
    for group in frappe.get_hooks("agentflo_tools") or []:
        for tool in (group if isinstance(group, (list, tuple)) else [group]):
            yield tool

def validate_tool_def(d):
    required = {"tool_name","description","function_path","parameters"}
    missing = required - set(d)
    if missing:
        frappe.throw(f"Invalid tool def {d.get('tool_name')}: missing {missing}")
    mod, fn = d["function_path"].rsplit(".", 1)
    callable_obj = getattr(importlib.import_module(mod), fn, None)
    if not callable(callable_obj):
        frappe.throw(f"Function not callable: {d['function_path']}")
    return d

def upsert_tool_doc(d):
    docname = frappe.db.get_value(TOOL_DOCTYPE, {"tool_name": d["tool_name"]})
    payload = {
        "doctype": TOOL_DOCTYPE,
        "tool_name": d["tool_name"],
        "description": d["description"],
        "types":"App Provided",
        "function_path": d["function_path"],
        "parameters": [{"param_name": p["name"], "param_type": p["type"], "required": int(p.get("required", False))}
                       for p in d["parameters"]],
    }
    if docname:
        doc = frappe.get_doc(TOOL_DOCTYPE, docname)
        doc.update(payload)
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(payload).insert(ignore_permissions=True)

def get_tools_by_app(apps_to_scan=None):
    """
    Get tools from hooks for specified apps or all installed apps.
    
    Args:
        apps_to_scan: List of app names to scan, or None for all installed apps
    
    Returns:
        dict: {app_name: [list of tools]}
    """
    tools_by_app = {}
    apps = apps_to_scan if apps_to_scan is not None else frappe.get_installed_apps()
    
    for app in apps:
        app_hooks = frappe.get_hooks("agentflo_tools", app_name=app) or []
        if app_hooks:
            tools_by_app[app] = app_hooks
    return tools_by_app

@frappe.whitelist()
def sync_discovered_tools(apps_to_scan=None):
    """
    Sync discovered tools from hooks.
    
    Args:
        apps_to_scan: List of app names to scan, or None for all installed apps
                     (None = full scan, used for manual sync and after_migrate)
    
    Returns:
        dict: Summary of sync results
    """
    tools_by_app = get_tools_by_app(apps_to_scan)

    valid_tool_names = set()

    for app, tools in tools_by_app.items():
        for d in tools:
            mod, fn = d["function_path"].rsplit(".", 1)
            if not callable(getattr(importlib.import_module(mod), fn, None)):
                frappe.throw(f"Not callable: {d['function_path']}")
            
            tool_name = d["tool_name"]
            valid_tool_names.add(tool_name)

            docname = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name})
            payload = {
                "doctype": "Agent Tool Function",
                "tool_name": tool_name,
                "description": d.get("description"),
                "types": "App Provided",
                "function_path": d["function_path"],
                "parameters": [
                    {
                        "label": p["name"].title(),
                        "fieldname": p["name"],
                        "param_type": p["type"],
                        "required": int(p.get("required", False)),
                    }
                    for p in d.get("parameters", [])
                ],
                "provider_app": app,
            }
            if docname:
                doc = frappe.get_doc("Agent Tool Function", docname)
                doc.update(payload)
                doc.save(ignore_permissions=True)
            else:
                frappe.get_doc(payload).insert(ignore_permissions=True)

    # Only cleanup orphaned tools if scanning all apps (not incremental)
    if apps_to_scan is None:
        existing_tools = frappe.get_all(
            "Agent Tool Function",
            filters={"types": "App Provided"},
            fields=["name", "tool_name"]
        )
        for t in existing_tools:
            if t.tool_name not in valid_tool_names:
                frappe.delete_doc("Agent Tool Function", t.name, ignore_permissions=True, force=True)
    
    return {
        "synced_apps": list(tools_by_app.keys()),
        "total_tools": len(valid_tool_names)
    }

def sync_app_tools(app_name):
    """
    Sync tools for a specific app (called from after_app_install hook).
    
    Args:
        app_name: Name of the app to sync tools for
    """
    try:
        result = sync_discovered_tools(apps_to_scan=[app_name])
        frappe.log_error(
            f"Synced tools for app '{app_name}': {result.get('total_tools', 0)} tools",
            "Tool Sync"
        )
    except Exception as e:
        frappe.log_error(
            f"Failed to sync tools for app '{app_name}': {str(e)}",
            "Tool Sync Error"
        )
