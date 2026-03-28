"""
huf/ai/permissions_api.py

Whitelisted API endpoints for Huf user and role management.
All endpoints enforce capability checks before doing anything.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from huf.permissions import (
	CAPABILITIES,
	DEFAULT_ROLE_CAPABILITIES,
	has_capability,
	get_user_huf_role,
	get_user_capabilities,
	_bust_cache,
)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def _require(capability: str) -> None:
	"""Throw a PermissionError if the current user lacks *capability*."""
	if not has_capability(frappe.session.user, capability):
		frappe.throw(
			_("You don't have permission to perform this action."),
			frappe.PermissionError,
		)


# ---------------------------------------------------------------------------
# User listing & management
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_users() -> list[dict]:
	"""
	Return all Huf User Role records with display-friendly fields.

	Requires: users.manage
	"""
	_require("users.manage")

	rows = frappe.get_all(
		"Huf User Role",
		fields=["user", "full_name", "huf_role", "enabled", "invited_by", "invited_on"],
		order_by="creation asc",
		ignore_permissions=True,
	)

	# Attach email separately (full_name is fetched, email is the user itself
	# for Frappe users whose name IS their email).
	for row in rows:
		row["email"] = row["user"]  # Frappe user name == email by convention

	return rows


@frappe.whitelist()
def invite_user(email: str, full_name: str, huf_role: str) -> dict:
	"""
	Create a Frappe user and assign a Huf role in one step.

	Steps:
	  1. Validate the caller has users.invite
	  2. Validate the requested huf_role exists
	  3. Create or reuse the Frappe User record
	  4. Create the Huf User Role record (which syncs the Frappe Has Role)

	Returns the created Huf User Role document.
	Requires: users.invite
	"""
	_require("users.invite")

	email = email.strip().lower()

	if not frappe.db.exists("Huf Role", huf_role):
		frappe.throw(_("Huf Role '{0}' does not exist.").format(huf_role))

	# Create Frappe user if they don't exist yet.
	if not frappe.db.exists("User", email):
		user_doc = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": full_name.split()[0] if full_name else email,
			"last_name": " ".join(full_name.split()[1:]) if full_name and len(full_name.split()) > 1 else "",
			"send_welcome_email": 0,
			"user_type": "System User",
		})
		user_doc.insert(ignore_permissions=True)

	# Create Huf User Role (controller syncs the Frappe role).
	if frappe.db.exists("Huf User Role", {"user": email}):
		frappe.throw(
			_("User '{0}' already has a Huf role. Use update_user_role to change it.").format(email)
		)

	doc = frappe.get_doc({
		"doctype": "Huf User Role",
		"user": email,
		"huf_role": huf_role,
		"enabled": 1,
		"invited_by": frappe.session.user,
		"invited_on": now_datetime(),
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return doc.as_dict()


@frappe.whitelist()
def update_user_role(user: str, huf_role: str) -> dict:
	"""
	Change the Huf role of an existing Huf user.
	The controller will automatically sync the underlying Frappe role.

	Requires: users.manage
	"""
	_require("users.manage")

	if not frappe.db.exists("Huf Role", huf_role):
		frappe.throw(_("Huf Role '{0}' does not exist.").format(huf_role))

	if not frappe.db.exists("Huf User Role", {"user": user}):
		frappe.throw(_("User '{0}' has no Huf User Role record.").format(user))

	doc = frappe.get_doc("Huf User Role", user)
	doc.huf_role = huf_role
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	_bust_cache(user)
	return doc.as_dict()


@frappe.whitelist()
def set_user_enabled(user: str, enabled: int) -> dict:
	"""
	Enable or disable a user's Huf access.
	Disabling removes their Frappe role immediately (via the controller).

	Requires: users.manage
	"""
	_require("users.manage")

	if not frappe.db.exists("Huf User Role", {"user": user}):
		frappe.throw(_("User '{0}' has no Huf User Role record.").format(user))

	doc = frappe.get_doc("Huf User Role", user)
	doc.enabled = int(enabled)
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	_bust_cache(user)
	return doc.as_dict()


# ---------------------------------------------------------------------------
# Role listing & management
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_huf_roles() -> list[dict]:
	"""
	Return all Huf Roles with their capability lists.

	Readable by anyone with users.manage or roles.manage.
	"""
	if not (has_capability(frappe.session.user, "users.manage") or
	        has_capability(frappe.session.user, "roles.manage")):
		_require("users.manage")  # will throw with a clear message

	roles = frappe.get_all(
		"Huf Role",
		fields=["role_name", "description", "is_system_role", "frappe_role"],
		order_by="creation asc",
		ignore_permissions=True,
	)

	for role in roles:
		cap_rows = frappe.get_all(
			"Huf Role Permission",
			filters={"parent": role["role_name"]},
			fields=["capability", "label"],
			ignore_permissions=True,
		)
		role["capabilities"] = [r.capability for r in cap_rows]

	return roles


@frappe.whitelist()
def get_capabilities_catalogue() -> dict:
	"""
	Return the full capability catalogue as {capability: label}.

	Used by the Roles editor to present all available options.
	Requires: roles.manage
	"""
	_require("roles.manage")
	return CAPABILITIES


@frappe.whitelist()
def create_huf_role(role_name: str, description: str, capabilities: list) -> dict:
	"""
	Create a new custom Huf Role with the given capabilities.

	Requires: roles.manage
	"""
	_require("roles.manage")

	if frappe.db.exists("Huf Role", role_name):
		frappe.throw(_("A Huf Role named '{0}' already exists.").format(role_name))

	unknown = [c for c in capabilities if c not in CAPABILITIES]
	if unknown:
		frappe.throw(_("Unknown capabilities: {0}").format(", ".join(unknown)))

	doc = frappe.get_doc({
		"doctype": "Huf Role",
		"role_name": role_name,
		"description": description,
		"is_system_role": 0,
	})
	for cap in capabilities:
		doc.append("permissions", {"capability": cap})

	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.as_dict()


@frappe.whitelist()
def update_huf_role(role_name: str, capabilities: list, description: str = None) -> dict:
	"""
	Replace the capability set of an existing Huf Role.
	System roles can have capabilities updated but not deleted.

	Requires: roles.manage
	"""
	_require("roles.manage")

	if not frappe.db.exists("Huf Role", role_name):
		frappe.throw(_("Huf Role '{0}' does not exist.").format(role_name))

	unknown = [c for c in capabilities if c not in CAPABILITIES]
	if unknown:
		frappe.throw(_("Unknown capabilities: {0}").format(", ".join(unknown)))

	doc = frappe.get_doc("Huf Role", role_name)

	if description is not None:
		doc.description = description

	doc.set("permissions", [])
	for cap in capabilities:
		doc.append("permissions", {"capability": cap})

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return doc.as_dict()
