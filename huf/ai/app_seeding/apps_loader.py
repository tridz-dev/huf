"""
HUF App manifest loader.

Discovers flat ``*.json`` manifests under ``<installed_app>/huf/apps/``,
validates them against the MVP manifest grammar (see HUF_APPS_MVP.md §6/§8.3)
and syncs them into the ``HUF App`` registry DocType.

Provenance fields (``source_app``, ``source_file``, ``manifest_hash`` and all
sync state) are always derived here, never trusted from the manifest JSON.
"""
import hashlib
import json
import re
from pathlib import Path

import frappe

from .scanner import find_seed_dirs, get_seed_files

APPS_FOLDER = "apps"

SUPPORTED_MANIFEST_VERSION = 1

APP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_\-]*$")
ICON_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]*$")
URL_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

# Documented default launcher categories. Custom categories are allowed (only
# shape-checked) but noted at sync time; see _nonstandard_category_note.
DEFAULT_CATEGORIES = (
	"Create",
	"Plan",
	"Research",
	"Automate",
	"Analyze",
	"Communicate",
	"Manage",
	"Other",
)
CATEGORY_MAX_LENGTH = 30
MAX_EXPOSED_TABLES = 20

# Top-level fields a manifest may declare. Anything else (including
# provenance/sync fields such as source_app or manifest_hash) is rejected.
ALLOWED_FIELDS = {
	"manifest_version",
	"app_id",
	"title",
	"description",
	"version",
	"route",
	"icon",
	"category",
	"launch_mode",
	"required_huf_version",
	"permission_method",
	"sort_order",
	"enabled",
	"exposed_tables",
}

STRING_FIELDS = (
	"app_id",
	"title",
	"description",
	"version",
	"route",
	"icon",
	"category",
	"required_huf_version",
	"permission_method",
)


def _is_int(value) -> bool:
	return isinstance(value, int) and not isinstance(value, bool)


def _validate_route(route) -> str | None:
	"""Return an error message if the route is not a site-local path."""
	if not route.startswith("/"):
		return "route must be an absolute site-local path beginning with '/'"
	if route.startswith("//"):
		return "route must begin with exactly one '/' (protocol-relative URLs are not allowed)"
	if "://" in route or URL_SCHEME_PATTERN.search(route):
		return "route must not contain a URL scheme (external URLs are not allowed)"
	return None


def _validate_icon(icon) -> str | None:
	"""Return an error message if the icon is neither a site-local asset
	path nor a plain icon identifier."""
	if icon.startswith("/"):
		if icon.startswith("//") or "://" in icon:
			return "icon must be a site-local asset path, not an external URL"
		return None
	if URL_SCHEME_PATTERN.search(icon):
		return "icon must not contain a URL scheme"
	if not ICON_NAME_PATTERN.match(icon):
		return "icon must be a site-local asset path or a simple icon identifier"
	return None


def _validate_permission_method(path) -> str | None:
	"""Return an error message unless the dotted path belongs to an installed
	app and resolves to a callable."""
	if "." not in path:
		return "permission_method must be a dotted Python path"
	root_module = path.split(".", 1)[0]
	if root_module not in frappe.get_installed_apps():
		return f"permission_method module '{root_module}' is not an installed app"
	try:
		fn = frappe.get_attr(path)
	except Exception as e:
		return f"permission_method '{path}' could not be imported: {e}"
	if not callable(fn):
		return f"permission_method '{path}' does not resolve to a callable"
	return None


def _validate_category(category) -> str | None:
	"""Return an error message if the category has an invalid shape.

	Only the shape is enforced (single line, no HTML, length cap); custom
	categories are accepted and merely noted at sync time.
	"""
	if "\n" in category or "\r" in category:
		return "category must be a single line"
	if len(category) > CATEGORY_MAX_LENGTH:
		return f"category must be at most {CATEGORY_MAX_LENGTH} characters"
	if "<" in category or ">" in category:
		return "category must not contain HTML"
	return None


def _validate_exposed_tables_shape(value) -> str | None:
	"""Return an error message unless exposed_tables is a list of at most
	MAX_EXPOSED_TABLES single-line DocType name strings."""
	if not isinstance(value, list) or len(value) > MAX_EXPOSED_TABLES:
		return f"exposed_tables must be a list of at most {MAX_EXPOSED_TABLES} DocType names"
	for table in value:
		if not isinstance(table, str) or not table.strip() or "\n" in table or "\r" in table:
			return "exposed_tables entries must be single-line DocType name strings"
	return None


