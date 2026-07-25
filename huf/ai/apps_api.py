"""
Permission-aware launcher API for discovered HUF Apps.

Security boundaries (HUF_APPS_MVP.md §8.5/§13):
  - only safe launcher fields are ever returned to non-System-Managers
    (never permission_method, source_file, manifest_hash or sync_error);
  - visibility is evaluated server-side per record;
  - a hidden app fails exactly like a nonexistent one.
"""
import frappe
from frappe import _

from huf.permissions import ADMINISTRATOR, SYSTEM_MANAGER, has_capability

# Fields that are safe to expose to any permitted user.
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
		frappe.log_error(f"Could not import permission_method '{path}': {e}", "HUF Apps API")
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
			frappe.log_error(f"permission_method '{path}' raised: {e}", "HUF Apps API")
			return False

	frappe.log_error(
		f"permission_method '{path}' has an unsupported signature", "HUF Apps API"
	)
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


def _safe_app_dict(record: dict) -> dict:
	return {field: record.get(field) for field in SAFE_FIELDS}


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
			"permission_method",
			"sync_status",
			"sort_order",
		],
		order_by="sort_order asc, title asc",
	)

	apps = [_safe_app_dict(r) for r in records if _can_user_see(r, user)]
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
				"permission_method",
				"sync_status",
			],
			as_dict=True,
		)

	if not record or not _can_user_see(record, user):
		frappe.throw(_("HUF App {0} not found").format(app_id), frappe.DoesNotExistError)

	return _safe_app_dict(record)


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
