# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""WhatsApp Broadcast: read-only whitelisted API (list, detail, template parameters, recipient rows)."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from huf.ai.whatsapp.broadcast.api import (
	_BROADCAST,
	_BROADCAST_RECIPIENT,
	_BROADCAST_FIELDS,
	_require_broadcast_read,
	_broadcast_view,
	_mask_phone,
	_mask_digits,
)
from huf.ai.whatsapp.management import (
	_bridge_guard,
	_error,
	_gateway_write_allowed,
	_gateway_read_allowed,
	_gateway_whatsapp_account,
	_TEMPLATE_RECORD_RE,
	_iso,
	_clamp_limit,
	_gateway_required,
	_can_manage_integrations,
)
from huf.ai.gateway_adapters import whatsapp_bridge as bridge


@frappe.whitelist()
@_bridge_guard
def list_broadcasts(gateway: str | None = None, status: str | None = None, limit: Any = 50, offset: Any = 0) -> dict[str, Any]:
	"""List broadcasts (newest first) with counts. A non-admin must name a Gateway they can read."""
	filters: dict[str, Any] = {}
	if gateway:
		if not frappe.db.exists("Gateway", gateway):
			return _error("not_found", "Gateway not found.")
		if not _gateway_read_allowed(gateway):
			raise frappe.PermissionError(_("Not permitted to read this Gateway"))
		filters["gateway"] = gateway
	elif not _can_manage_integrations():
		return _gateway_required()
	if status:
		filters["status"] = status
	try:
		skip = max(0, int(offset))
	except (TypeError, ValueError):
		skip = 0
	rows = frappe.get_all(
		_BROADCAST, filters=filters, fields=list(_BROADCAST_FIELDS), order_by="creation desc",
		limit_start=skip, limit_page_length=_clamp_limit(limit),
	)
	return {"success": True, "broadcasts": [_broadcast_view(r) for r in rows or []]}


@frappe.whitelist()
@_bridge_guard
def get_broadcast_template_params(gateway: str | None = None, template: str | None = None) -> dict[str, Any]:
	"""What a broadcast of ``template`` needs per recipient (body / header / button parameters). Read-only.

	``{success, template, parameter_format: NAMED|POSITIONAL, body: [{name|index, sample}],
	header: {type, required, name|index?, sample?}|None, buttons: [{index, sub_type, required, label}]}``.
	"""
	if not gateway or not frappe.db.exists("Gateway", gateway):
		return _error("not_found", "Gateway not found.")
	if not _gateway_read_allowed(gateway):
		raise frappe.PermissionError(_("Not permitted to read this Gateway"))
	account = _gateway_whatsapp_account(gateway)
	if not account:
		return _error("no_account", "This gateway is not linked to a WhatsApp Account.")
	if not template or not _TEMPLATE_RECORD_RE.match(str(template).strip()):
		return _error("invalid_name", "Template must be the Meta name or '<name>-<language_code>'.")
	from huf.ai.whatsapp.broadcast import limits as broadcast_limits

	docname = bridge._template_docname(account, str(template).strip(), None)
	req = broadcast_limits.template_requirements(docname)
	if not req or (req["tpl"].get("whatsapp_account") or "") != account:
		return _error("template_not_found", "Template not found on this gateway's WhatsApp account.")
	return {
		"success": True,
		"template": docname,
		"parameter_format": req["parameter_format"],
		"body": req["body"],
		"header": req["header"],
		"buttons": req["buttons"],
	}


@frappe.whitelist()
@_bridge_guard
def get_broadcast(broadcast: str | None = None) -> dict[str, Any]:
	"""One broadcast with its status counters."""
	row = _require_broadcast_read(broadcast)
	if row.get("error"):
		return row
	return {"success": True, "broadcast": _broadcast_view(row)}


@frappe.whitelist()
@_bridge_guard
def list_broadcast_recipients(broadcast: str | None = None, status: str | None = None, limit: Any = 100, offset: Any = 0) -> dict[str, Any]:
	"""Recipient rows of a broadcast, optionally filtered by status."""
	row = _require_broadcast_read(broadcast)
	if row.get("error"):
		return row
	filters: dict[str, Any] = {"broadcast": broadcast}
	if status:
		filters["status"] = status
	try:
		skip = max(0, int(offset))
	except (TypeError, ValueError):
		skip = 0
	masked = not _gateway_write_allowed(row.get("gateway"))
	rows = frappe.get_all(
		_BROADCAST_RECIPIENT, filters=filters,
		fields=["name", "recipient", "status", "skip_reason", "wamid", "message_status", "attempts", "next_attempt_at",
			"error_code", "error_message", "sent_at", "delivered_at", "read_at", "failed_at"],
		order_by="creation asc", limit_start=skip, limit_page_length=_clamp_limit(limit),
	)
	out = [dict(r, **{k: _iso(r.get(k)) for k in ("next_attempt_at", "sent_at", "delivered_at", "read_at", "failed_at")}) for r in rows or []]
	if masked:  # read-only Gateway users must not see the full phone list (L5)
		for r in out:
			r["recipient"] = _mask_phone(r.get("recipient"))
			r["error_message"] = _mask_digits(r.get("error_message"))
			r["name"] = _mask_digits(r.get("name"))
	return {"success": True, "recipients": out}
