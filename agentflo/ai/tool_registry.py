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

def get_tools_by_app():
    tools_by_app = {}
    for app in frappe.get_installed_apps():
        app_hooks = frappe.get_hooks("agentflo_tools", app_name=app) or []
        if app_hooks:
            tools_by_app[app] = app_hooks
    return tools_by_app

@frappe.whitelist()
def sync_discovered_tools():
    tools_by_app = get_tools_by_app()
    for app, tools in tools_by_app.items():
        for d in tools:
            mod, fn = d["function_path"].rsplit(".", 1)
            if not callable(getattr(importlib.import_module(mod), fn, None)):
                frappe.throw(f"Not callable: {d['function_path']}")
            docname = frappe.db.get_value("Agent Tool Function", {"tool_name": d["tool_name"]})
            payload = {
                "doctype": "Agent Tool Function",
                "tool_name": d["tool_name"],
                "description": d.get("description"),
                "types":"App Provided",
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
