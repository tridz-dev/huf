"""Flow ownership: which installed app a Flow Definition belongs to (``owner_app``).

``owner_app`` is set once, by the server, through :func:`create_app_flow`. It is empty for Huf-native flows.
A run of an app flow copies it in ``AgentFlowRun.before_insert``. No form, API or ``db_set`` write can set or
change it afterwards: :func:`guard_owner_app` (from ``FlowDefinition.validate``) and ``FlowDefinition.db_set``
refuse it.
"""

import json

import frappe
from frappe import _

FIELD = "owner_app"
#: Document flag that only :func:`create_app_flow` sets: the one path allowed to set ``owner_app``.
SERVER_FLAG = "huf_app_scope_server"


def create_app_flow(app: str, flow_id: str, flow_name: str, definition, *, status: str = "Draft"):
	"""Create a Flow Definition owned by ``app``. Python only: deliberately not whitelisted.

	``app`` must be installed, and every app-registered step type in ``definition`` must be ``app``'s own
	(its ``<app>.`` prefix). The flow is saved through the normal validator.
	"""
	_require_installed(app)
	defn = json.loads(definition) if isinstance(definition, str) else definition
	_require_own_node_types(app, defn)
	doc = frappe.new_doc("Flow Definition")
	doc.update(
		{
			"flow_id": flow_id,
			"flow_name": flow_name,
			"status": status,
			"definition_json": json.dumps(defn),
			FIELD: app,
		}
	)
	doc.flags[SERVER_FLAG] = True
	doc.insert(ignore_permissions=True)
	return doc


def guard_owner_app(doc) -> None:
	"""Refuse any write that sets or changes ``owner_app`` other than :func:`create_app_flow`'s insert."""
	value = doc.get(FIELD) or None
	if doc.is_new():
		if value and not doc.flags.get(SERVER_FLAG):
			frappe.throw(_("Owner App is set only by the app's server."), frappe.PermissionError)
		return
	before = doc.get_doc_before_save()
	stored = (before.get(FIELD) if before else frappe.db.get_value(doc.doctype, doc.name, FIELD)) or None
	if value != stored:
		frappe.throw(_("Owner App cannot be changed."), frappe.PermissionError)


def guard_db_set(doc, fieldname, value) -> None:
	"""``Document.db_set`` skips validate; refuse a change to ``owner_app`` there too."""
	changes = fieldname if isinstance(fieldname, dict) else {fieldname: value}
	if FIELD in changes and (changes[FIELD] or None) != (
		frappe.db.get_value(doc.doctype, doc.name, FIELD) or None
	):
		frappe.throw(_("Owner App cannot be changed."), frappe.PermissionError)


def owner_app_of(flow: str | None) -> str | None:
	return (frappe.db.get_value("Flow Definition", flow, FIELD) or None) if flow else None


def _require_installed(app: str) -> None:
	if not app or app not in frappe.get_installed_apps():
		frappe.throw(_("Unknown app: {0}").format(app))


def _require_own_node_types(app: str, defn: dict) -> None:
	from huf.ai.flow.catalog.node_registry import registered_types

	app_types = registered_types()
	for node in (defn or {}).get("nodes") or []:
		node_type = app_types.get((node or {}).get("type"))
		if node_type and node_type.app != app:
			frappe.throw(
				_("Step {0} belongs to app {1}, not {2}.").format(node.get("id"), node_type.app, app)
			)
