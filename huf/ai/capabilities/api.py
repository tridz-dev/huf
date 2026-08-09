"""Whitelisted API endpoints for HUF app capability discovery.

Thin wrappers only: input validation/coercion and an admin-only permission
gate, then delegation to huf.ai.capabilities.{apps,actions,resources,events}.
No business logic lives here (see plan §13 Phase 1/2 APIs).

Permission gate: capability discovery exposes implementation details (app
manifests, whitelisted function paths, DocType/event internals) that plan
§18.1 says should be restricted to admins. This reuses the same
System-Manager-or-Huf-Admin/Manager gate already used by
huf.ai.agent_run_analytics_api._require_analytics_access, rather than
inventing new permission logic.
"""

import frappe

from huf.ai.capabilities import actions, apps, events, resources


def _require_capability_discovery_access():
	"""Restrict capability discovery endpoints to admins.

	Allowed: System Manager (Frappe role), or Huf Admin / Huf Manager
	(Huf capability role). Mirrors the gate in
	huf.ai.agent_run_analytics_api._require_analytics_access.
	"""
	user = frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return

	from huf.permissions import get_user_huf_role

	if get_user_huf_role(user) in ("Huf Admin", "Huf Manager"):
		return

	frappe.throw("Capability discovery requires admin access", frappe.PermissionError)


def _coerce_bool(value) -> bool:
	"""Coerce a whitelisted GET/POST param (which may arrive as a string) to bool."""
	if isinstance(value, str):
		return frappe.parse_json(value)
	return bool(value)


@frappe.whitelist()
def get_capability_apps():
	"""List installed Frappe apps with their HUF App manifest status."""
	_require_capability_discovery_access()
	return apps.get_capability_apps()


@frappe.whitelist()
def search_app_actions(app, query="", limit=50):
	"""Search declared + discovered action capabilities for `app`."""
	_require_capability_discovery_access()
	return actions.search_app_actions(app, query, int(limit))


@frappe.whitelist()
def describe_app_action(capability_id):
	"""Resolve a single action capability descriptor by its capability_id."""
	_require_capability_discovery_access()
	return actions.describe_app_action(capability_id)


@frappe.whitelist()
def get_app_resources(app, scope="recommended"):
	"""List ranked resource (DocType) capabilities for `app`."""
	_require_capability_discovery_access()
	return resources.get_app_resources(app, scope)


@frappe.whitelist()
def describe_resource(app, doctype):
	"""Describe a single app-owned DocType: generated actions/events/related resources."""
	_require_capability_discovery_access()
	return resources.describe_resource(app, doctype)


@frappe.whitelist()
def get_resource_events(app, doctype, include_advanced=False):
	"""List event capability descriptors for a doctype's lifecycle events."""
	_require_capability_discovery_access()
	submittable = bool(frappe.get_meta(doctype).is_submittable)
	return events.generate_events_for_resource(
		app,
		doctype,
		include_advanced=_coerce_bool(include_advanced),
		submittable=submittable,
	)


@frappe.whitelist()
def preview_trigger_payload(app, doctype, event_capability_id, condition=None, prompt_field=None):
	"""Preview the Agent Trigger "Doc Event" field payload for an event capability id.

	Discovery/preview only: does NOT create an Agent Trigger document. Actual
	creation stays in the existing Agent Trigger creation flow on the frontend.
	"""
	_require_capability_discovery_access()
	return events.build_trigger_payload(app, doctype, event_capability_id, condition, prompt_field)
