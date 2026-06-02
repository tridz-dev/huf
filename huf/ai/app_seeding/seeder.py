import json
import frappe
from pathlib import Path
from dataclasses import dataclass
from typing import List

from .scanner import find_seed_dirs, get_seed_files
from .loaders import (
    upsert_prompt,
    upsert_tool,
    upsert_knowledge,
    upsert_agent,
    upsert_trigger
)

@dataclass
class SeedResult:
    app: str
    seeded: int
    skipped: int
    errors: List[str]

# Load order matters for dependency resolution
LOAD_ORDER = [
    ("prompts", upsert_prompt),
    ("tools", upsert_tool),
    ("knowledge", upsert_knowledge),
    ("agents", upsert_agent),
    ("triggers", upsert_trigger)
]

def seed_app(app_name: str, huf_dir: Path) -> SeedResult:
    result = SeedResult(app=app_name, seeded=0, skipped=0, errors=[])
    
    for type_folder, loader_fn in LOAD_ORDER:
        files = get_seed_files(huf_dir, type_folder)
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                source_file = f"huf/{type_folder}/{file_path.name}"
                ok, error = loader_fn(data, app_name, source_file)
                
                if ok:
                    result.seeded += 1
                else:
                    result.skipped += 1
                    result.errors.append(f"Failed to seed {file_path.name}: {error}")
            except Exception as e:
                result.skipped += 1
                result.errors.append(f"Error parsing {file_path.name}: {e}")
                frappe.log_error(f"Error parsing seed file {file_path}: {e}", "App Seeding Error")
                
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
