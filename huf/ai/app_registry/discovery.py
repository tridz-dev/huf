# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - orchestration and public API

from __future__ import annotations

import os

import frappe

from huf.ai.app_registry.cache import clear_scan_cache, update_scan_cache
from huf.ai.app_registry.importer import import_definition
from huf.ai.app_registry.loader import (
	FOLDER_TO_TYPE,
	KNOWN_TYPES,
	get_huf_dir_for_app,
	load_definition,
	scan_app,
)
from huf.ai.app_registry.normaliser import normalise
from huf.ai.app_registry.validator import validate

# Dependency order: providers, models, prompts, tools, knowledge, agents, triggers
IMPORT_ORDER = [
	"providers",
	"models",
	"prompts",
	"tools",
	"knowledge",
	"agents",
	"triggers",
]


def _relative_source_file(file_path: str, app_name: str) -> str:
	"""Build relative path like 'crm/huf/tools/create_lead.tool.json'."""
	app_path = frappe.get_app_path(app_name)
	# Go up from app package to app root (e.g. crm/crm -> crm)
	app_root = os.path.dirname(app_path)
	try:
		return os.path.relpath(file_path, app_root)
	except ValueError:
		return file_path


def _import_app_definitions(
	app_name: str,
	huf_dir: str,
	definitions: dict[str, list[str]],
	*,
	use_cache: bool = True,
) -> tuple[int, list[str], list[str]]:
	"""
	Import all definitions from an app.

	Returns:
		(count, errors, warnings)
	"""
	count = 0
	errors: list[str] = []
	warnings: list[str] = []

	for type_dir in IMPORT_ORDER:
		files = definitions.get(type_dir, [])
		singular = FOLDER_TO_TYPE.get(type_dir, type_dir.rstrip("s"))

		for file_path in files:
			data = load_definition(file_path, type_dir)
			if data is None:
				errors.append(f"{app_name}: {_relative_source_file(file_path, app_name)}: Invalid JSON or type mismatch")
				continue

			result = validate(data, singular)
			if not result.is_valid:
				for e in result.errors:
					errors.append(f"{app_name}: {_relative_source_file(file_path, app_name)}: {e}")
				continue

			for w in result.warnings:
				warnings.append(f"{app_name}: {_relative_source_file(file_path, app_name)}: {w}")

			try:
				source_file = _relative_source_file(file_path, app_name)
				payload = normalise(data, singular, app_name, source_file)
				doc_name = import_definition(singular, payload, skip_sensitive=(singular == "provider"))
				if doc_name:
					count += 1
			except Exception as e:
				errors.append(f"{app_name}: {_relative_source_file(file_path, app_name)}: {e}")
				frappe.log_error(
					f"Failed to import {file_path} from {app_name}: {e}",
					"HUF App Discovery",
				)

	return count, errors, warnings


def discover_app_definitions(app_name: str | None = None, *, use_cache: bool = False) -> dict:
	"""
	Discover and sync AI definitions from installed apps.

	Args:
		app_name: If provided, only scan this app. Otherwise scan all installed apps.
		use_cache: If True, skip apps whose definition files haven't changed.

	Returns:
		dict with keys: synced_apps, total_definitions, by_type, errors, error_count, warnings, warning_count
	"""
	synced_apps: list[str] = []
	by_type: dict[str, int] = {}
	all_errors: list[str] = []
	all_warnings: list[str] = []
	total = 0

	apps_to_scan = [app_name] if app_name else frappe.get_installed_apps()

	for app in apps_to_scan:
		huf_dir = get_huf_dir_for_app(app)
		if not huf_dir:
			continue

		definitions = scan_app(app, huf_dir)
		if not definitions:
			continue

		if use_cache:
			from huf.ai.app_registry.cache import should_scan_app

			if not should_scan_app(app, huf_dir, definitions):
				continue

		count, errs, warns = _import_app_definitions(app, huf_dir, definitions, use_cache=use_cache)
		total += count
		synced_apps.append(app)
		all_errors.extend(errs)
		all_warnings.extend(warns)

		for type_dir, files in definitions.items():
			by_type[type_dir] = by_type.get(type_dir, 0) + len(files)

		if count > 0:
			update_scan_cache(app, huf_dir, definitions)

	return {
		"synced_apps": synced_apps,
		"total_definitions": total,
		"by_type": by_type,
		"errors": all_errors[:50],
		"error_count": len(all_errors),
		"warnings": all_warnings[:20],
		"warning_count": len(all_warnings),
	}


@frappe.whitelist()
def discover_app_definitions_api(app_name: str | None = None, use_cache: bool = False) -> dict:
	"""
	Whitelisted API for discovering and syncing app definitions.

	Args:
		app_name: Optional. If provided, only sync this app.
		use_cache: If True, skip apps whose files haven't changed.

	Returns:
		Sync result dict.
	"""
	return discover_app_definitions(app_name=app_name, use_cache=use_cache)


@frappe.whitelist()
def get_app_discovery_status() -> list[dict]:
	"""
	Return discovery status for all installed apps.

	Returns list of:
		{
			"app": str,
			"has_huf_dir": bool,
			"definition_counts": dict,
			"last_sync": str | None,
			"files": list[str],
		}
	"""
	from huf.ai.app_registry.cache import _get_cache

	cache = _get_cache()
	result = []

	for app in frappe.get_installed_apps():
		huf_dir = get_huf_dir_for_app(app)
		entry = {
			"app": app,
			"has_huf_dir": huf_dir is not None,
			"definition_counts": {},
			"last_sync": None,
			"files": [],
		}

		if huf_dir:
			definitions = scan_app(app, huf_dir)
			for type_dir, files in definitions.items():
				entry["definition_counts"][type_dir] = len(files)
				for fp in files:
					entry["files"].append(_relative_source_file(fp, app))

			cache_entry = cache.get(app, {})
			entry["last_sync"] = cache_entry.get("timestamp")

		result.append(entry)

	return result


@frappe.whitelist()
def rebuild_app_definitions() -> dict:
	"""
	Clear all provenance cache and re-import everything from scratch.
	"""
	clear_scan_cache()
	return discover_app_definitions(use_cache=False)
