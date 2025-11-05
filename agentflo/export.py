# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Agent Export/Import utilities for AgentFlo.

This module provides functionality to export and import agents along with their
dependencies (AI Provider, AI Model, Agent Tool Functions, etc.).
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.utils import cstr


def can_export_agent(agent_name: str) -> bool:
	"""
	Check if an agent can be exported.
	
	Similar to Studio's can_export - checks if agent is standard and
	if developer mode is enabled.
	
	Args:
		agent_name: Name of the agent to check
		
	Returns:
		True if agent can be exported, False otherwise
	"""
	if not agent_name:
		return False
		
	try:
		agent = frappe.get_doc("Agent", agent_name)
		
		# Only standard agents can be exported
		if not agent.is_standard:
			return False
			
		# Check if in developer mode (similar to Studio's pattern)
		if not frappe.conf.developer_mode:
			return False
			
		# Check if not in install/uninstall process
		if frappe.flags.in_install or frappe.flags.in_uninstall:
			return False
			
		return True
	except frappe.DoesNotExistError:
		return False


def export_agent(agent_name: str, include_dependencies: bool = True) -> Dict:
	"""
	Export an agent with all dependencies as a structured dictionary.
	
	Args:
		agent_name: Name of the agent to export
		include_dependencies: Whether to include dependencies (Provider, Model, Tools)
		
	Returns:
		Dictionary containing agent data, dependencies, and metadata
	"""
	if not agent_name:
		frappe.throw(_("Agent name is required"))
		
	agent = frappe.get_doc("Agent", agent_name)
	
	# Get agent data (as dict)
	agent_dict = agent.as_dict()
	
	# Clean up sensitive/unnecessary data
	agent_dict = _clean_agent_data(agent_dict)
	
	result = {
		"agent": agent_dict,
		"dependencies": {},
		"metadata": {
			"version": "1.0",
			"exported_at": datetime.now().isoformat(),
			"exported_by": frappe.session.user,
			"app": "agentflo"
		}
	}
	
	if include_dependencies:
		result["dependencies"] = _export_dependencies(agent)
		
	return result


def _clean_agent_data(agent_dict: Dict) -> Dict:
	"""
	Clean up agent data before export.
	
	Removes:
	- Conversation history references
	- Run logs
	- Internal flags
	- Execution timestamps
	"""
	# Fields to remove
	fields_to_remove = [
		"last_run",
		"total_run",
		"last_execution",
		"next_execution",
		"modified",
		"modified_by",
		"creation",
		"owner",
		"docstatus",
		"doctype",
		"name"
	]
	
	for field in fields_to_remove:
		agent_dict.pop(field, None)
		
	# Ensure is_standard is set appropriately
	# Keep it as-is if already set, otherwise it will be 0
	
	return agent_dict


def _export_dependencies(agent: "Agent") -> Dict:
	"""
	Export all dependencies for an agent.
	
	Returns:
		Dictionary containing:
		- ai_provider: Provider data
		- ai_model: Model data
		- agent_tool_functions: List of tool function data
	"""
	dependencies = {}
	
	# Export AI Provider
	if agent.provider:
		provider = frappe.get_doc("AI Provider", agent.provider)
		provider_dict = provider.as_dict()
		# Remove API key for security
		provider_dict.pop("api_key", None)
		provider_dict.pop("modified", None)
		provider_dict.pop("modified_by", None)
		provider_dict.pop("creation", None)
		provider_dict.pop("owner", None)
		provider_dict.pop("docstatus", None)
		provider_dict.pop("doctype", None)
		dependencies["ai_provider"] = provider_dict
	
	# Export AI Model
	if agent.model:
		model = frappe.get_doc("AI Model", agent.model)
		model_dict = model.as_dict()
		# Remove internal fields
		model_dict.pop("modified", None)
		model_dict.pop("modified_by", None)
		model_dict.pop("creation", None)
		model_dict.pop("owner", None)
		model_dict.pop("docstatus", None)
		model_dict.pop("doctype", None)
		# Store provider name instead of link for resolution
		if model.provider:
			model_dict["provider_name"] = model.provider
		dependencies["ai_model"] = model_dict
	
	# Export Agent Tool Functions
	if agent.agent_tool:
		tool_functions = []
		for tool_row in agent.agent_tool:
			if tool_row.tool:
				tool_function = frappe.get_doc("Agent Tool Function", tool_row.tool)
				tool_dict = tool_function.as_dict()
				
				# Remove internal fields
				for field in ["modified", "modified_by", "creation", "owner", "docstatus", "doctype", "name"]:
					tool_dict.pop(field, None)
				
				# Export parameters (child table)
				if tool_function.parameters:
					params = []
					for param_row in tool_function.parameters:
						param_dict = param_row.as_dict()
						for field in ["modified", "modified_by", "creation", "owner", "docstatus", "doctype", "name", "parent", "parenttype", "parentfield", "idx"]:
							param_dict.pop(field, None)
						params.append(param_dict)
					tool_dict["parameters"] = params
				else:
					tool_dict["parameters"] = []
				
				# Export HTTP headers if present
				if tool_function.http_headers:
					headers = []
					for header_row in tool_function.http_headers:
						header_dict = header_row.as_dict()
						for field in ["modified", "modified_by", "creation", "owner", "docstatus", "doctype", "name", "parent", "parenttype", "parentfield", "idx"]:
							header_dict.pop(field, None)
						headers.append(header_dict)
					tool_dict["http_headers"] = headers
				else:
					tool_dict["http_headers"] = []
				
				tool_functions.append(tool_dict)
		
		dependencies["agent_tool_functions"] = tool_functions
	
	return dependencies


