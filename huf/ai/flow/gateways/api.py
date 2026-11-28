"""Editor endpoint for the chat trigger nodes: the registry (forms and data names) and the channels the caller may use.

``connection_state`` is the channel's own Connected / Degraded / Disconnected.
"""

import frappe

from huf.ai.api_support import require_permission
from huf.ai.flow.gateways.registry import get_registry


def _choice(row) -> dict:
	"""What the editor may know about a channel: never credentials or provider payloads."""
	return {
		"name": row.name,
		"label": row.gateway_name or row.name,
		"provider": row.provider,
		"enabled": bool(row.is_enabled),
		"connection_state": row.connection_state or "",
	}


@frappe.whitelist()
def get_gateway_trigger_registry() -> dict:
	"""``{version, limits, specs:{node_type: spec}, gateways:[{name,label,provider,enabled,connection_state}]}``.

	Only people who can edit flows may ask. ``gateways`` lists the channels the caller may write (the same right a chat
	trigger needs); no credentials or provider payloads are included.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_huf_only
	guard_huf_only()
	require_permission(frappe.has_permission("Flow Definition", "write"), "Not permitted")
	registry = get_registry()
	rows = frappe.get_all("Gateway", fields=["name", "gateway_name", "provider", "is_enabled", "connection_state"], order_by="gateway_name asc")
	registry["gateways"] = [_choice(row) for row in rows if frappe.has_permission("Gateway", "write", doc=row.name)]
	return registry


@frappe.whitelist()
def get_gateway_states(names=None) -> list:
	"""``[{name,label,provider,enabled,connection_state}]`` for the named channels, for people who may read flows.

	A view-only person cannot list channels, but their canvas card must still say "switched off" like the editor's.
	Only the channels asked for come back, and only name, label, provider and on/off state; never credentials.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_huf_only
	guard_huf_only()
	require_permission(frappe.has_permission("Flow Definition", "read"), "Not permitted")
	if isinstance(names, str):
		names = frappe.parse_json(names)
	wanted = [str(n) for n in (names or []) if n][:50]
	rows = frappe.get_all(
		"Gateway", filters={"name": ["in", wanted]}, fields=["name", "gateway_name", "provider", "is_enabled", "connection_state"]
	) if wanted else []
	return [_choice(row) for row in rows]


@frappe.whitelist()
def get_app_flow_gateways(flow_id: str) -> dict:
	"""``{restricted, gateways}``: the channels the caller may pick in the steps of one flow.

	``restricted`` is True for a non-privileged editor of an app-owned flow, and ``gateways`` then holds only the ones
	the flow already stores plus the ones its app lists. Otherwise it is False and the list is empty: the editor
	uses :func:`get_gateway_trigger_registry`.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_flow
	guard_flow(flow_id, "edit")
	from huf.ai.flow.app_scope import targets
	from huf.ai.flow.app_scope.access import flow_access, is_privileged
	from huf.ai.flow.app_scope.gateways import app_gateways
	from huf.ai.flow.app_scope.ownership import owner_app_of

	app = owner_app_of(flow_id)
	# explicit form of the rule guard_flow applies to app-owned flows; native flows keep guard_flow's rule
	require_permission(not app or flow_access(frappe.session.user, flow_id, "edit"), "Not permitted")
	if not app or is_privileged():
		return {"restricted": False, "gateways": []}
	definition = frappe.parse_json(frappe.db.get_value("Flow Definition", flow_id, "definition_json") or "{}")
	nodes = [n for n in definition.get("nodes") or [] if isinstance(n, dict)]
	wanted = sorted(app_gateways(app, frappe.session.user) | targets.gateway_names(nodes))
	rows = frappe.get_all(
		"Gateway", filters={"name": ["in", wanted]},
		fields=["name", "gateway_name", "provider", "is_enabled", "connection_state"], order_by="gateway_name asc",
	) if wanted else []
	return {"restricted": True, "gateways": [_choice(row) for row in rows]}
