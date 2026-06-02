import os
import frappe
from pathlib import Path

def find_seed_dirs() -> dict:
    """
    Returns {app_name: Path} for every installed app that has a huf/ seed dir.
    Skips 'huf' itself.
    """
    result = {}
    installed_apps = frappe.get_installed_apps()
    for app in installed_apps:
        if app == "huf":
            continue
        try:
            app_path = frappe.get_app_path(app)
            huf_dir = Path(app_path) / "huf"
            if huf_dir.is_dir():
                result[app] = huf_dir
        except Exception as e:
            frappe.log_error(f"Error checking app {app} for seed directory: {e}", "App Seeding Scanner")
    return result

def get_seed_files(huf_dir: Path, type_folder: str) -> list:
    """
    Returns a list of Path objects for all .json files in a specific type folder.
    Non-recursive (flat scan).
    """
    type_dir = huf_dir / type_folder
    if not type_dir.is_dir():
        return []
    
    files = []
    try:
        for item in type_dir.iterdir():
            if item.is_file() and item.name.endswith(".json"):
                files.append(item)
    except Exception as e:
        frappe.log_error(f"Error reading seed directory {type_dir}: {e}", "App Seeding Scanner")
        
    return files
