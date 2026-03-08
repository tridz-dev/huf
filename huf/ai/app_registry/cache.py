# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - cache management for definition scans

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import frappe
from frappe.utils import now_datetime

CACHE_DOCTYPE = "Agent Settings"
CACHE_FIELD = "last_definition_scans"


def _get_cache() -> dict:
	"""Get the last_definition_scans cache from Agent Settings."""
	try:
		if not frappe.db.exists("DocType", CACHE_DOCTYPE):
			return {}
		settings = frappe.get_single(CACHE_DOCTYPE)
		if hasattr(settings, CACHE_FIELD) and settings.get(CACHE_FIELD):
			return json.loads(settings[CACHE_FIELD])
	except Exception:
		pass
	return {}


def _set_cache(cache: dict) -> None:
	"""Update the last_definition_scans cache in Agent Settings."""
	try:
		if not frappe.db.exists("DocType", CACHE_DOCTYPE):
			return
		settings = frappe.get_single(CACHE_DOCTYPE)
		if hasattr(settings, CACHE_FIELD):
			settings[CACHE_FIELD] = json.dumps(cache)
			settings.save(ignore_permissions=True)
	except Exception:
		pass


def compute_file_hash(huf_dir: str, definitions: dict[str, list[str]]) -> str:
	"""
	Compute a combined hash of all definition file paths and modification times.

	Args:
		huf_dir: Base huf/ directory path
		definitions: dict from scan_app (type -> list of file paths)

	Returns:
		Hex digest of the combined hash.
	"""
	hasher = hashlib.sha256()
	for type_dir in sorted(definitions.keys()):
		for fp in sorted(definitions[type_dir]):
			rel = os.path.relpath(fp, huf_dir) if fp.startswith(huf_dir) else fp
			try:
				mtime = os.path.getmtime(fp)
				hasher.update(f"{rel}:{mtime}\n".encode("utf-8"))
			except OSError:
				hasher.update(f"{rel}:0\n".encode("utf-8"))
	return hasher.hexdigest()


def should_scan_app(app_name: str, huf_dir: str, definitions: dict) -> bool:
	"""
	Determine if an app needs a full scan based on cache and file hash.

	Args:
		app_name: App name
		huf_dir: Path to huf/ directory
		definitions: Result of scan_app

	Returns:
		True if the app should be scanned (cache miss or files changed).
	"""
	cache = _get_cache()
	entry = cache.get(app_name)
	if not entry:
		return True

	file_hash = compute_file_hash(huf_dir, definitions)
	return entry.get("file_hash") != file_hash


def update_scan_cache(app_name: str, huf_dir: str, definitions: dict) -> None:
	"""
	Update the cache after a successful scan.

	Args:
		app_name: App name
		huf_dir: Path to huf/ directory
		definitions: Result of scan_app
	"""
	cache = _get_cache()
	cache[app_name] = {
		"timestamp": now_datetime().isoformat(),
		"file_hash": compute_file_hash(huf_dir, definitions),
	}
	_set_cache(cache)


def clear_scan_cache(app_name: str | None = None) -> None:
	"""
	Clear the scan cache for an app or all apps.

	Args:
		app_name: If provided, clear only this app. Otherwise clear all.
	"""
	cache = _get_cache()
	if app_name:
		cache.pop(app_name, None)
	else:
		cache.clear()
	_set_cache(cache)
