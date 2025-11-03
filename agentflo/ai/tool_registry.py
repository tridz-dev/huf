import importlib
import json
import os
from datetime import datetime
import frappe
from frappe.utils import now_datetime

TOOL_DOCTYPE = "Agent Tool Function"
CACHE_DOCTYPE = "Agent Settings"  # Singleton for caching

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

def _get_app_modified_time(app_name):
    """
    Get modification time of app's hooks.py file as proxy for app changes.
    
    Args:
        app_name: Name of the app
    
    Returns:
        datetime: Modification time of hooks.py, or None if not found
    """
    try:
        app_path = frappe.get_app_path(app_name)
        hooks_path = os.path.join(app_path, "hooks.py")
        if os.path.exists(hooks_path):
            mtime = os.path.getmtime(hooks_path)
            return datetime.fromtimestamp(mtime)
    except Exception:
        pass
    return None

def _get_cached_scans():
    """
    Get cached scan timestamps for each app.
    
    Returns:
        dict: {app_name: datetime}
    """
    try:
        settings = frappe.get_single(CACHE_DOCTYPE)
        if hasattr(settings, "last_app_scans") and settings.last_app_scans:
            return json.loads(settings.last_app_scans)
    except Exception:
        pass
    return {}

def _update_cached_scans(apps_scanned):
    """
    Update cached scan timestamps for scanned apps.
    
    Args:
        apps_scanned: List of app names that were scanned
    """
    try:
        settings = frappe.get_single(CACHE_DOCTYPE)
        cache = _get_cached_scans()
        current_time = now_datetime().isoformat()
        
        for app in apps_scanned:
            cache[app] = current_time
        
        settings.last_app_scans = json.dumps(cache)
        settings.save(ignore_permissions=True)
    except Exception:
        # Cache update is non-critical, fail silently
        pass

def _get_apps_to_scan():
    """
    Determine which apps need scanning based on cache and modification times.
    
    Returns:
        list: App names that need scanning
    """
    installed_apps = frappe.get_installed_apps()
    cache = _get_cached_scans()
    apps_to_scan = []
    
    for app in installed_apps:
        app_modified = _get_app_modified_time(app)
        last_scan_str = cache.get(app)
        
        # If no cache or app modified since last scan, add to scan list
        if not last_scan_str or not app_modified:
            apps_to_scan.append(app)
        else:
            try:
                last_scan = datetime.fromisoformat(last_scan_str)
                if app_modified > last_scan:
                    apps_to_scan.append(app)
            except Exception:
                # If cache is invalid, scan the app
                apps_to_scan.append(app)
    
    return apps_to_scan

def get_tools_by_app(apps_to_scan=None, use_cache=True):
    """
    Get tools from hooks for specified apps or all installed apps.
    Uses cache to skip apps that haven't changed since last scan.
    
    Args:
        apps_to_scan: List of app names to scan, or None for all installed apps
        use_cache: If True, use cache to skip unchanged apps (only when apps_to_scan is None)
    
    Returns:
        dict: {app_name: [list of tools]}
    """
    tools_by_app = {}
    
    if apps_to_scan is None and use_cache:
        # Use cache to determine which apps need scanning
        apps_to_scan = _get_apps_to_scan()
    elif apps_to_scan is None:
        apps_to_scan = frappe.get_installed_apps()
    
    for app in apps_to_scan:
        app_hooks = frappe.get_hooks("agentflo_tools", app_name=app) or []
        if app_hooks:
            tools_by_app[app] = app_hooks
    
    # Update cache with scanned apps
    if use_cache and apps_to_scan:
        _update_cached_scans(apps_to_scan)
    
    return tools_by_app

@frappe.whitelist()
def sync_discovered_tools(apps_to_scan=None, use_cache=True):
    """
    Sync discovered tools from hooks.
    
    Args:
        apps_to_scan: List of app names to scan, or None for all installed apps
                     (None = full scan, used for manual sync and after_migrate)
        use_cache: If True, use cache to skip unchanged apps (only when apps_to_scan is None)
    
    Returns:
        dict: Summary of sync results
    """
    # For manual sync, don't use cache (force full scan)
    # For incremental sync (apps_to_scan specified), always scan those apps
    cache_enabled = use_cache and apps_to_scan is None
    
    tools_by_app = get_tools_by_app(apps_to_scan, use_cache=cache_enabled)

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
