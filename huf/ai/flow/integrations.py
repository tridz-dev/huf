# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Which integrations the Flow builder's Slack / Sheets / Drive / Gmail steps need, and whether each is connected."""

import frappe
from frappe import _

from huf.ai.tools.credentials import get_credential

# service -> (label, credential keys the flow tools read)
FLOW_INTEGRATIONS = {
	"slack": ("Slack", ("token",)),
	"gmail": ("Gmail", ("client_id", "client_secret", "refresh_token")),
	"google_drive": ("Google Drive", ("client_id", "client_secret", "refresh_token")),
	"google_sheets": ("Google Sheets", ("client_id", "client_secret", "refresh_token")),
}

# tool id prefix -> service
TOOL_PREFIX_SERVICE = {
	"slack_": "slack",
	"gmail_": "gmail",
	"gdrive_": "google_drive",
	"gsheets_": "google_sheets",
}


def service_for_tool(tool_id: str) -> str | None:
	for prefix, service in TOOL_PREFIX_SERVICE.items():
		if (tool_id or "").startswith(prefix):
			return service
	return None


def is_connected(service: str) -> bool:
	"""True when every credential the service's flow tools read is set (Integration Settings or environment)."""
	_label, keys = FLOW_INTEGRATIONS[service]
	return all(get_credential(service, key) for key in keys)


@frappe.whitelist()
def get_flow_integration_status() -> dict:
	"""``{service: {label, connected}}`` for the integrations Flow steps use. Never returns credential values."""
	if not frappe.has_permission("Flow Definition", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return {
		service: {"label": label, "connected": is_connected(service)}
		for service, (label, _keys) in FLOW_INTEGRATIONS.items()
	}
