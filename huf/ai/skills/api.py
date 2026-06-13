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

from huf.ai.skills.exporter import download_skill_huf as _download_skill_huf
from huf.ai.skills.hooks import sync_app_skills as _sync_app_skills
from huf.ai.skills.importer import (
	DEFAULT_DESTINATIONS,
	fetch_skill_registry as _fetch_skill_registry,
	import_skill_from_common_destination as _import_skill_from_common_destination,
	import_skill_from_git as _import_skill_from_git,
	import_skill_from_huf as _import_skill_from_huf,
	import_skill_from_registry as _import_skill_from_registry,
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
def import_skill_from_huf(file_url: str) -> dict[str, Any]:
	"""Whitelisted wrapper around ``huf.ai.skills.importer.import_skill_from_huf``."""
	return _import_skill_from_huf(file_url=file_url)


@frappe.whitelist()
def import_skill_from_registry(
	repo_url: str,
	skill_name: str | None = None,
	path: str = "skills",
	ref: str = "main",
) -> dict[str, Any]:
	"""Whitelisted wrapper around ``huf.ai.skills.importer.import_skill_from_registry``."""
	return _import_skill_from_registry(
		repo_url=repo_url, skill_name=skill_name, path=path, ref=ref
	)


@frappe.whitelist()
def fetch_skill_registry(repo_url: str, ref: str = "main", path: str = "_index.json") -> dict[str, Any]:
	"""Fetch a remote skill registry ``_index.json``."""
	return _fetch_skill_registry(repo_url=repo_url, ref=ref, path=path)


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


@frappe.whitelist()
def get_skill_destinations() -> list[dict[str, Any]]:
	"""Return configured common skill destinations for the import UI.

	The default ``tridz-dev/huf-skills`` destination is always included; user
	destinations from ``Agent Settings.skill_destinations`` are merged on top.
	"""
	from huf.ai.skills.importer import _get_common_destinations

	destinations = _get_common_destinations()
	return [
		{"name": name, **config}
		for name, config in destinations.items()
	]


@frappe.whitelist()
def download_skill_huf(skill_name: str):
	"""Download a Skill as a ``.huf`` archive."""
	return _download_skill_huf(skill_name=skill_name)
