# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
App hook sync for Huf Skills.

Installed Frappe apps can expose skills via the ``huf_skills`` hook. This module
scans those hooks, calls the referenced function paths to obtain skill manifests,
and upserts ``Skill`` documents.
"""

from __future__ import annotations

import importlib
import json
import os
from datetime import datetime
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.ai.skills.importer import (
    SKILL_DOCTYPE,
    _create_or_update_skill,
)

CACHE_DOCTYPE = "Agent Settings"


def _get_app_modified_time(app_name: str):
    """Return the modification time of an app's hooks.py as a datetime."""
    try:
        app_path = frappe.get_app_path(app_name)
        hooks_path = os.path.join(app_path, "hooks.py")
        if os.path.exists(hooks_path):
            mtime = os.path.getmtime(hooks_path)
            return datetime.fromtimestamp(mtime)
    except Exception:
        pass
    return None


def _get_cached_scans() -> dict[str, str]:
    """Return cached scan timestamps per app from Agent Settings."""
    try:
        if frappe.db.exists("DocType", CACHE_DOCTYPE):
            settings = frappe.get_single(CACHE_DOCTYPE)
            if hasattr(settings, "last_skill_scans") and settings.last_skill_scans:
                return json.loads(settings.last_skill_scans)
    except Exception:
        pass
    return {}


def _update_cached_scans(apps_scanned: list[str]) -> None:
    """Update cached scan timestamps for scanned apps."""
    try:
        if not frappe.db.exists("DocType", CACHE_DOCTYPE):
            return

        settings = frappe.get_single(CACHE_DOCTYPE)
        if not hasattr(settings, "last_skill_scans"):
            return

        cache = _get_cached_scans()
        current_time = now_datetime().isoformat()

        for app in apps_scanned:
            cache[app] = current_time

        settings.last_skill_scans = json.dumps(cache)
        settings.save(ignore_permissions=True)
    except Exception:
        pass


def _get_apps_to_scan() -> list[str]:
    """Determine which installed apps need scanning based on cache/modified times."""
    installed_apps = frappe.get_installed_apps()
    cache = _get_cached_scans()
    apps_to_scan = []

    for app in installed_apps:
        app_modified = _get_app_modified_time(app)
        last_scan_str = cache.get(app)

        if not last_scan_str or not app_modified:
            apps_to_scan.append(app)
        else:
            try:
                last_scan = datetime.fromisoformat(last_scan_str)
                if app_modified > last_scan:
                    apps_to_scan.append(app)
            except Exception:
                apps_to_scan.append(app)

    return apps_to_scan


def _normalize_hook_skills(hook_value):
    """Normalize ``huf_skills`` hook values into a flat list of skill-definition dicts."""
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
            normalized.extend(_normalize_hook_skills(item))

    return normalized


def _call_skill_function(function_path: str, app_name: str) -> dict[str, Any] | None:
    """Import and call the function at ``function_path`` to get a skill manifest."""
    if not function_path:
        return None

    try:
        module_path, fn_name = function_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, fn_name, None)
        if not callable(func):
            frappe.log_error(
                _("Skill function '{0}' is not callable for app '{1}'").format(function_path, app_name),
                "Skill Sync",
            )
            return None
        return func()
    except Exception as e:
        frappe.log_error(
            _("Failed to call skill function '{0}' for app '{1}': {2}").format(
                function_path, app_name, str(e)
            ),
            "Skill Sync",
        )
    return None


def get_skills_by_app(apps_to_scan=None, use_cache=True) -> dict[str, list[dict[str, Any]]]:
    """Scan apps for ``huf_skills`` hooks and return manifests grouped by app."""
    skills_by_app: dict[str, list[dict[str, Any]]] = {}

    if apps_to_scan is None and use_cache:
        apps_to_scan = _get_apps_to_scan()
    elif apps_to_scan is None:
        apps_to_scan = frappe.get_installed_apps()

    for app in apps_to_scan:
        app_hooks = frappe.get_hooks("huf_skills", app_name=app) or []
        app_skills = []

        for hook_entry in app_hooks:
            app_skills.extend(_normalize_hook_skills(hook_entry))

        if app_skills:
            skills_by_app[app] = app_skills

    if use_cache and apps_to_scan:
        _update_cached_scans(apps_to_scan)

    return skills_by_app


