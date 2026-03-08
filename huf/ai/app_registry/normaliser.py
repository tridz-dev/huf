# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - payload normalisation for DocType upsert

from __future__ import annotations

import os

import frappe


def _relative_path(file_path: str, app_name: str) -> str:
	"""Build a relative path like 'crm/huf/tools/create_lead.tool.json'."""
	app_path = frappe.get_app_path(app_name)
	# file_path is absolute; make it relative to app root
	try:
		return os.path.relpath(file_path, os.path.dirname(app_path))
	except ValueError:
		return file_path


def normalise_provider(data: dict, app_name: str, source_file: str) -> dict:
	payload = {
		"provider_name": data.get("provider_name"),
		"is_local_llm": data.get("is_local_llm", False),
		"url": data.get("url"),
		"port": data.get("port"),
		"source_app": app_name,
		"source_file": source_file,
	}
	return {k: v for k, v in payload.items() if v is not None or k in ("is_local_llm",)}


def normalise_model(data: dict, app_name: str, source_file: str) -> dict:
	return {
		"model_name": data.get("model_name"),
		"provider": data.get("provider"),
		"source_app": app_name,
		"source_file": source_file,
	}


def normalise_prompt(data: dict, app_name: str, source_file: str) -> dict:
	return {
		"title": data.get("title"),
		"slug": data.get("slug"),
		"description": data.get("description") or "",
		"category": data.get("category"),
		"visibility": data.get("visibility", "App"),
		"tags": data.get("tags") or "",
		"prompt_body": data.get("prompt_body", ""),
		"is_active": data.get("is_active", True),
		"source_app": app_name,
		"source_file": source_file,
	}


def normalise_tool(data: dict, app_name: str, source_file: str) -> dict:
	# Ensure App Provided tool type exists
	if not frappe.db.exists("Agent Tool Type", "App Provided"):
		doc = frappe.get_doc({"doctype": "Agent Tool Type", "name1": "App Provided"})
		doc.insert(ignore_permissions=True)

	payload = {
		"tool_name": data.get("tool_name"),
		"description": data.get("description"),
		"tool_type": "App Provided",
		"types": data.get("types", "App Provided"),
		"function_path": data.get("function_path"),
		"reference_doctype": data.get("reference_doctype"),
		"base_url": data.get("base_url"),
		"pass_parameters_as_json": data.get("pass_parameters_as_json", False),
		"is_read_only": data.get("is_read_only", False),
		"allowed_for_guest": data.get("allowed_for_guest", False),
		"required_permission": data.get("required_permission"),
		"agent": data.get("agent"),
		"provider_app": app_name,
		"source_app": app_name,
		"source_file": source_file,
	}

	# Parameters
	params = data.get("parameters") or []
	if isinstance(params, dict):
		params = []
	payload["parameters"] = []
	for p in params:
		if not isinstance(p, dict):
			continue
		payload["parameters"].append({
			"label": p.get("label", ""),
			"fieldname": p.get("fieldname", ""),
			"type": p.get("type", "string"),
			"required": 1 if p.get("required") else 0,
			"description": p.get("description") or "",
			"options": p.get("options") or "",
		})

	# HTTP headers
	headers = data.get("http_headers") or []
	if isinstance(headers, dict):
		headers = []
	payload["http_headers"] = []
	for h in headers:
		if isinstance(h, dict) and h.get("key") is not None:
			payload["http_headers"].append({
				"key": h.get("key", ""),
				"value": h.get("value", ""),
			})

	return payload


def normalise_knowledge(data: dict, app_name: str, source_file: str) -> dict:
	return {
		"source_name": data.get("source_name"),
		"description": data.get("description") or "",
		"knowledge_type": data.get("knowledge_type", "sqlite_fts"),
		"scope": data.get("scope", "Global"),
		"storage_mode": data.get("storage_mode", "Frappe File"),
		"chunk_size": data.get("chunk_size", 512),
		"chunk_overlap": data.get("chunk_overlap", 50),
		"disabled": data.get("disabled", False),
		"embedding_model": data.get("embedding_model"),
		"vector_dimension": data.get("vector_dimension", 1536),
		"embedding_provider": data.get("embedding_provider"),
		"source_app": app_name,
		"source_file": source_file,
	}


def _resolve_prompt_slug(slug: str) -> str | None:
	"""Resolve prompt slug to Agent Prompt document name."""
	if not slug:
		return None
	name = frappe.db.get_value("Agent Prompt", {"slug": slug}, "name")
	return name


