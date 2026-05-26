"""
Integration Recipient lookup tool for HUF agents.

Resolves a human-friendly recipient name (e.g. "John Doe", "Sales Alerts")
to a service-specific ID (Telegram Chat ID, Slack User/Channel ID, Discord
Channel ID, etc.) stored in the Integration Settings recipients table.

This keeps agent prompts and instructions free of hardcoded IDs, and allows
the same recipient name to be used across multiple services without any
code changes — just add a row to the Integration Settings for that service.
"""

import json
import frappe


def handle_get_recipient(**kwargs) -> str:
	"""
	Look up a recipient's service-specific ID from Integration Settings.

	Searches the recipients child table of the active Integration Settings
	document for the given service, matching on recipient_name
	(case-insensitive).

	Args (via kwargs):
		service (str): Service name, e.g. "telegram", "slack", "discord".
		recipient_name (str): Human-friendly name, e.g. "John Doe".

	Returns:
		JSON string with:
		  - success=True + recipient_id  on match
		  - success=False + error + available_recipients list  on failure
	"""
	service = (kwargs.get("service") or "").strip().lower()
	recipient_name = (kwargs.get("recipient_name") or "").strip()

	if not service or not recipient_name:
		return json.dumps({
			"success": False,
			"error": "Both 'service' and 'recipient_name' are required"
		})

	try:
		# Find the active Integration Settings for this service
		settings_list = frappe.get_all(
			"Integration Settings",
			filters={"service": service, "is_active": 1},
			fields=["name"],
			order_by="is_default DESC, modified DESC",
			limit=1
		)

		if not settings_list:
			return json.dumps({
				"success": False,
				"error": f"No active Integration Settings found for service '{service}'. "
				         f"Please configure it in Huf > Integration Settings."
			})

		doc = frappe.get_doc("Integration Settings", settings_list[0].name)

		if not doc.recipients:
			return json.dumps({
				"success": False,
				"error": f"No recipients configured for '{service}'. "
				         f"Open Integration Settings > {doc.name} and add recipients.",
				"available_recipients": []
			})

		# Case-insensitive name match
		name_lower = recipient_name.lower()
		for row in doc.recipients:
			if (row.recipient_name or "").strip().lower() == name_lower:
				return json.dumps({
					"success": True,
					"recipient_name": row.recipient_name,
					"recipient_id": row.recipient_id,
					"service": service
				})

		# Not found — return helpful list of available names
		available = [r.recipient_name for r in doc.recipients if r.recipient_name]
		return json.dumps({
			"success": False,
			"error": f"Recipient '{recipient_name}' not found for service '{service}'.",
			"available_recipients": available
		})

	except Exception as e:
		frappe.log_error(f"get_integration_recipient error: {str(e)}", "Integration Recipient Tool")
		return json.dumps({"success": False, "error": str(e)})
