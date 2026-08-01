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
			"required_credentials": '[{"key": "api_key", "label": "API Key", "required": true}, {"key": "api_secret", "label": "API Secret", "required": true}]',
			"is_builtin": 1,
		}
	).insert(ignore_permissions=True)
