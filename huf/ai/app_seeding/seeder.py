import json
import frappe
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from .scanner import find_seed_dirs, get_seed_files
from .loaders import (
    upsert_prompt,
    upsert_tool,
    upsert_knowledge,
    upsert_agent,
    upsert_trigger
)
from .apps_loader import upsert_huf_app

@dataclass
class SeedResult:
    app: str
    seeded: int
    skipped: int
    errors: List[str]
    skipped_records: List[dict] = field(default_factory=list)

# Load order matters for dependency resolution.
# Apps load last so a manifest may later reference agents/capabilities
# seeded by the same provider app.
LOAD_ORDER = [
    ("prompts", upsert_prompt),
    ("tools", upsert_tool),
    ("knowledge", upsert_knowledge),
    ("agents", upsert_agent),
    ("triggers", upsert_trigger),
    ("apps", upsert_huf_app)
]

def seed_app(app_name: str, huf_dir: Path) -> SeedResult:
    result = SeedResult(app=app_name, seeded=0, skipped=0, errors=[])

    frappe.flags.in_seeding = True
    try:
        for type_folder, loader_fn in LOAD_ORDER:
            files = get_seed_files(huf_dir, type_folder)
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    source_file = f"huf/{type_folder}/{file_path.name}"

                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        ok, error = loader_fn(item, app_name, source_file)

                        if ok:
                            result.seeded += 1
                        else:
                            result.skipped += 1
                            # Use a fallback name if the key isn't standard across all types
                            item_name = item.get('name') or item.get('app_id') or item.get('title') or item.get('agent_name') or item.get('tool_name') or item.get('source_name') or file_path.name

                            if isinstance(error, dict) and error.get("reason") == "missing_refs":
                                missing_refs = error.get("missing_refs", [])
                                error_str = "Missing reference(s): " + ", ".join(missing_refs)
                            else:
                                missing_refs = []
                                error_str = str(error)

                            result.errors.append(f"Failed to seed {item_name}: {error_str}")

                            result.skipped_records.append({
                                "app": app_name,
                                "file": source_file,
                                "record": item_name,
                                "error": error_str,
                                "missing_refs": missing_refs,
                            })
                except Exception as e:
                    result.skipped += 1
                    result.errors.append(f"Error parsing {file_path.name}: {e}")
                    frappe.log_error(f"Error parsing seed file {file_path}: {e}", "App Seeding Error")
    finally:
        frappe.flags.in_seeding = False

    return result

def seed_all() -> List[SeedResult]:
    """Scans all installed apps and seeds their HUF definitions."""
    results = []
    seed_dirs = find_seed_dirs()
    
    for app_name, huf_dir in seed_dirs.items():
        res = seed_app(app_name, huf_dir)
        results.append(res)
        
    return results

def on_app_installed(app_name):
    """Hook for after_app_install to immediately seed the new app."""
    try:
        app_path = frappe.get_app_path(app_name)
        huf_dir = Path(app_path) / "huf"
        if huf_dir.is_dir():
            res = seed_app(app_name, huf_dir)
            if res.errors:
                frappe.log_error(f"Seeding errors for {app_name}: {res.errors}", "App Seeding")
    except Exception as e:
        frappe.log_error(f"Error in on_app_installed for {app_name}: {e}", "App Seeding Error")

@frappe.whitelist()
def seed_all_apps():
    """Whitelist endpoint to trigger manual sync from UI."""
    frappe.only_for("System Manager")
    
    results = seed_all()
    
    total_seeded = sum(r.seeded for r in results)
    total_skipped = sum(r.skipped for r in results)
    
    return {
        "status": "success",
        "message": f"Seeded {total_seeded} documents. Skipped {total_skipped}.",
        "results": [r.__dict__ for r in results]
    }
