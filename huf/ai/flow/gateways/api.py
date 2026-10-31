"""Editor endpoint for the chat trigger nodes: the registry (forms and data names) and the channels the caller may use.

``connection_state`` is the channel's own Connected / Degraded / Disconnected.
"""

import frappe

from huf.ai.api_support import require_permission
from huf.ai.flow.gateways.registry import get_registry


@frappe.whitelist()
def get_gateway_trigger_registry() -> dict:
	"""``{version, limits, specs:{node_type: spec}, gateways:[{name,label,provider,enabled,connection_state}]}``.

	Only people who can edit flows may ask. ``gateways`` lists the channels the caller may write (the same right a chat
	trigger needs); no credentials or provider payloads are included.
	"""
	require_permission(frappe.has_permission("Flow Definition", "write"), "Not permitted")
	registry = get_registry()
	rows = frappe.get_all("Gateway", fields=["name", "gateway_name", "provider", "is_enabled", "connection_state"], order_by="gateway_name asc")
	registry["gateways"] = [
		{
			"name": row.name,
			"label": row.gateway_name or row.name,
			"provider": row.provider,
			"enabled": bool(row.is_enabled),
			"connection_state": row.connection_state or "",
		}
		for row in rows
		if frappe.has_permission("Gateway", "write", doc=row.name)
	]
	return registry


@frappe.whitelist()
def get_gateway_states(names=None) -> list:
	"""``[{name,label,provider,enabled,connection_state}]`` for the named channels, for people who may read flows.

	A view-only person cannot list channels, but their canvas card must still say "switched off" like the editor's.
	Only the channels asked for come back, and only name, label, provider and on/off state; never credentials.
	"""
	require_permission(frappe.has_permission("Flow Definition", "read"), "Not permitted")
	if isinstance(names, str):
		names = frappe.parse_json(names)
	wanted = [str(n) for n in (names or []) if n][:50]
	rows = frappe.get_all(
		"Gateway", filters={"name": ["in", wanted]}, fields=["name", "gateway_name", "provider", "is_enabled", "connection_state"]
	) if wanted else []
	return [
		{
			"name": row.name,
			"label": row.gateway_name or row.name,
			"provider": row.provider,
			"enabled": bool(row.is_enabled),
			"connection_state": row.connection_state or "",
		}
		for row in rows
	]
