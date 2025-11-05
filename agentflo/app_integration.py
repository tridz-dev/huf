# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
App integration hooks for AgentFlo.

Allows other Frappe apps to seed their own agents via fixtures.
"""

import json
import os

import frappe


def after_app_install(app_name: str):
	"""
	Called when another app is installed.
	
	Checks if the app has agent fixtures and seeds them.
	
	Args:
		app_name: Name of the app being installed
	"""
	try:
		# Check if app has agent fixtures
		app_agent_fixtures = frappe.get_app_path(app_name, "fixtures", "agents")
		
		if os.path.exists(app_agent_fixtures):
			seed_app_agents(app_name, app_agent_fixtures)
	except Exception as e:
		frappe.log_error(
			f"Failed to check agent fixtures for app {app_name}: {str(e)}",
			"App Integration Error"
		)


def seed_app_agents(app_name: str, fixtures_path: str):
	"""
	Seed agents from another app's fixtures.
	
	Convention: Apps can provide agents in {app_name}/fixtures/agents/*.json
	Agents should have is_standard: 1 and metadata.app set to app name.
	
	Args:
		app_name: Name of the app providing the agents
		fixtures_path: Path to the fixtures directory
	"""
	try:
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
					agent_data["metadata"]["app"] = app_name
					agent_data["metadata"]["is_seed"] = True
					
					# Ensure agent is marked as standard
					if "agent" in agent_data:
						agent_data["agent"]["is_standard"] = 1
					
					# Import with skip mode (don't overwrite existing)
					import_agent(agent_data, import_mode="skip")
					seed_count += 1
				except Exception as e:
					frappe.log_error(
						f"Failed to seed agent from {app_name}/{fixture_file}: {str(e)}",
						"App Agent Seed Error"
					)
		
		if seed_count > 0:
			frappe.log_error(
				f"Seeded {seed_count} agents from app {app_name}",
				"App Agent Seed"
			)
	except Exception as e:
		frappe.log_error(
			f"Failed to seed agents from app {app_name}: {str(e)}",
			"App Agent Seed Error"
		)