def export_agent_to_file(agent_name: str, folder_path: Optional[str] = None) -> str:
	"""
	Export agent to JSON file.
	
	Args:
		agent_name: Name of the agent to export
		folder_path: Optional folder path to save the file. Defaults to site public files.
		
	Returns:
		Path to the exported JSON file
	"""
	agent_data = export_agent(agent_name, include_dependencies=True)
	
	if not folder_path:
		folder_path = frappe.get_site_path("public", "files", "agent_exports")
		os.makedirs(folder_path, exist_ok=True)
	
	# Create filename
	filename = f"{agent_name.replace(' ', '_')}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
	file_path = os.path.join(folder_path, filename)
	
	# Write to file
	with open(file_path, "w", encoding="utf-8") as f:
		json.dump(agent_data, f, indent=2, ensure_ascii=False)
	
	return file_path


def export_agent_bundle(agent_names: List[str]) -> Dict:
	"""
	Export multiple agents as a bundle.
	
	Future extension for multi-agent exports.
	
	Args:
		agent_names: List of agent names to export
		
	Returns:
		Dictionary containing all agents and their dependencies
	"""
	bundle = {
		"agents": [],
		"dependencies": {
			"ai_providers": {},
			"ai_models": {},
			"agent_tool_functions": {}
		},
		"metadata": {
			"version": "1.0",
			"exported_at": datetime.now().isoformat(),
			"exported_by": frappe.session.user,
			"app": "agentflo",
			"agent_count": len(agent_names)
		}
	}
	
	# Collect all dependencies
	all_providers = {}
	all_models = {}
	all_tools = {}
	
	for agent_name in agent_names:
		agent_data = export_agent(agent_name, include_dependencies=True)
		bundle["agents"].append(agent_data["agent"])
		
		# Merge dependencies
		deps = agent_data.get("dependencies", {})
		
		if "ai_provider" in deps:
			provider_name = deps["ai_provider"].get("provide_name")
			if provider_name:
				all_providers[provider_name] = deps["ai_provider"]
		
		if "ai_model" in deps:
			model_name = deps["ai_model"].get("model_name")
			if model_name:
				all_models[model_name] = deps["ai_model"]
		
		if "agent_tool_functions" in deps:
			for tool in deps["agent_tool_functions"]:
				tool_name = tool.get("tool_name")
				if tool_name:
					all_tools[tool_name] = tool
	
	bundle["dependencies"]["ai_providers"] = list(all_providers.values())
	bundle["dependencies"]["ai_models"] = list(all_models.values())
	bundle["dependencies"]["agent_tool_functions"] = list(all_tools.values())
	
	return bundle


