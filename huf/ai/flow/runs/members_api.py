"""Whitelisted calls for the people of a flow (Flow Member State) and the site's saved-data limit."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils.password import decrypt, encrypt

from huf.ai.api_support import require_permission
from huf.ai.flow.app_scope.runs_api import mask_member
from huf.ai.flow import state
from huf.ai.flow.runs import member
from huf.ai.flow.runs.access import require_flow_read


@frappe.whitelist()
def get_flow_state_limits() -> dict:
	"""``max_ttl_seconds`` for saved data on this site; 0 means no ceiling (keeping data until removed is allowed)."""
	from huf.ai.flow.app_scope.api_guards import guard_app_meta
	guard_app_meta()
	require_permission(frappe.has_permission("Flow Definition", "read"), "Not permitted")
	return {"max_ttl_seconds": state.max_ttl_seconds()}


@frappe.whitelist()
def list_flow_members(flow: str, limit: int = 200) -> list[dict]:
	"""The people of a flow, most recent first. Needs read on the flow.

	``member_key`` is masked (it may be a phone number); ``member_ref`` is the opaque handle to remove that person.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_flow
	guard_flow(flow, "view")
	require_flow_read(flow)
	rows = frappe.get_all(
		member.DOCTYPE,
		filters={"flow": flow},
		fields=["member_key", "status", "current_node_id", "active_flow_run", "last_event_at"],
		order_by="last_event_at desc",
		limit=min(int(limit), 500),
	)
	for row in rows:
		row["member_ref"] = encrypt(row["member_key"])
		row["member_key"] = mask_member(row["member_key"])
	return rows


@frappe.whitelist(methods=["POST"])
def remove_flow_member(flow: str, member_key: str | None = None, member_ref: str | None = None) -> dict:
	"""Forget a person: cancels their waiting run and deletes what the flow saved for them. Needs write on the flow.

	The person is named by ``member_key``, or by the ``member_ref`` that :func:`list_flow_members` returned.
	"""
	from huf.ai.flow.app_scope.api_guards import guard_flow
	guard_flow(flow, "edit")
	require_flow_read(flow)
	if not frappe.db.exists("Flow Definition", flow) or not frappe.has_permission("Flow Definition", "write", doc=flow):
		frappe.throw(_("Only people who can edit this flow can remove people from it."), frappe.PermissionError)
	if member_ref:
		member_key = _key_of_ref(member_ref)
	if not member_key:
		frappe.throw(_("Choose the person to remove."), frappe.ValidationError)
	return {"removed": member.remove_member(flow, member_key)}


def _key_of_ref(member_ref: str) -> str:
	try:
		return decrypt(member_ref)
	except Exception:  # noqa: BLE001 - any unreadable ref is the same plain refusal
		frappe.clear_last_message()
		frappe.throw(_("This person is no longer listed. Reload the list."), frappe.ValidationError)
