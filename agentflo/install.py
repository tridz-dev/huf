# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for AgentFlo app
"""

import frappe


def after_install():
	"""
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	"""
	try:
		import litellm
		frappe.msgprint("✅ LiteLLM is installed and ready to use.")
	except ImportError:
		frappe.msgprint(
			"⚠️ LiteLLM package not found. "
			"Please run 'bench setup requirements' to install dependencies, "
			"then restart your site with 'bench restart'.",
			indicator="orange",
			title="Dependency Missing"
		)


def after_migrate():
	"""
	Called after app migration.
	Syncs all discovered tools from all installed apps.
	"""
	try:
		from agentflo.ai.tool_registry import sync_discovered_tools
		result = sync_discovered_tools()  # Full scan (apps_to_scan=None)
		frappe.log_error(
			f"Synced tools after migrate: {result.get('total_tools', 0)} tools from {len(result.get('synced_apps', []))} apps",
			"Tool Sync"
		)
	except Exception as e:
		frappe.log_error(
			f"Failed to sync tools after migrate: {str(e)}",
			"Tool Sync Error"
		)