def _get_module_app(module: str) -> str | None:
	"""App that owns the given Module Def (seam for tests)."""
	return frappe.db.get_value("Module Def", module, "app_name")


def _get_doctype_module(doctype: str) -> str:
	"""Module of an existing DocType; raises for unknown ones (seam for tests)."""
	return frappe.get_meta(doctype).module


def get_doctype_owner_app(doctype: str) -> str | None:
	"""App that owns the given DocType via its Module Def.

	Returns None if the DocType does not exist or its module has no
	registered app_name. Public, reusable ownership lookup (see
	huf.ai.capabilities.apps.app_owns_doctype).
	"""
	try:
		module = _get_doctype_module(doctype)
	except Exception:
		return None
	return _get_module_app(module)


def _validate_exposed_tables(tables: list, source_app: str) -> str | None:
	"""Return an error message unless every exposed table is an existing
	DocType whose module belongs to the provider app. Never raises."""
	for table in tables:
		try:
			module = _get_doctype_module(table)
		except Exception:
			return f"exposed_tables references unknown DocType '{table}'"
		owner_app = _get_module_app(module)
		if owner_app != source_app:
			return (
				f"exposed_tables DocType '{table}' is owned by app "
				f"'{owner_app}', not provider app '{source_app}'"
			)
	return None


def _nonstandard_category_note(app_id: str, category: str) -> str | None:
	"""Info note for accepted categories outside the documented defaults."""
	if category in DEFAULT_CATEGORIES:
		return None
	return f"HUF App '{app_id}' declares non-standard category '{category}'"


def validate_manifest(data) -> tuple:
	"""
	Validate a raw manifest dict against the MVP grammar.

	Returns (normalized_manifest, None) on success or (None, error_message).
	The normalized manifest has defaults applied and launch_mode normalized to
	the DocType Select value ("Route").
	"""
	if not isinstance(data, dict):
		return None, "manifest must be a JSON object"

	unknown = sorted(set(data) - ALLOWED_FIELDS)
	if unknown:
		return None, f"unknown top-level field(s): {', '.join(unknown)}"

	if data.get("manifest_version") != SUPPORTED_MANIFEST_VERSION or not _is_int(data.get("manifest_version")):
		return None, f"manifest_version must be the integer {SUPPORTED_MANIFEST_VERSION}"

	for field in STRING_FIELDS:
		if field in data and not isinstance(data[field], str):
			return None, f"{field} must be a string"

	app_id = (data.get("app_id") or "").strip()
	if not app_id:
		return None, "app_id is required"
	if not APP_ID_PATTERN.match(app_id):
		return None, "app_id must match ^[a-z][a-z0-9_\\-]*$"

	title = (data.get("title") or "").strip()
	if not title:
		return None, "title is required"

	route = (data.get("route") or "").strip()
	if not route:
		return None, "route is required"
	if error := _validate_route(route):
		return None, error

	icon = (data.get("icon") or "").strip()
	if icon:
		if error := _validate_icon(icon):
			return None, error

	category = (data.get("category") or "").strip()
	if category:
		if error := _validate_category(category):
			return None, error

	exposed_tables = data.get("exposed_tables", [])
	if error := _validate_exposed_tables_shape(exposed_tables):
		return None, error

	launch_mode = data.get("launch_mode", "route")
	if not isinstance(launch_mode, str) or launch_mode.lower() != "route":
		return None, "launch_mode must be 'route'"

	if "sort_order" in data and not _is_int(data["sort_order"]):
		return None, "sort_order must be an integer"

	if "enabled" in data and not isinstance(data["enabled"], bool):
		return None, "enabled must be a boolean"

	permission_method = (data.get("permission_method") or "").strip()
	if permission_method:
		if error := _validate_permission_method(permission_method):
			return None, error

	normalized = {
		"app_id": app_id,
		"title": title,
		"description": (data.get("description") or "").strip(),
		"version": (data.get("version") or "").strip(),
		"route": route,
		"icon": icon,
		"category": category or "Other",
		"launch_mode": "Route",
		"required_huf_version": (data.get("required_huf_version") or "").strip(),
		"permission_method": permission_method,
		"sort_order": data.get("sort_order", 100),
		"enabled": 1 if data.get("enabled", True) else 0,
		# Stored on the DocType as a comma-joined string.
		"exposed_tables": ",".join(t.strip() for t in exposed_tables),
	}
	return normalized, None


