"""
huf/permissions.py

Huf capability-based permission layer.

Mental model
------------
  Huf Role  →  set of capabilities  (e.g. "agent.create", "flows.use")
  Huf User Role  →  user gets one Huf Role
  Frappe Role  →  real DocType-level enforcement underneath

Public API
----------
  has_capability(user, capability) -> bool
  get_user_capabilities(user)      -> list[str]
  get_user_huf_role(user)          -> str | None
  check_app_permission()           -> bool          (Frappe add_to_apps_screen hook)
  get_me()                         -> dict          (whitelisted API for frontend)
"""

import frappe
from frappe import _

# ---------------------------------------------------------------------------
# Capability catalogue
# Every capability Huf understands is declared here.
# The value is a human-readable label used in the Roles UI.
# ---------------------------------------------------------------------------

CAPABILITIES: dict[str, str] = {
	# --- Agents ---
	"agent.use": "Use Agents",
	"agent.create": "Create Agents",
	"agent.edit": "Edit Agents",
	"agent.delete": "Delete Agents",
	"agent.view_all": "View All Agents",
	# --- Chat ---
	"chat.use": "Use Chat",
	"chat.view_own": "View Own Conversations",
	"chat.view_all": "View All Conversations",
	# --- Knowledge ---
	"knowledge.use": "Use Knowledge",
	"knowledge.create": "Create Knowledge",
	"knowledge.manage": "Manage Knowledge",
	# --- Tools ---
	"tools.use": "Use Tools",
	"tools.create": "Create Tools",
	"tools.manage": "Manage Tools",
	# --- Flows ---
	"flows.use": "Use Flows",
	"flows.create": "Create Flows",
	"flows.manage": "Manage Flows",
	# --- System ---
	"system.providers.manage": "Manage AI Providers",
	"system.models.manage": "Manage AI Models",
	"system.mcp.manage": "Manage MCP Servers",
	"system.integrations.manage": "Manage Integrations",
	"system.settings.manage": "Manage Settings",
	# --- Users & Roles ---
	"users.invite": "Invite Users",
	"users.manage": "Manage Users",
	"roles.manage": "Manage Roles",
}

# Capabilities granted to each default Huf Role.
# Used during installation to seed Huf Role Permission child rows.
DEFAULT_ROLE_CAPABILITIES: dict[str, list[str]] = {
	"Huf Admin": list(CAPABILITIES.keys()),  # everything
	"Huf Manager": [
		"agent.use",
		"agent.create",
		"agent.edit",
		"agent.delete",
		"agent.view_all",
		"chat.use",
		"chat.view_own",
		"chat.view_all",
		"knowledge.use",
		"knowledge.create",
		"knowledge.manage",
		"tools.use",
		"tools.create",
		"tools.manage",
		"flows.use",
		"flows.create",
		"flows.manage",
	],
	"Huf User": [
		"agent.use",
		"chat.use",
		"chat.view_own",
		"knowledge.use",
		"tools.use",
		"flows.use",
	],
	"Huf Viewer": [
		"agent.use",
		"chat.view_own",
	],
}

# Which Frappe Role backs each Huf Role.
# Huf Admin reuses the existing System Manager role.
HUF_ROLE_FRAPPE_ROLE_MAP: dict[str, str] = {
	"Huf Admin": "System Manager",
	"Huf Manager": "Huf Manager",
	"Huf User": "Huf User",
	"Huf Viewer": "Huf Viewer",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CACHE_KEY_PREFIX = "huf_user_capabilities"


def _cache_key(user: str) -> str:
	return f"{_CACHE_KEY_PREFIX}::{user}"


def _bust_cache(user: str) -> None:
	frappe.cache().delete_value(_cache_key(user))


def _is_system_manager(user: str) -> bool:
	return "System Manager" in frappe.get_roles(user)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_user_huf_role(user: str | None = None) -> str | None:
	"""Return the user's Huf Role name, or None if they have no Huf role."""
	if not user:
		user = frappe.session.user

	if user == "Administrator" or _is_system_manager(user):
		return "Huf Admin"

	huf_role = frappe.db.get_value(
		"Huf User Role",
		{"user": user, "enabled": 1},
		"huf_role",
	)
	if huf_role:
		return huf_role

	# Fallback: check standard Frappe Roles if no Huf User Role record exists
	user_roles = frappe.get_roles(user)
	if "Huf Manager" in user_roles:
		return "Huf Manager"
	if "Huf User" in user_roles:
		return "Huf User"
	if "Huf Viewer" in user_roles:
		return "Huf Viewer"

	return None


def get_user_capabilities(user: str | None = None) -> list[str]:
	"""
	Return the full list of capability strings for *user*.

	Result is cached per request (frappe.local.cache) so repeated
	calls within one request are free.
	"""
	if not user:
		user = frappe.session.user

	# Administrator / System Manager get every capability.
	if user == "Administrator" or _is_system_manager(user):
		return list(CAPABILITIES.keys())

	cached = frappe.cache().get_value(_cache_key(user))
	if cached is not None:
		return cached

	huf_role = get_user_huf_role(user)
	if not huf_role:
		result: list[str] = []
		frappe.cache().set_value(_cache_key(user), result, expires_in_sec=300)
		return result

	rows = frappe.get_all(
		"Huf Role Permission",
		filters={"parent": huf_role},
		fields=["capability"],
		ignore_permissions=True,
	)
	result = [r.capability for r in rows if r.capability in CAPABILITIES]
	frappe.cache().set_value(_cache_key(user), result, expires_in_sec=300)
	return result


def has_capability(user: str | None, capability: str) -> bool:
	"""
	Central capability check.

	Usage::

	    from huf.permissions import has_capability
	    if not has_capability(frappe.session.user, "agent.create"):
	        frappe.throw(_("Not permitted"), frappe.PermissionError)
	"""
	if not user:
		user = frappe.session.user
	return capability in get_user_capabilities(user)


# ---------------------------------------------------------------------------
# Frappe app-screen hook
# ---------------------------------------------------------------------------


def check_app_permission() -> bool:
	"""
	Frappe hook: controls whether the Huf tile appears in the Apps page.

	Allows access if the user:
	  - is Administrator, OR
	  - has System Manager role, OR
	  - has an active Huf User Role record.
	"""
	user = frappe.session.user

	if user == "Administrator":
		return True

	if _is_system_manager(user):
		return True

	return bool(get_user_huf_role(user))


# ---------------------------------------------------------------------------
# Whitelisted API endpoint — consumed by the React frontend
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_me() -> dict:
	"""
	GET /api/method/huf.permissions.get_me

	Returns the current user's identity, Huf role, and capability list.
	The React app calls this once on load to drive module visibility.

	Response shape::

	    {
	      "user": "jane@example.com",
	      "full_name": "Jane Doe",
	      "huf_role": "Huf Manager",
	      "capabilities": ["agent.use", "agent.create", ...]
	    }
	"""
	user = frappe.session.user
	full_name = frappe.db.get_value("User", user, "full_name") or user

	return {
		"user": user,
		"full_name": full_name,
		"huf_role": get_user_huf_role(user),
		"capabilities": get_user_capabilities(user),
	}
