"""Server guards for the whitelisted flow APIs (D-HAPPIOL-EMBED decisions 2-4, H-W7-09).

Every whitelisted function under ``huf.ai.flow`` calls exactly one of the ``guard_*`` functions below as its
first statement. ``tests/test_api_guards.py`` finds the whitelisted functions by introspection and fails for any
function that does not, so a new API stays refused in review until someone classifies it.

Users split in three:

- *privileged*: Administrator, System Manager, Huf Manager. They pass every guard here (support access); the
  function's own checks still apply.
- *Huf users*: hold the Huf capability ``flows.use``. On Huf-native flows nothing changes; on app-owned flows
  they need the app's delegated role, like everyone else.
- *app-only users*: no Huf capability. They reach only the flows of apps that granted them a role, never a
  Huf-native flow, never a Huf-wide screen or setting, never publish, and a test run is always a dry run.

Reading is the one exception: holders of a native Huf role (Huf User, Huf Viewer, Huf Manager) keep reading
Huf-native flows even without ``flows.use`` (a Huf Viewer has none). It never reaches an app-owned flow.

The guards only ever refuse. They never grant what the function's own permission checks would refuse.
"""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.flow.app_scope import access
from huf.ai.flow.app_scope.access import apps_for, is_privileged, require_flow_access
from huf.ai.flow.app_scope.ownership import owner_app_of

HUF_CAPABILITY = "flows.use"


def _deny():
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def is_app_only(user: str | None = None) -> bool:
	"""True for a signed-in user who reaches flows only through an app's delegated roles."""
	from huf.permissions import has_capability

	user = user or frappe.session.user
	if user == "Guest" or is_privileged(user):
		return False
	return not has_capability(user, HUF_CAPABILITY)


def _may_not_read_native() -> bool:
	"""App-only and without a native Huf role: Huf-native flows are not theirs to read either."""
	return is_app_only() and not (access.NATIVE_ROLES & set(frappe.get_roles(frappe.session.user)))


def app_approve_roles(action: str) -> set[str]:
	"""The approve roles of the apps whose flows the caller may ``action``: all an app-only user may look up."""
	grants = access.app_grants()
	return {role for app in apps_for(None, action) if app in grants for role in grants[app]["approve"]}


def is_app_flow(flow_id: str | None) -> bool:
	return bool(flow_id and owner_app_of(flow_id))


def _run_flow_id(flow_run_id: str | None) -> str | None:
	if not flow_run_id:
		return None
	row = frappe.db.get_value("Agent Flow Run", flow_run_id, ["flow_definition", "flow_id"], as_dict=True)
	if not row:
		return None
	return row.flow_definition or row.flow_id


# --- guards -------------------------------------------------------------------------------------------------


def guard_public() -> None:
	"""Marker for endpoints authenticated by their own secret (webhook HMAC, single-use resume token)."""


def guard_huf_only() -> None:
	"""A Huf-wide screen or setting: refused for app-only users."""
	if is_app_only():
		_deny()


def guard_huf_read() -> None:
	"""A read-only list of Huf-native flows: refused for app-only users without a native Huf role.

	The list itself must be permission-checked, so app-owned flows stay out of it.
	"""
	if _may_not_read_native():
		_deny()


def guard_app_meta(app: str | None = None) -> None:
	"""Static builder metadata (doctype lists, roles, time zone, user search).

	App-only users need view on some app's flows (on ``app`` when given); everyone else passes.
	"""
	if not is_app_only():
		return
	apps = apps_for(None, "view")
	if not apps or (app and app not in apps):
		_deny()


def guard_app_named(app: str | None) -> None:
	"""Node types and schemas: an app-only user must name an app whose flows they may view.

	Anyone else naming an app must also be able to view that app's flows (privileged users pass).
	"""
	if is_privileged():
		return
	if app:
		if app not in apps_for(None, "view"):
			_deny()
	elif is_app_only():
		_deny()


def guard_flow(flow_id: str | None, action: str) -> None:
	"""One flow. App-owned: ``flow_access(action)``. Huf-native or unknown: refused for app-only users, except
	that a native Huf role may ``view`` it."""
	if is_privileged():
		return
	if is_app_flow(flow_id):
		require_flow_access(flow_id, action)
	elif _may_not_read_native() if action == "view" else is_app_only():
		_deny()


def guard_flow_or_huf(flow_id: str | None, action: str) -> None:
	"""A list that is per flow when ``flow_id`` is given and Huf-wide otherwise."""
	if flow_id:
		guard_flow(flow_id, action)
	elif action == "view":
		guard_huf_read()
	else:
		guard_huf_only()


def guard_run(flow_run_id: str | None, action: str) -> None:
	"""One run, checked through its flow. A run that does not exist is refused for app-only users."""
	if is_privileged():
		return
	flow_id = _run_flow_id(flow_run_id)
	if flow_id is None:
		if is_app_only():
			_deny()
		return
	guard_flow(flow_id, action)


def guard_huf_flow(flow_id: str | None, action: str = "edit") -> None:
	"""Huf-only actions on one flow (publish, unpublish, settings, conversion, real entry).

	An app-owned flow goes live only through its app (decision 3): refused for everyone but privileged users.
	A Huf-native flow is refused for app-only users.
	"""
	if is_privileged():
		return
	if is_app_flow(flow_id) or is_app_only():
		_deny()


def force_dry_run(flow_id: str | None, mode: str) -> str:
	"""The run mode to use: an app-owned flow started by a non-privileged user is always a test (dry) run."""
	if is_app_flow(flow_id) and not is_privileged():
		return "test"
	if is_app_only():
		return "test"
	return mode


def embed_policy(flow_id: str, user: str | None = None) -> dict | None:
	"""``huf_embed.policy`` for an app-owned flow (booleans only), None for a Huf-native flow."""
	from huf.ai.flow.app_scope.access import flow_access

	if not is_app_flow(flow_id):
		return None
	user = user or frappe.session.user
	return {
		"publish": "host",
		"test": "dry_run",
		"can_edit": bool(flow_access(user, flow_id, "edit")),
		"can_test": bool(flow_access(user, flow_id, "test")),
		"can_approve": bool(flow_access(user, flow_id, "approve")),
	}
