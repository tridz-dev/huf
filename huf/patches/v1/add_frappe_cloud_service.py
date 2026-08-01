import json

import frappe


def execute():
	"""Create or update the Frappe Cloud Integration Service record."""
	schema = [
		{"key": "api_key", "label": "API Key", "required": True},
		{"key": "api_secret", "label": "API Secret", "required": True},
		{
			"key": "server_url",
			"label": "Server URL",
			"required": False,
			"secret": False,
			"description": "Optional Frappe Cloud base URL (defaults to https://cloud.frappe.io)",
		},
	]

	if frappe.db.exists("Integration Service", "frappe_cloud"):
		doc = frappe.get_doc("Integration Service", "frappe_cloud")
	else:
		doc = frappe.get_doc({"doctype": "Integration Service", "service_name": "frappe_cloud"})

	doc.category = "Cloud"
	doc.description = "Manage Frappe Cloud benches, sites, apps, webhooks, and SSH access."
	doc.required_credentials = json.dumps(schema)
	doc.is_builtin = 1
	doc.save(ignore_permissions=True)