def compute_manifest_hash(normalized: dict) -> str:
	"""sha256 over the normalized manifest, used to skip unchanged writes."""
	payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_huf_app(data: dict, source_app: str, source_file: str) -> tuple:
	"""
	Loader for the seeding LOAD_ORDER. Validates one manifest and inserts or
	updates the matching ``HUF App`` registry record keyed by ``app_id``.

	Returns (True, None) on success, (False, error_message) otherwise. Invalid
	manifests are still recorded (sync_status="Invalid") when a usable app_id
	is present, so System Managers can see what failed and why.
	"""
	normalized, error = validate_manifest(data)
	if error:
		_record_invalid_manifest(data, error, source_app, source_file)
		return False, error

	# DocType existence/ownership can only be checked against the live site.
	tables = [t for t in normalized["exposed_tables"].split(",") if t]
	if error := _validate_exposed_tables(tables, source_app):
		_record_invalid_manifest(data, error, source_app, source_file)
		return False, error

	app_id = normalized["app_id"]
	manifest_hash = compute_manifest_hash(normalized)

	if note := _nonstandard_category_note(app_id, normalized["category"]):
		frappe.logger().info(note)

	existing = frappe.db.get_value(
		"HUF App",
		app_id,
		["source_app", "manifest_hash", "sync_status"],
		as_dict=True,
	)

	if existing and existing.source_app and existing.source_app != source_app:
		note = (
			f"Duplicate app_id '{app_id}': already registered by app "
			f"'{existing.source_app}'; manifest from app '{source_app}' "
			f"({source_file}) was rejected."
		)
		frappe.log_error(note, "HUF App Registration Collision")
		# Surface the collision on the registry without overwriting the
		# existing valid registration.
		frappe.db.set_value("HUF App", app_id, "sync_error", note, update_modified=False)
		return False, note

	now = frappe.utils.now_datetime()
	values = {
		**normalized,
		"source_app": source_app,
		"source_file": source_file,
		"manifest_hash": manifest_hash,
		"last_synced_at": now,
		"sync_status": "Active",
		"sync_error": "",
	}

	# Skip the write entirely when nothing changed.
	if (
		existing
		and existing.manifest_hash == manifest_hash
		and existing.sync_status == "Active"
	):
		return True, None

	try:
		if existing:
			# Manual-disable-wins: the manifest's enabled applies only when
			# inserting a new record; updates never touch the stored flag
			# (an admin may have disabled the app manually).
			values.pop("enabled", None)
			doc = frappe.get_doc("HUF App", app_id)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "HUF App", **values}).insert(ignore_permissions=True)
		return True, None
	except Exception as e:
		return False, str(e)


def _record_invalid_manifest(data, error: str, source_app: str, source_file: str) -> None:
	"""Best-effort registry record for an invalid manifest.

	Only possible when the manifest still carries a usable app_id (the
	registry is keyed by it); otherwise the failure is only logged.
	"""
	frappe.log_error(
		f"Invalid HUF App manifest in {source_file} from app '{source_app}': {error}",
		"HUF App Sync",
	)
	if not isinstance(data, dict):
		return
	app_id = data.get("app_id")
	if not isinstance(app_id, str) or not APP_ID_PATTERN.match(app_id.strip()):
		return
	app_id = app_id.strip()
	try:
		# Never let an invalid manifest claim another provider's app_id.
		existing_app = frappe.db.get_value("HUF App", app_id, "source_app")
		if existing_app and existing_app != source_app:
			return
		title = data.get("title")
		route = data.get("route")
		values = {
			"title": title.strip() if isinstance(title, str) and title.strip() else app_id,
			"route": route.strip() if isinstance(route, str) and route.strip() and not _validate_route(route.strip()) else "/",
			"enabled": 0,
			"source_app": source_app,
			"source_file": source_file,
			"manifest_hash": "",
			"last_synced_at": frappe.utils.now_datetime(),
			"sync_status": "Invalid",
			"sync_error": error,
		}
		if frappe.db.exists("HUF App", app_id):
			doc = frappe.get_doc("HUF App", app_id)
			doc.update(values)
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({"doctype": "HUF App", "app_id": app_id, **values}).insert(
				ignore_permissions=True
			)
	except Exception as e:
		frappe.log_error(
			f"Failed to record invalid HUF App manifest '{app_id}': {e}",
			"HUF App Sync",
		)


