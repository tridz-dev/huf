import importlib
import json
import os
from datetime import datetime
import frappe
from frappe import _
from frappe.utils import now_datetime

TOOL_DOCTYPE = "Agent Tool Function"
CACHE_DOCTYPE = "Agent Settings"  # Singleton for caching

class PermissionAwareToolRegistry:
    """Registry that filters tools based on user permissions"""
    
    TOOL_PERMISSIONS = {
        "Get Document": {"permission": "read"},
        "Get List": {"permission": "read"},
        "Create Document": {"permission": "create"},
        "Create Multiple Documents": {"permission": "create"},
        "Update Document": {"permission": "write"},
        "Update Multiple Documents": {"permission": "write"},
        "Delete Document": {"permission": "delete"},
        "Delete Multiple Documents": {"permission": "delete"},
        "Submit Document": {"permission": "submit"},
        "Cancel Document": {"permission": "cancel"},
        "Attach File to Document": {"permission": "create"} 
    }
    
    MUTATING_TOOL_TYPES = {
        "Create Document", "Create Multiple Documents",
        "Update Document", "Update Multiple Documents", 
        "Delete Document", "Delete Multiple Documents",
        "Submit Document", "Cancel Document",
        "Set Value", "POST", "Run Agent",
        "Attach File to Document"
    }

    @classmethod
    def get_allowed_tools(cls, agent_doc, user: str) -> list:
        """Return only tools the user has permission to use"""
        all_tools = []
        
        if not hasattr(agent_doc, "agent_tool"):
            return []

        for tool_link in agent_doc.agent_tool:
            try:
                tool_doc = frappe.get_doc("Agent Tool Function", tool_link.tool)
                
                if cls._can_use_tool(tool_doc, user):
                    all_tools.append(tool_doc)

            except Exception as e:
                frappe.log_error(f"Error checking tool permission for {tool_link.tool}: {e}", "Tool Registry")
        
        return all_tools
    
    @classmethod
    def _can_use_tool(cls, tool_doc, user: str) -> bool:
        """Check if user has permission for this tool"""
        tool_type = tool_doc.types
        
        # Read Only restriction
        if tool_doc.is_read_only and tool_type in cls.MUTATING_TOOL_TYPES:
            return False
        
        #Guest Restrictions
        if user == "Guest":
            #Explicitly Allowed
            if bool(tool_doc.allowed_for_guest):
                return True
                
            #Hard block mutated tools if NOT explicitly allowed
            if tool_type in cls.MUTATING_TOOL_TYPES:
                return False
                
            return False

        #Reference DocType Permission Checks
        if tool_doc.reference_doctype:
            perm_type = None
             
            #Explicitly configured permission
            if tool_doc.required_permission:
                perm_type = tool_doc.required_permission
             
            #Implicit based on tool type
            elif tool_type in cls.TOOL_PERMISSIONS:
                perm_type = cls.TOOL_PERMISSIONS[tool_type]["permission"]
             
            if perm_type:
                if not frappe.has_permission(doctype=tool_doc.reference_doctype, ptype=perm_type, user=user):
                    return False
                     
        return True

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
        if frappe.db.exists("DocType", CACHE_DOCTYPE):
            settings = frappe.get_single(CACHE_DOCTYPE)
            if hasattr(settings, "last_app_scans") and settings.last_app_scans:
                return json.loads(settings.last_app_scans)
    except Exception:
        # DocType might not exist yet, fail silently
        pass
    return {}

def _update_cached_scans(apps_scanned):
    """
    Update cached scan timestamps for scanned apps.
    
    Args:
        apps_scanned: List of app names that were scanned
    """
    try:
        # Only update cache if Agent Settings DocType exists
        if not frappe.db.exists("DocType", CACHE_DOCTYPE):
            return
        
        settings = frappe.get_single(CACHE_DOCTYPE)
        cache = _get_cached_scans()
        current_time = now_datetime().isoformat()
        
        for app in apps_scanned:
            cache[app] = current_time
        
        # Create field if it doesn't exist (for backward compatibility)
        if not hasattr(settings, "last_app_scans"):
            return
        
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


