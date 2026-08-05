import json

import frappe


BUILTIN_SERVICES = {
	"frappe_cloud": {
		"category": "Cloud",
		"description": "Manage Frappe Cloud benches, sites, apps, webhooks, and SSH access.",
		"required_credentials": [
			{"key": "api_key", "label": "API Key", "required": True},
			{"key": "api_secret", "label": "API Secret", "required": True},
			{
				"key": "server_url",
				"label": "Server URL",
				"required": False,
				"secret": False,
				"description": "Optional Frappe Cloud base URL (defaults to https://cloud.frappe.io)",
			},
		],
	},
}


def execute():
	"""Link every Agent Tool Function to the Integration Service it needs.

	Until now only the 45 Frappe Cloud tools carried a `service` value, so
	`get_service_tools` returned nothing for Slack, Gmail, GitHub, SERP and the
	rest — the picker could not tell a user which account a tool depends on.
	`_registry.py` now stamps the service onto every tool list, so re-running
	the sync backfills existing rows.

	Also re-asserts the built-in service records. `add_frappe_cloud_service`
	already ran on existing sites, so a record deleted since then would never
	come back; this patch is written to be safely re-assertable.
	"""
	_ensure_builtin_services()
	_resync_tools()


def _ensure_builtin_services():
	for service_name, spec in BUILTIN_SERVICES.items():
		try:
			if frappe.db.exists("Integration Service", service_name):
				doc = frappe.get_doc("Integration Service", service_name)
			else:
				doc = frappe.get_doc(
					{"doctype": "Integration Service", "service_name": service_name}
				)

			doc.category = spec["category"]
			doc.description = spec["description"]
			doc.required_credentials = json.dumps(spec["required_credentials"])
			doc.is_builtin = 1
			doc.save(ignore_permissions=True)
		except Exception as e:
			frappe.log_error(
				f"Could not assert Integration Service '{service_name}': {e}",
				"Backfill Tool Service Links",
			)


def _resync_tools():
	try:
		from huf.ai.tool_registry import sync_discovered_tools

		sync_discovered_tools(use_cache=False)
	except Exception as e:
		frappe.log_error(
			f"Tool re-sync failed during service backfill: {e}",
			"Backfill Tool Service Links",
		)