def normalise_agent(data: dict, app_name: str, source_file: str) -> dict:
	payload = {
		"agent_name": data.get("agent_name"),
		"description": data.get("description") or "",
		"provider": data.get("provider"),
		"model": data.get("model"),
		"prompt_mode": data.get("prompt_mode", "Local"),
		"instructions": data.get("instructions") or "",
		"temperature": data.get("temperature", 1.0),
		"top_p": data.get("top_p", 1.0),
		"allow_chat": data.get("allow_chat", False),
		"persist_conversation": data.get("persist_conversation", True),
		"persist_user_history": data.get("persist_user_history", True),
		"allow_guest": data.get("allow_guest", False),
		"disabled": data.get("disabled", False),
		"context_strategy": data.get("context_strategy", "Summarize"),
		"history_limit": data.get("history_limit", 20),
		"max_turns": data.get("max_turns", 20),
		"max_knowledge_tokens": data.get("max_knowledge_tokens", 4000),
		"tts_model": data.get("tts_model"),
		"tts_voice": data.get("tts_voice"),
		"image_generation_model": data.get("image_generation_model"),
		"enable_prompt_caching": data.get("enable_prompt_caching", False),
		"enable_conversation_data": data.get("enable_conversation_data", False),
		"autonaming_of_conversation_title": data.get("autonaming_of_conversation_title", True),
		"source_app": app_name,
		"source_file": source_file,
	}

	# Resolve agent_prompt (slug -> doc name)
	prompt_mode = data.get("prompt_mode", "Local")
	if prompt_mode == "Template":
		agent_prompt_slug = data.get("agent_prompt")
		if agent_prompt_slug:
			resolved = _resolve_prompt_slug(agent_prompt_slug)
			payload["agent_prompt"] = resolved

	# Tools -> agent_tool child table
	tool_names = data.get("tools") or []
	if not isinstance(tool_names, (list, tuple)):
		tool_names = []
	payload["agent_tool"] = []
	for tn in tool_names:
		if frappe.db.exists("Agent Tool Function", {"tool_name": tn}):
			payload["agent_tool"].append({"tool": tn})

	# MCP servers -> agent_mcp_server child table
	mcp_names = data.get("mcp_servers") or []
	if not isinstance(mcp_names, (list, tuple)):
		mcp_names = []
	payload["agent_mcp_server"] = []
	for mcp_name in mcp_names:
		if frappe.db.exists("MCP Server", {"server_name": mcp_name}):
			payload["agent_mcp_server"].append({
				"mcp_server": mcp_name,
				"enabled": 1,
			})

	# Knowledge -> agent_knowledge child table
	knowledge_list = data.get("knowledge") or []
	if not isinstance(knowledge_list, (list, tuple)):
		knowledge_list = []
	payload["agent_knowledge"] = []
	for k in knowledge_list:
		if not isinstance(k, dict):
			continue
		source = k.get("source")
		if not source or not frappe.db.exists("Knowledge Source", {"source_name": source}):
			continue
		payload["agent_knowledge"].append({
			"knowledge_source": source,
			"mode": (k.get("mode") or "optional").capitalize(),
			"priority": k.get("priority", 0),
			"max_chunks": k.get("max_chunks", 5),
			"token_budget": k.get("token_budget", 2000),
		})

	return payload


def normalise_trigger(data: dict, app_name: str, source_file: str) -> dict:
	return {
		"trigger_name": data.get("trigger_name"),
		"agent": data.get("agent"),
		"trigger_type": data.get("trigger_type"),
		"disabled": data.get("disabled", False),
		"reference_doctype": data.get("reference_doctype"),
		"doc_event": data.get("doc_event"),
		"condition": data.get("condition"),
		"scheduled_interval": data.get("scheduled_interval"),
		"interval_count": data.get("interval_count", 1),
		"webhook_slug": data.get("webhook_slug"),
		"webhook_key": data.get("webhook_key"),
		"app_name": data.get("app_name"),
		"event_name": data.get("event_name"),
		"metadata": data.get("metadata"),
		"source_app": app_name,
		"source_file": source_file,
	}


NORMALISERS = {
	"provider": normalise_provider,
	"model": normalise_model,
	"prompt": normalise_prompt,
	"tool": normalise_tool,
	"knowledge": normalise_knowledge,
	"agent": normalise_agent,
	"trigger": normalise_trigger,
}


def normalise(data: dict, definition_type: str, app_name: str, source_file: str) -> dict:
	"""
	Transform raw JSON definition into DocType-compatible payload.

	Args:
		data: Parsed JSON definition
		definition_type: Singular type (agent, tool, etc.)
		app_name: App that owns the definition
		source_file: Relative path to source file

	Returns:
		Payload dict for upsert.
	"""
	fn = NORMALISERS.get(definition_type)
	if fn:
		return fn(data, app_name, source_file)
	raise ValueError(f"Unknown definition type: {definition_type}")
