# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Whitelisted API surface for the Huf Skills system.

These methods are consumed by the frontend skills UI and can also be called
from Frappe client scripts.
"""

from __future__ import annotations

from typing import Any

import frappe

from huf.ai.skills.hooks import sync_app_skills as _sync_app_skills
from huf.ai.skills.importer import (
    import_skill_from_common_destination as _import_skill_from_common_destination,
    import_skill_from_git as _import_skill_from_git,
)


@frappe.whitelist()
def import_skill_from_git(repo_url: str, path: str = "skills", ref: str = "main") -> dict[str, Any]:
    """Whitelisted wrapper around ``huf.ai.skills.importer.import_skill_from_git``."""
    return _import_skill_from_git(repo_url=repo_url, path=path, ref=ref)


@frappe.whitelist()
def import_skill_from_common_destination(destination_name: str) -> dict[str, Any]:
    """Whitelisted wrapper around ``huf.ai.skills.importer.import_skill_from_common_destination``."""
    return _import_skill_from_common_destination(destination_name=destination_name)


@frappe.whitelist()
def sync_app_skills(apps_to_scan=None, use_cache: bool = True) -> dict[str, Any]:
    """Whitelisted wrapper around ``huf.ai.skills.hooks.sync_app_skills``."""
    return _sync_app_skills(apps_to_scan=apps_to_scan, use_cache=use_cache)


@frappe.whitelist()
def get_skill_options() -> list[dict[str, Any]]:
    """Return active skills as label/value options for the frontend.

    Used by link/multi-select fields that need a simple options list.
    """
    if not frappe.db.exists("DocType", "Skill"):
        return []

    skills = frappe.get_all(
        "Skill",
        filters={"status": "Active"},
        fields=["skill_name", "title", "description", "skill_icon"],
        order_by="title asc",
    )

    return [
        {
            "label": skill.title or skill.skill_name,
            "value": skill.skill_name,
            "description": skill.description,
            "icon": skill.skill_icon,
        }
        for skill in skills
    ]
