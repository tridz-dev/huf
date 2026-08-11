"""Installed Frappe app enumeration and HUF App manifest lookup."""
import frappe

from ..app_seeding.apps_loader import get_doctype_owner_app


def get_capability_apps() -> list:
	"""Return one dict per installed Frappe app, describing its display
	title and HUF App manifest status (if any)."""
	apps = []
	for app in frappe.get_installed_apps():
		huf_app_id, has_manifest = _get_huf_app_status(app)
		apps.append({
			"app": app,
			"title": _get_app_title(app),
			"huf_app_id": huf_app_id,
			"has_manifest": has_manifest,
		})
	return apps


def _get_app_title(app: str) -> str:
	hooked = frappe.get_hooks("app_title", app_name=app)
	title = hooked[0] if isinstance(hooked, (list, tuple)) and hooked else hooked
	if isinstance(title, str) and title.strip():
		return title.strip()
	return app.replace("_", " ").title()


def _get_huf_app_status(app: str) -> tuple:
	name = frappe.db.get_value("HUF App", {"source_app": app}, "name")
	if not name:
		return None, False
	exposed_tables = frappe.db.get_value("HUF App", name, "exposed_tables")
	return name, bool(exposed_tables and exposed_tables.strip())


def app_owns_doctype(app_name: str, doctype_name: str) -> bool:
	"""Whether doctype_name's Module Def belongs to app_name."""
	return get_doctype_owner_app(doctype_name) == app_name