def import_agent(agent_data: Dict, import_mode: str = "merge") -> str:
	"""
	Import an agent from structured dictionary.
	
	Args:
		agent_data: Dictionary containing agent data and dependencies
		import_mode: How to handle conflicts
			- "merge": Update if exists
			- "skip": Skip if exists
			- "overwrite": Replace if exists (dangerous)
			
	Returns:
		Name of the imported agent
	"""
	if not agent_data:
		frappe.throw(_("Agent data is required"))
	
	# Validate structure
	if "agent" not in agent_data:
		frappe.throw(_("Invalid agent data format: missing 'agent' key"))
	
	agent_dict = agent_data["agent"]
	dependencies = agent_data.get("dependencies", {})
	
	# Check if agent already exists
	agent_name = agent_dict.get("agent_name")
	if not agent_name:
		frappe.throw(_("Agent name is required"))
	
	agent_exists = frappe.db.exists("Agent", agent_name)
	
	# Resolve dependencies first (needed for both create and update)
	resolved_deps = resolve_dependencies(dependencies)
	
	if agent_exists:
		if import_mode == "skip":
			frappe.msgprint(_("Agent '{0}' already exists. Skipping import.").format(agent_name))
			return agent_name
		elif import_mode == "overwrite":
			# Delete existing agent
			frappe.delete_doc("Agent", agent_name, force=1, ignore_permissions=True)
			frappe.db.commit()
			# Create new agent (fall through to creation logic)
			agent = frappe.new_doc("Agent")
		elif import_mode == "merge":
			# Update existing agent
			agent = frappe.get_doc("Agent", agent_name)
			
			# Update agent fields (excluding child tables and internal fields)
			agent_fields = {k: v for k, v in agent_dict.items() 
				if k not in ["agent_tool", "name", "doctype", "modified", "modified_by", "creation", "owner"]}
			agent.update(agent_fields)
			
			# Update provider and model from resolved dependencies
			if resolved_deps.get("provider"):
				agent.provider = resolved_deps.get("provider")
			if resolved_deps.get("model"):
				agent.model = resolved_deps.get("model")
			
			# Clear existing tools and add new ones
			agent.agent_tool = []
			if "agent_tool_functions" in dependencies:
				tool_names = resolved_deps.get("tool_functions", [])
				for tool_name in tool_names:
					agent.append("agent_tool", {"tool": tool_name})
			
			# Save updated agent
			agent.save(ignore_permissions=True)
			frappe.db.commit()
			frappe.msgprint(_("Agent '{0}' updated successfully.").format(agent_name))
			return agent_name
	else:
		# Create new agent document
		agent = frappe.new_doc("Agent")
		
		# Update agent fields (excluding child tables)
		agent_fields = {k: v for k, v in agent_dict.items() if k != "agent_tool"}
		agent.update(agent_fields)
		
		# Set provider and model from resolved dependencies
		if resolved_deps.get("provider"):
			agent.provider = resolved_deps.get("provider")
		if resolved_deps.get("model"):
			agent.model = resolved_deps.get("model")
		
		# Set agent tools
		if "agent_tool_functions" in dependencies:
			tool_names = resolved_deps.get("tool_functions", [])
			for tool_name in tool_names:
				agent.append("agent_tool", {"tool": tool_name})
		
		# Save agent
		agent.insert(ignore_permissions=True)
		frappe.db.commit()
	
	frappe.msgprint(_("Agent '{0}' imported successfully.").format(agent_name))
	return agent_name


