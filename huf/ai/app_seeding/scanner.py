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
            # Check Python package root (e.g., apps/myapp/myapp/huf)
            app_path = frappe.get_app_path(app)
            huf_dir = Path(app_path) / "huf"
            if huf_dir.is_dir():
                result[app] = huf_dir
                continue
            
            # Check App root (e.g., apps/myapp/huf)
            app_root = Path(app_path).parent
            huf_dir_alt = app_root / "huf"
            if huf_dir_alt.is_dir():
                result[app] = huf_dir_alt
        except Exception as e:
            frappe.log_error(
                title="App Seeding Scanner",
                message=f"Error checking app {app} for seed directory: {e}",
            )
    return result

def find_www_template_dir(app_name: str, template_name: str) -> Path | None:
    """
    Resolve a provider app's own per-app ``www/`` portal template directory,
    analogous to ``find_seed_dirs()`` above -- same two-location precedent
    (package root first, then app repo root), same "huf is never modified"
    contract: the template lives entirely under the *provider* app's own
    source tree, never under the shared ``huf/www/``.

    ``template_name`` is the manifest's ``www_template`` value (already
    validated by apps_loader to match the app_id slug shape, so it is always
    a single path segment -- no traversal risk).

    Checked in this order:
    1. ``apps/<app_name>/<app_name>/www/<template_name>/`` (package root --
       preferred; this is also where a colocated ``index.py`` with
       ``get_context`` can be imported as ``<app_name>.www.<template_name>.index``,
       the same way ``huf.www.huf`` backs ``huf/www/huf.html``).
    2. ``apps/<app_name>/www/<template_name>/`` (app repo root).

    Returns the resolved ``Path`` if it exists and is a directory containing
    an ``index.html``, else ``None``. Never raises -- a missing/misconfigured
    template is a validation-time or render-time concern for the caller, not
    a scanner-level error.
    """
    try:
        app_path = Path(frappe.get_app_path(app_name))
    except Exception:
        return None

    candidates = (
        app_path / "www" / template_name,
        app_path.parent / "www" / template_name,
    )
    for candidate in candidates:
        try:
            if candidate.is_dir() and (candidate / "index.html").is_file():
                return candidate
        except Exception:
            continue
    return None


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
        frappe.log_error(title="App Seeding Scanner", message=f"Error reading seed directory {type_dir}: {e}")
        
    return files
