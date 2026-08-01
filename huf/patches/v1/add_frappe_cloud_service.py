import json

import frappe


def execute():
	"""Create the Frappe Cloud Integration Service record if it does not exist."""
	if frappe.db.exists("Integration Service", "frappe_cloud"):
		return

	frappe.get_doc(
		{
			"doctype": "Integration Service",
			"service_name": "frappe_cloud",
			"category": "Cloud",
			"description": "Manage Frappe Cloud benches, sites, apps, webhooks, and SSH access.",
			"required_credentials": json.dumps(
				[
					{"key": "api_key", "label": "API Key", "required": True},
					{"key": "api_secret", "label": "API Secret", "required": True},
					{
						"key": "server_url",
						"label": "Server URL",
						"required": False,
						"description": "Optional Frappe Cloud base URL (defaults to https://cloud.frappe.io)",
					},
				]
			),
			"is_builtin": 1,
		}
	).insert(ignore_permissions=True)
