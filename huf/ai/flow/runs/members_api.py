"""Whitelisted calls for the people of a flow (Flow Member State) and the site's saved-data limit."""

from __future__ import annotations

import frappe
from frappe import _

from huf.ai.api_support import require_permission
from huf.ai.flow import state
from huf.ai.flow.runs import member
from huf.ai.flow.runs.access import require_flow_read


@frappe.whitelist()
def get_flow_state_limits() -> dict:
	"""``max_ttl_seconds`` for saved data on this site; 0 means no ceiling (keeping data until removed is allowed)."""
	require_permission(frappe.has_permission("Flow Definition", "read"), "Not permitted")
	return {"max_ttl_seconds": state.max_ttl_seconds()}


@frappe.whitelist()
def list_flow_members(flow: str, limit: int = 200) -> list[dict]:
	"""The people of a flow, most recent first. Needs read on the flow."""
	require_flow_read(flow)
	return frappe.get_all(
		member.DOCTYPE,
		filters={"flow": flow},
		fields=["member_key", "status", "current_node_id", "active_flow_run", "last_event_at"],
		order_by="last_event_at desc",
		limit=min(int(limit), 500),
	)


@frappe.whitelist(methods=["POST"])
def remove_flow_member(flow: str, member_key: str) -> dict:
	"""Forget a person: cancels their waiting run and deletes what the flow saved for them. Needs write on the flow."""
	require_flow_read(flow)
	if not frappe.db.exists("Flow Definition", flow) or not frappe.has_permission("Flow Definition", "write", doc=flow):
		frappe.throw(_("Only people who can edit this flow can remove people from it."), frappe.PermissionError)
	return {"removed": member.remove_member(flow, member_key)}
