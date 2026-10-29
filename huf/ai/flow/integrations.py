# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Which integrations the Flow builder's Slack / Sheets / Drive / Gmail steps need, and whether each is connected."""

import re

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


_MISSING_CREDENTIAL = re.compile(r"Credential not found for service '([^']+)'")


def friendly_tool_error(error: str | None) -> str | None:
	"""Plain wording for a tool failure caused by a missing integration credential.

	The credential lookup names an internal key and an environment variable; a Flow step should say
	``"Google Sheets is not connected. Connect it in Integrations."`` instead. Other provider and integration
	messages ("X is not connected: add ...", a rejected token, a blocked address) get the same plain wording;
	any other error only loses HTML and Python noise (``plain_error``).
	"""
	match = _MISSING_CREDENTIAL.search(error or "")
	if not match:
		from huf.ai.graph.error_copy import plain_error

		return plain_error(error) if error else error
	service = match.group(1)
	label = FLOW_INTEGRATIONS[service][0] if service in FLOW_INTEGRATIONS else service.replace("_", " ").title()
	return f"{label} is not connected. Connect it in Integrations."


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