def sync_app_skills(apps_to_scan=None, use_cache=True) -> dict[str, Any]:
    """Sync skills exposed by installed apps via ``huf_skills`` hooks.

    Args:
        apps_to_scan: List of app names to scan, a single app name string,
            or None for all installed apps.
        use_cache: If True, skip apps whose hooks.py has not changed since last scan.

    Returns:
        dict: Summary of synced skills and any errors.
    """
    if isinstance(apps_to_scan, str):
        apps_to_scan = [apps_to_scan]

    if not frappe.db.exists("DocType", SKILL_DOCTYPE):
        return {
            "synced_apps": [],
            "total_skills": 0,
            "errors": ["Skill DocType does not exist yet"],
        }

    cache_enabled = use_cache and apps_to_scan is None
    errors: list[str] = []
    synced_count = 0
    valid_skill_names: set[str] = set()

    try:
        skills_by_app = get_skills_by_app(apps_to_scan, use_cache=cache_enabled)
    except Exception as e:
        frappe.log_error(f"Failed to get skills from apps: {str(e)}", "Skill Sync Error")
        return {
            "synced_apps": [],
            "total_skills": 0,
            "errors": [f"Failed to get skills: {str(e)}"],
        }

    for app, skill_defs in skills_by_app.items():
        for skill_def in skill_defs:
            try:
                if not isinstance(skill_def, dict):
                    errors.append(f"App '{app}': Skill definition is not a dict")
                    continue

                skill_name = skill_def.get("skill_name") or skill_def.get("name")
                function_path = skill_def.get("function_path")

                if not skill_name:
                    errors.append(f"App '{app}': Skill missing skill_name/name")
                    continue

                if not function_path:
                    errors.append(f"App '{app}': Skill '{skill_name}' missing function_path")
                    continue

                manifest = _call_skill_function(function_path, app)
                if not manifest:
                    errors.append(
                        f"App '{app}': Skill '{skill_name}' function returned no manifest"
                    )
                    continue

                # Merge hook metadata into the manifest so the skill record knows its origin.
                manifest.setdefault("name", skill_name)
                manifest.setdefault("title", skill_def.get("title", skill_name))
                manifest.setdefault("description", skill_def.get("description", ""))

                source_meta = {
                    "source_type": "App Provided",
                    "source_url": "",
                    "source_path": "",
                    "source_ref": "",
                    "provider_app": app,
                }

                synced_skill, warnings = _create_or_update_skill(manifest, source_meta)
                valid_skill_names.add(synced_skill)
                synced_count += 1

                if warnings:
                    for warning in warnings:
                        frappe.log_error(warning, "Skill Sync Warning")
            except Exception as e:
                error_msg = str(e)
                skill_name = skill_def.get("skill_name", "unknown") if isinstance(skill_def, dict) else "unknown"
                errors.append(f"App '{app}': Skill '{skill_name}': {error_msg}")
                frappe.log_error(
                    f"Error syncing skill '{skill_name}' from app '{app}': {error_msg}",
                    "Skill Sync Error",
                )
                continue

    # Cleanup orphaned app-provided skills.
    # During a full scan, remove any app-provided skill no longer declared.
    # During an app-specific scan (e.g. after_uninstall), remove app-provided
    # skills whose provider_app matches the scanned app.
    try:
        if apps_to_scan is None:
            existing_skills = frappe.get_all(
                SKILL_DOCTYPE,
                filters={"source_type": "App Provided"},
                fields=["name", "skill_name", "provider_app"],
            )
            skills_to_remove = [
                skill for skill in existing_skills if skill.skill_name not in valid_skill_names
            ]
        else:
            apps_set = set(apps_to_scan)
            existing_skills = frappe.get_all(
                SKILL_DOCTYPE,
                filters={"source_type": "App Provided", "provider_app": ["in", list(apps_set)]},
                fields=["name", "skill_name", "provider_app"],
            )
            skills_to_remove = [
                skill
                for skill in existing_skills
                if skill.skill_name not in valid_skill_names or skill.provider_app in apps_set
            ]

        for skill in skills_to_remove:
            try:
                frappe.delete_doc(SKILL_DOCTYPE, skill.name, ignore_permissions=True, force=True)
            except Exception as e:
                errors.append(
                    f"Failed to delete orphaned skill '{skill.skill_name}': {str(e)}"
                )
                frappe.log_error(
                    f"Failed to delete orphaned skill '{skill.skill_name}': {str(e)}",
                    "Skill Sync Error",
                )
    except Exception as e:
        errors.append(f"Failed to cleanup orphaned skills: {str(e)}")
        frappe.log_error(f"Failed to cleanup orphaned skills: {str(e)}", "Skill Sync Error")

    if errors:
        frappe.log_error(
            f"Skill sync completed with {len(errors)} error(s). Synced {synced_count} skills successfully.\n"
            f"Errors:\n" + "\n".join(errors[:20]),
            "Skill Sync Errors",
        )

    return {
        "synced_apps": list(skills_by_app.keys()),
        "total_skills": synced_count,
        "errors": errors[:50] if errors else [],
        "error_count": len(errors),
    }
