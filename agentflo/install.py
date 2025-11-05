# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Installation hooks for AgentFlo app
"""

import json
import os

import frappe


def after_install():
	"""
	Called after app installation.
	Checks if litellm is installed and provides helpful message if not.
	Seeds initial agents from fixtures.
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
	
	# Seed initial agents
	seed_agents()


def seed_agents():
	"""
	Load and import seed agents from fixtures.
	"""
	try:
		fixtures_path = frappe.get_app_path("agentflo", "fixtures", "agents")
		
		if not os.path.exists(fixtures_path):
			return
		
		from agentflo.export import import_agent
		
		seed_count = 0
		for fixture_file in os.listdir(fixtures_path):
			if fixture_file.endswith(".json"):
				file_path = os.path.join(fixtures_path, fixture_file)
				try:
					with open(file_path, "r", encoding="utf-8") as f:
						agent_data = json.load(f)
					
					# Ensure metadata is set
					if "metadata" not in agent_data:
						agent_data["metadata"] = {}
					agent_data["metadata"]["app"] = "agentflo"
					agent_data["metadata"]["is_seed"] = True
					
					# Import with skip mode (don't overwrite existing)
					import_agent(agent_data, import_mode="skip")
					seed_count += 1
				except Exception as e:
					frappe.log_error(
						f"Failed to seed agent from {fixture_file}: {str(e)}",
						"Agent Seed Error"
					)
		
		if seed_count > 0:
			frappe.log_error(
				f"Seeded {seed_count} agents from fixtures",
				"Agent Seed"
			)
	except Exception as e:
		frappe.log_error(
			f"Failed to seed agents: {str(e)}",
			"Agent Seed Error"
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