def _normalize_hook_tools(hook_value):
    """Normalize huf_tools hook values into a flat list of tool-definition dicts."""
    normalized = []

    if isinstance(hook_value, str):
        try:
            hook_value = frappe.get_attr(hook_value)
        except Exception:
            return normalized

    if isinstance(hook_value, dict):
        return [hook_value]

    if isinstance(hook_value, (list, tuple)):
        for item in hook_value:
            normalized.extend(_normalize_hook_tools(item))

    return normalized

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
        app_hooks = frappe.get_hooks("huf_tools", app_name=app) or []
        app_tools = []

        for hook_entry in app_hooks:
            app_tools.extend(_normalize_hook_tools(hook_entry))

        if app_tools:
            tools_by_app[app] = app_tools
    
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
    
    errors = []
    synced_count = 0
    
    try:
        tools_by_app = get_tools_by_app(apps_to_scan, use_cache=cache_enabled)
    except Exception as e:
        frappe.log_error(f"Failed to get tools from apps: {str(e)}", "Tool Sync Error")
        return {
            "synced_apps": [],
            "total_tools": 0,
            "errors": [f"Failed to get tools: {str(e)}"]
        }

    # BATCH 1: Collect all tools to process (with error handling per app)
    tools_to_process = []
    for app, tools in tools_by_app.items():
        try:
            if not isinstance(tools, (list, tuple)):
                tools = [tools]
            for d in tools:
                if d:  # Skip None/empty tools
                    tools_to_process.append((app, d))
        except Exception as e:
            errors.append(f"App '{app}': Failed to process tools list: {str(e)}")
            frappe.log_error(f"Failed to process tools for app '{app}': {str(e)}", "Tool Sync Error")
            continue

    # Ensure all tool types exist
    for app, d in tools_to_process:
        try:
            category = d.get("tool_type")
            if category and not frappe.db.exists("Agent Tool Type", category):
                tool_type_doc = frappe.new_doc("Agent Tool Type")
                tool_type_doc.name1 = category
                tool_type_doc.insert(ignore_permissions=True)
        except Exception as e:
            errors.append(f"Failed to create Tool Type '{category}': {str(e)}")
    
    # BATCH 2: Validate all functions first (before any DB operations)
    validated_tools = []
    validation_cache = {}  # function_path -> bool
    
    for app, d in tools_to_process:
        try:
            func_path = d.get("function_path")
            tool_name = d.get("tool_name")
            
            if not tool_name:
                errors.append(f"App '{app}': Tool missing tool_name")
                continue
            
            if not func_path:
                errors.append(f"App '{app}': Tool '{tool_name}' missing function_path")
                continue
            
            # Use cache to avoid re-validating same function
            if func_path not in validation_cache:
                try:
                    mod, fn = func_path.rsplit(".", 1)
                    module_obj = importlib.import_module(mod)
                    func_obj = getattr(module_obj, fn, None)
                    validation_cache[func_path] = callable(func_obj)
                except ImportError as ie:
                    validation_cache[func_path] = False
                    errors.append(f"App '{app}': Tool '{tool_name}': Cannot import module '{mod}': {str(ie)}")
                except AttributeError as ae:
                    validation_cache[func_path] = False
                    errors.append(f"App '{app}': Tool '{tool_name}': Function '{fn}' not found: {str(ae)}")
                except Exception as e:
                    validation_cache[func_path] = False
                    errors.append(f"App '{app}': Tool '{tool_name}': Validation error: {str(e)}")
            
            if validation_cache[func_path]:
                validated_tools.append((app, d))
            else:
                errors.append(f"App '{app}': Tool '{tool_name}': Function '{func_path}' is not callable")
        except Exception as e:
            errors.append(f"App '{app}': Error processing tool: {str(e)}")
            frappe.log_error(f"Error processing tool in app '{app}': {str(e)}", "Tool Sync Error")
            continue
    
    # BATCH 3: Get all existing tools in one query
    valid_tool_names = set()
    existing_tools = {}
    
    try:
        if validated_tools:
            tool_names = [d.get("tool_name") for _, d in validated_tools]
            existing_docs = frappe.get_all(
                "Agent Tool Function",
                filters={"tool_name": ["in", tool_names]},
                fields=["name", "tool_name"]
            )
            existing_tools = {t.tool_name: t.name for t in existing_docs}
    except Exception as e:
        errors.append(f"Failed to fetch existing tools: {str(e)}")
        frappe.log_error(f"Failed to fetch existing tools: {str(e)}", "Tool Sync Error")
    
    # BATCH 4: Prepare bulk operations (with error handling)
    to_create = []
    to_update = []
    
    for app, d in validated_tools:
        try:
            tool_name = d.get("tool_name")
            valid_tool_names.add(tool_name)
            
            # Validate parameters format
            parameters = d.get("parameters", [])
            if not isinstance(parameters, (list, tuple)):
                errors.append(f"App '{app}': Tool '{tool_name}': parameters must be a list")
                continue
            
            payload = {
                "tool_name": tool_name,
                "description": d.get("description", ""),
                "types": "App Provided",
                "tool_type":  d.get("tool_type"),
                "function_path": d.get("function_path"),
                "parameters": [
                    {
                        "label": p.get("label") or p.get("name", "").replace("_", " ").title(),
                        "fieldname": p.get("fieldname") or p.get("name", ""),
                        "param_type": p.get("type", "Data"),
                        "required": int(p.get("required", False)),
                        "description": p.get("description", ""),
                    }
                    for p in parameters
                ],
                "provider_app": app,
            }
            
            if tool_name in existing_tools:
                to_update.append((existing_tools[tool_name], payload))
            else:
                payload["doctype"] = "Agent Tool Function"
                to_create.append(payload)
        except Exception as e:
            errors.append(f"App '{app}': Failed to prepare tool '{d.get('tool_name', 'unknown')}': {str(e)}")
            frappe.log_error(f"Failed to prepare tool in app '{app}': {str(e)}", "Tool Sync Error")
            continue
    
    # BATCH 5: Execute database operations (with per-tool error handling)
    for docname, payload in to_update:
        try:
            doc = frappe.get_doc("Agent Tool Function", docname)
            doc.update(payload)
            doc.save(ignore_permissions=True)
            synced_count += 1
        except Exception as e:
            tool_name = payload.get("tool_name", "unknown")
            error_msg = f"Failed to update tool '{tool_name}' (docname: {docname}): {str(e)}"
            errors.append(error_msg)
            frappe.log_error(error_msg, "Tool Sync Error")
            continue
    
    for payload in to_create:
        try:
            frappe.get_doc(payload).insert(ignore_permissions=True)
            synced_count += 1
        except Exception as e:
            tool_name = payload.get("tool_name", "unknown")
            error_msg = f"Failed to create tool '{tool_name}': {str(e)}"
            errors.append(error_msg)
            frappe.log_error(error_msg, "Tool Sync Error")
            continue

    # Only cleanup orphaned tools if scanning all apps (not incremental)
    if apps_to_scan is None:
        try:
            existing_tools = frappe.get_all(
                "Agent Tool Function",
                filters={"types": "App Provided"},
                fields=["name", "tool_name"]
            )
            for t in existing_tools:
                if t.tool_name not in valid_tool_names:
                    try:
                        frappe.delete_doc("Agent Tool Function", t.name, ignore_permissions=True, force=True)
                    except Exception as e:
                        errors.append(f"Failed to delete orphaned tool '{t.tool_name}': {str(e)}")
                        frappe.log_error(f"Failed to delete orphaned tool '{t.tool_name}': {str(e)}", "Tool Sync Error")
        except Exception as e:
            errors.append(f"Failed to cleanup orphaned tools: {str(e)}")
            frappe.log_error(f"Failed to cleanup orphaned tools: {str(e)}", "Tool Sync Error")
    
    # Log summary of errors if any
    if errors:
        frappe.log_error(
            f"Tool sync completed with {len(errors)} error(s). Synced {synced_count} tools successfully.\n"
            f"Errors:\n" + "\n".join(errors[:20]),  # Limit to first 20 errors
            "Tool Sync Errors"
        )
    
    return {
        "synced_apps": list(tools_by_app.keys()),
        "total_tools": synced_count,
        "errors": errors[:50] if errors else [],  # Return first 50 errors
        "error_count": len(errors)
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