def cleanup_orphaned_apps(seen: set | None = None) -> list:
	"""
	Delete registry records whose provider app is no longer installed or whose
	source manifest file was not seen during discovery (MVP: delete, do not
	mark Missing).

	``seen`` is a set of (source_app, source_file) pairs discovered during the
	current sync run. When None, every record from an installed app is treated
	as seen unless its source app was uninstalled.
	Returns the list of deleted app_ids.
	"""
	installed_apps = set(frappe.get_installed_apps())
	deleted = []
	records = frappe.get_all(
		"HUF App",
		fields=["name", "app_id", "source_app", "source_file"],
	)
	for record in records:
		orphaned = record.source_app not in installed_apps
		if not orphaned and seen is not None:
			orphaned = (record.source_app, record.source_file) not in seen
		if not orphaned:
			continue
		try:
			frappe.delete_doc("HUF App", record.name, ignore_permissions=True, force=True)
			deleted.append(record.app_id or record.name)
		except Exception as e:
			frappe.log_error(
				f"Failed to delete orphaned HUF App '{record.name}': {e}",
				"HUF App Sync",
			)
	return deleted


def sync_huf_apps() -> dict:
	"""
	Full registry sync: discover every ``huf/apps/`` manifest across installed
	apps, upsert valid ones, record invalid ones, then delete orphaned
	registry records. Commits one provider app at a time so a single failure
	does not roll back other registrations.
	"""
	summary = {
		"synced": 0,
		"invalid": 0,
		"deleted": 0,
		"errors": [],
		"deleted_apps": [],
		"notes": [],
	}
	seen = set()

	for app_name, huf_dir in find_seed_dirs().items():
		try:
			for file_path in sorted(get_seed_files(huf_dir, APPS_FOLDER), key=lambda p: p.name):
				source_file = f"huf/{APPS_FOLDER}/{file_path.name}"
				try:
					with open(file_path, "r", encoding="utf-8") as f:
						data = json.load(f)
				except Exception as e:
					summary["invalid"] += 1
					summary["errors"].append(
						{"app": app_name, "file": source_file, "error": f"Error parsing manifest: {e}"}
					)
					frappe.log_error(
						f"Error parsing HUF App manifest {file_path}: {e}",
						"HUF App Sync",
					)
					continue

				seen.add((app_name, source_file))
				items = data if isinstance(data, list) else [data]
				for item in items:
					ok, error = upsert_huf_app(item, app_name, source_file)
					if ok:
						summary["synced"] += 1
						if isinstance(item, dict):
							category = (item.get("category") or "").strip() or "Other"
							if note := _nonstandard_category_note(item.get("app_id"), category):
								summary["notes"].append(note)
					else:
						summary["invalid"] += 1
						summary["errors"].append(
							{"app": app_name, "file": source_file, "error": str(error)}
						)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			summary["errors"].append({"app": app_name, "file": None, "error": str(e)})
			frappe.log_error(
				f"HUF App sync failed for provider app '{app_name}': {e}",
				"HUF App Sync",
			)

	deleted = cleanup_orphaned_apps(seen)
	summary["deleted"] = len(deleted)
	summary["deleted_apps"] = deleted
	frappe.db.commit()
	return summary


def on_app_uninstalled(app_name):
	"""Hook for after_app_uninstall: remove registry entries of the provider
	app that was just uninstalled."""
	try:
		records = frappe.get_all(
			"HUF App",
			filters={"source_app": app_name},
			pluck="name",
		)
		for name in records:
			frappe.delete_doc("HUF App", name, ignore_permissions=True, force=True)
		if records:
			frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			f"Error removing HUF App registry entries for uninstalled app '{app_name}': {e}",
			"HUF App Sync",
		)
