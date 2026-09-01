"""
Permission-aware launcher API for discovered HUF Apps.

Security boundaries (HUF_APPS_MVP.md §8.5/§13):
  - only safe launcher fields are ever returned to non-System-Managers
    (never permission_method, source_file, manifest_hash or sync_error);
  - visibility is evaluated server-side per record;
  - a hidden app fails exactly like a nonexistent one.

Note for app developers (known behavior, not a bug): agent runs are
graceful-error tolerant — a run can return success while carrying an error
text payload (see run_agent_sync), so providers should surface the payload,
not just the status.
"""
import frappe
from frappe import _

from huf.permissions import ADMINISTRATOR, SYSTEM_MANAGER, has_capability

# Fields that are safe to expose to any permitted user. exposed_tables is
# also safe (it reveals only DocType names the provider explicitly
# published), but is stored comma-joined and shaped as a list on output;
# see _safe_app_dict.
SAFE_FIELDS = ("app_id", "title", "description", "route", "icon", "category", "version")

# Capability required to see apps that declare no permission_method.
BASE_ACCESS_CAPABILITY = "agent.use"


def _is_system_manager(user: str) -> bool:
	return user == ADMINISTRATOR or SYSTEM_MANAGER in frappe.get_roles(user)


def _call_permission_method(path: str, user: str, app_meta: dict) -> bool:
	"""Call the provider's permission_method with the current user and
	registry metadata. Fails closed: any error hides the app."""
	try:
		fn = frappe.get_attr(path)
	except Exception as e:
		frappe.log_error(title="HUF Apps API", message=f"Could not import permission_method '{path}': {e}")
		return False

	for args, kwargs in (
		((), {"user": user, "app": app_meta}),
		((user,), {}),
		((), {}),
	):
		try:
			return bool(fn(*args, **kwargs))
		except TypeError:
			continue
		except Exception as e:
			frappe.log_error(title="HUF Apps API", message=f"permission_method '{path}' raised: {e}")
			return False

	frappe.log_error(title="HUF Apps API", message=f"permission_method '{path}' has an unsupported signature")
	return False


def _can_user_see(record: dict, user: str) -> bool:
	"""Visibility rules from the spec, in order."""
	if record.get("sync_status") != "Active":
		return False

	# 1. Administrator/System Manager see all valid registrations.
	if _is_system_manager(user):
		return True

	# 2. Disabled registrations are hidden from normal users.
	if not record.get("enabled"):
		return False

	# 3. Provider-declared permission_method wins when present.
	permission_method = record.get("permission_method")
	if permission_method:
		return _call_permission_method(permission_method, user, record)

	# 4. Otherwise require an authenticated user with base HUF access.
	if not user or user == "Guest":
		return False
	return has_capability(user, BASE_ACCESS_CAPABILITY)


def _split_exposed_tables(value) -> list:
	"""Comma-joined registry string -> list of DocType names."""
	if not value:
		return []
	return [table.strip() for table in value.split(",") if table.strip()]


def _safe_app_dict(record: dict, system_manager: bool = False, detail: bool = False) -> dict:
	"""Shape a registry record for output.

	exposed_tables (as a list) goes to any permitted user on the detail
	endpoint, and to System Managers on the list endpoint. enabled is only
	ever exposed to System Manager/Administrator requests.
	"""
	app = {field: record.get(field) for field in SAFE_FIELDS}
	if detail or system_manager:
		app["exposed_tables"] = _split_exposed_tables(record.get("exposed_tables"))
	if system_manager:
		app["enabled"] = 1 if record.get("enabled") else 0
	return app


@frappe.whitelist()
def get_huf_apps() -> dict:
	"""
	GET /api/method/huf.ai.apps_api.get_huf_apps

	Returns only the applications the current user may open, with safe
	launcher fields only, ordered for the launcher.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		return {"apps": []}

	system_manager = _is_system_manager(user)
	records = frappe.get_all(
		"HUF App",
		fields=[
			"app_id",
			"title",
			"description",
			"route",
			"icon",
			"category",
			"version",
			"enabled",
			"exposed_tables",
			"permission_method",
			"sync_status",
			"sort_order",
		],
		order_by="sort_order asc, title asc",
	)

	apps = [
		_safe_app_dict(r, system_manager=system_manager)
		for r in records
		if _can_user_see(r, user)
	]
	return {"apps": apps}


@frappe.whitelist()
def get_huf_app(app_id: str) -> dict:
	"""
	GET /api/method/huf.ai.apps_api.get_huf_app

	Returns a single app the current user may open. Apps that do not exist
	or are not permitted fail identically with DoesNotExistError.
	"""
	user = frappe.session.user
	record = None
	if user and user != "Guest" and app_id:
		record = frappe.db.get_value(
			"HUF App",
			app_id,
			[
				"app_id",
				"title",
				"description",
				"route",
				"icon",
				"category",
				"version",
				"enabled",
				"exposed_tables",
				"permission_method",
				"sync_status",
			],
			as_dict=True,
		)

	if not record or not _can_user_see(record, user):
		frappe.throw(_("HUF App {0} not found").format(app_id), frappe.DoesNotExistError)

	return _safe_app_dict(record, system_manager=_is_system_manager(user), detail=True)


@frappe.whitelist()
def sync_huf_apps() -> dict:
	"""
	POST /api/method/huf.ai.apps_api.sync_huf_apps  (System Manager only)

	Runs the full registry sync and returns a summary of synced/invalid/
	deleted counts and per-app errors.
	"""
	frappe.only_for(SYSTEM_MANAGER)

	from huf.ai.app_seeding.apps_loader import sync_huf_apps as _sync

	return _sync()


def _parse_truthy(value) -> bool:
	"""Parse an enabled flag from JSON/bool/int/string payloads."""
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


@frappe.whitelist()
def set_huf_app_enabled(app_id: str, enabled) -> dict:
	"""
	POST /api/method/huf.ai.apps_api.set_huf_app_enabled  (System Manager only)

	Manually enables/disables a registry record. The stored flag wins over
	the manifest on subsequent syncs (manual-disable-wins).
	"""
	frappe.only_for(SYSTEM_MANAGER)

	if not app_id or not frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App {0} not found").format(app_id), frappe.DoesNotExistError)

	flag = _parse_truthy(enabled)
	frappe.db.set_value("HUF App", app_id, "enabled", 1 if flag else 0)
	return {"ok": True, "app_id": app_id, "enabled": flag}
