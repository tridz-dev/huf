"""Per-app scan cache for tool discovery (hooks.py mtime vs last scan timestamp)."""
import json
import os
from datetime import datetime

import frappe
from frappe.utils import now_datetime

CACHE_DOCTYPE = "Agent Settings"  # Singleton for caching


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
    except (OSError, frappe.DoesNotExistError, frappe.ValidationError, AttributeError, ValueError):
        # Cache probe is best-effort; fail silently
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
    except (json.JSONDecodeError, frappe.DoesNotExistError, frappe.ValidationError, AttributeError, TypeError):
        # Cache may not exist yet; fail silently
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
    except (frappe.DoesNotExistError, frappe.ValidationError, TypeError, ValueError, json.JSONDecodeError):
        # Cache update is non-critical; fail silently
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
            except ValueError:
                # If cache is invalid, scan the app
                apps_to_scan.append(app)
    
    return apps_to_scan