def resolve_dependencies(dependencies: Dict) -> Dict:
	"""
	Resolve dependencies during import.
	
	Creates missing dependencies or links to existing ones.
	
	Returns:
		Dictionary with resolved dependency names:
		- provider: Provider name
		- model: Model name
		- tool_functions: List of tool function names
	"""
	resolved = {}
	
	# Resolve AI Provider
	if "ai_provider" in dependencies:
		provider_data = dependencies["ai_provider"]
		provider_name = provider_data.get("provide_name")
		
		if provider_name:
			# Check if provider exists (exact match first)
			if frappe.db.exists("AI Provider", provider_name):
				resolved["provider"] = provider_name
			else:
				# Try case-insensitive match
				existing_provider = frappe.db.get_value(
					"AI Provider",
					{"provide_name": ("like", f"%{provider_name}%")},
					"name"
				)
				
				if existing_provider:
					resolved["provider"] = existing_provider
				else:
					# Create new provider
					provider = frappe.new_doc("AI Provider")
					provider.provide_name = provider_name
					# Ensure API key is empty (user must configure)
					provider.api_key = ""
					provider.insert(ignore_permissions=True)
					resolved["provider"] = provider.name
					frappe.db.commit()
	
	# Resolve AI Model
	if "ai_model" in dependencies:
		model_data = dependencies["ai_model"]
		model_name = model_data.get("model_name")
		provider_name_for_model = model_data.get("provider_name") or resolved.get("provider")
		
		if model_name:
			# Check if model exists (by name)
			if frappe.db.exists("AI Model", model_name):
				# Verify provider matches
				existing_model_provider = frappe.db.get_value("AI Model", model_name, "provider")
				if existing_model_provider == provider_name_for_model or not provider_name_for_model:
					resolved["model"] = model_name
				else:
					# Provider mismatch - create new model with different name or use existing
					# For now, use existing (assume compatibility)
					resolved["model"] = model_name
			else:
				# Model doesn't exist - create it
				if provider_name_for_model:
					model = frappe.new_doc("AI Model")
					model.model_name = model_name
					model.provider = provider_name_for_model
					model.insert(ignore_permissions=True)
					resolved["model"] = model.name
					frappe.db.commit()
				else:
					frappe.throw(_("Cannot create AI Model '{0}' without a provider").format(model_name))
	
	# Resolve Agent Tool Functions
	if "agent_tool_functions" in dependencies:
		tool_functions = []
		for tool_data in dependencies["agent_tool_functions"]:
			tool_name = tool_data.get("tool_name")
			
			if tool_name:
				# Check if tool exists
				if frappe.db.exists("Agent Tool Function", tool_name):
					tool_functions.append(tool_name)
				else:
					# Create new tool function
					tool_function = frappe.new_doc("Agent Tool Function")
					tool_function.update(tool_data)
					
					# Handle tool_type - if not provided, try to infer or use default
					if not tool_function.tool_type and tool_data.get("types"):
						# Try to find a matching tool type or create a default one
						tool_type_name = "Standard"
						if not frappe.db.exists("Agent Tool Type", tool_type_name):
							# Create default tool type if it doesn't exist
							tool_type = frappe.new_doc("Agent Tool Type")
							tool_type.name1 = tool_type_name
							tool_type.insert(ignore_permissions=True)
							frappe.db.commit()
						tool_function.tool_type = tool_type_name
					
					# Handle parameters
					if "parameters" in tool_data:
						for param_data in tool_data["parameters"]:
							tool_function.append("parameters", param_data)
					
					# Handle HTTP headers
					if "http_headers" in tool_data:
						for header_data in tool_data["http_headers"]:
							tool_function.append("http_headers", header_data)
					
					tool_function.insert(ignore_permissions=True)
					tool_functions.append(tool_function.name)
					frappe.db.commit()
		
		resolved["tool_functions"] = tool_functions
	
	return resolved


def import_agent_from_file(file_path: str, import_mode: str = "merge") -> str:
	"""
	Import agent from JSON file.
	
	Args:
		file_path: Path to the JSON file, file URL, or file name from Frappe File doctype
		import_mode: How to handle conflicts (merge/skip/overwrite)
		
	Returns:
		Name of the imported agent
	"""
	# Handle file URL (from Frappe File doctype)
	if file_path.startswith("/files/"):
		# Public file
		file_path = frappe.get_site_path("public", "files", file_path.replace("/files/", ""))
	elif file_path.startswith("/private/files/"):
		# Private file
		file_path = frappe.get_site_path("private", "files", file_path.replace("/private/files/", ""))
	elif not os.path.isabs(file_path):
		# Try to get file from Frappe File doctype by name
		if frappe.db.exists("File", file_path):
			file_doc = frappe.get_doc("File", file_path)
			if file_doc.file_url:
				if file_doc.file_url.startswith("/files/"):
					file_path = frappe.get_site_path("public", "files", file_doc.file_url.replace("/files/", ""))
				elif file_doc.file_url.startswith("/private/files/"):
					file_path = frappe.get_site_path("private", "files", file_doc.file_url.replace("/private/files/", ""))
			elif file_doc.file_name:
				# Try to construct path from file_name
				file_path = frappe.get_site_path("public", "files", file_doc.file_name)
		else:
			# Try relative to site path
			if not os.path.exists(file_path):
				file_path = frappe.get_site_path(file_path)
	
	if not os.path.exists(file_path):
		frappe.throw(_("File not found: {0}").format(file_path))
	
	with open(file_path, "r", encoding="utf-8") as f:
		agent_data = json.load(f)
	
	return import_agent(agent_data, import_mode)
