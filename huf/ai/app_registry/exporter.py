# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - export DocType to JSON definition format

from __future__ import annotations

import json

import frappe


def _export_provider(doc: "frappe.Document") -> dict:
	return {
		"type": "provider",
		"provider_name": doc.provider_name,
		"is_local_llm": doc.is_local_llm or False,
		"url": doc.url,
		"port": doc.port,
		"version": "1.0",
	}


def _export_model(doc: "frappe.Document") -> dict:
	return {
		"type": "model",
		"model_name": doc.model_name,
		"provider": doc.provider,
		"version": "1.0",
	}


def _export_prompt(doc: "frappe.Document") -> dict:
	return {
		"type": "prompt",
		"title": doc.title,
		"slug": doc.slug,
		"description": doc.description or "",
		"category": doc.category,
		"visibility": doc.visibility or "App",
		"tags": doc.tags or "",
		"prompt_body": doc.prompt_body,
		"is_active": doc.is_active if doc.is_active is not None else True,
		"version": "1.0",
	}


def _export_tool(doc: "frappe.Document") -> dict:
	data = {
		"type": "tool",
		"tool_name": doc.tool_name,
		"description": doc.description,
		"tool_type": doc.tool_type or "App Provided",
		"types": doc.types or "App Provided",
		"function_path": doc.function_path,
		"reference_doctype": doc.reference_doctype,
		"base_url": doc.base_url,
		"pass_parameters_as_json": doc.pass_parameters_as_json or False,
		"is_read_only": doc.is_read_only or False,
		"allowed_for_guest": doc.allowed_for_guest or False,
		"required_permission": doc.required_permission,
		"agent": doc.agent,
		"version": "1.0",
	}
	data["parameters"] = []
	for p in doc.parameters or []:
		data["parameters"].append({
			"label": p.label,
			"fieldname": p.fieldname,
			"type": p.type,
			"required": bool(p.required),
			"description": p.description or "",
			"options": p.options or "",
		})
	data["http_headers"] = []
	for h in doc.http_headers or []:
		data["http_headers"].append({"key": h.key, "value": h.value})
	return data


def _export_knowledge(doc: "frappe.Document") -> dict:
	return {
		"type": "knowledge",
		"source_name": doc.source_name,
		"description": doc.description or "",
		"knowledge_type": doc.knowledge_type or "sqlite_fts",
		"scope": doc.scope or "Global",
		"storage_mode": doc.storage_mode or "Frappe File",
		"chunk_size": doc.chunk_size or 512,
		"chunk_overlap": doc.chunk_overlap or 50,
		"disabled": doc.disabled or False,
		"embedding_model": doc.embedding_model,
		"vector_dimension": doc.vector_dimension,
		"embedding_provider": doc.embedding_provider,
		"version": "1.0",
	}


def _export_agent(doc: "frappe.Document") -> dict:
	data = {
		"type": "agent",
		"agent_name": doc.agent_name,
		"description": doc.description or "",
		"provider": doc.provider,
		"model": doc.model,
		"prompt_mode": doc.prompt_mode or "Local",
		"instructions": doc.instructions or "",
		"agent_prompt": frappe.db.get_value("Agent Prompt", doc.agent_prompt, "slug") if doc.agent_prompt else None,
		"temperature": doc.temperature if doc.temperature is not None else 1.0,
		"top_p": doc.top_p if doc.top_p is not None else 1.0,
		"allow_chat": doc.allow_chat or False,
		"persist_conversation": doc.persist_conversation if doc.persist_conversation is not None else True,
		"persist_user_history": doc.persist_user_history if doc.persist_user_history is not None else True,
		"allow_guest": doc.allow_guest or False,
		"disabled": doc.disabled or False,
		"context_strategy": doc.context_strategy or "Summarize",
		"history_limit": doc.history_limit or 20,
		"max_turns": doc.max_turns or 20,
		"max_knowledge_tokens": doc.max_knowledge_tokens or 4000,
		"tts_model": doc.tts_model,
		"tts_voice": doc.tts_voice,
		"image_generation_model": doc.image_generation_model,
		"enable_prompt_caching": doc.enable_prompt_caching or False,
		"enable_conversation_data": doc.enable_conversation_data or False,
		"autonaming_of_conversation_title": doc.autonaming_of_conversation_title if doc.autonaming_of_conversation_title is not None else True,
		"version": "1.0",
	}
	data["tools"] = [row.tool for row in (doc.agent_tool or []) if row.tool]
	data["mcp_servers"] = [
		row.mcp_server for row in (doc.agent_mcp_server or [])
		if row.mcp_server and row.enabled
	]
	data["knowledge"] = []
	for row in doc.agent_knowledge or []:
		if row.knowledge_source:
			data["knowledge"].append({
				"source": row.knowledge_source,
				"mode": (row.mode or "optional").lower(),
				"priority": row.priority or 0,
				"max_chunks": row.max_chunks or 5,
				"token_budget": row.token_budget or 2000,
			})
	return data


def _export_trigger(doc: "frappe.Document") -> dict:
	return {
		"type": "trigger",
		"trigger_name": doc.trigger_name,
		"agent": doc.agent,
		"trigger_type": doc.trigger_type,
		"disabled": doc.disabled or False,
		"reference_doctype": doc.reference_doctype,
		"doc_event": doc.doc_event,
		"condition": doc.condition,
		"scheduled_interval": doc.scheduled_interval,
		"interval_count": doc.interval_count or 1,
		"webhook_slug": doc.webhook_slug,
		"webhook_key": doc.webhook_key,
		"app_name": doc.app_name,
		"event_name": doc.event_name,
		"metadata": doc.metadata,
		"version": "1.0",
	}


EXPORTERS = {
	"AI Provider": ("provider", _export_provider, "provider_name"),
	"AI Model": ("model", _export_model, "model_name"),
	"Agent Prompt": ("prompt", _export_prompt, "slug"),
	"Agent Tool Function": ("tool", _export_tool, "tool_name"),
	"Knowledge Source": ("knowledge", _export_knowledge, "source_name"),
	"Agent": ("agent", _export_agent, "agent_name"),
	"Agent Trigger": ("trigger", _export_trigger, "trigger_name"),
}


def export_definition(doctype: str, name: str) -> dict:
	"""
	Export a HUF DocType document as a JSON definition.

	Args:
		doctype: DocType name (e.g. "Agent", "Agent Tool Function")
		name: Document name

	Returns:
		dict with "filename" and "content" (JSON string)
	"""
	config = EXPORTERS.get(doctype)
	if not config:
		frappe.throw(f"Export not supported for doctype: {doctype}")

	_type, exporter_fn, key_field = config
	doc = frappe.get_doc(doctype, name)
	data = exporter_fn(doc)

	# Build filename from key
	key_val = doc.get(key_field) or name
	safe_name = str(key_val).replace(" ", "_").lower()
	filename = f"{safe_name}.{_type}.json"
	content = json.dumps(data, indent=2, ensure_ascii=False)

	return {"filename": filename, "content": content}


def export_agent_bundle(agent_name: str) -> dict[str, str]:
	"""
	Export an agent with all referenced tools, prompts, knowledge, triggers.

	Returns:
		dict mapping file paths to JSON content.
		e.g. {"agents/lead_assistant.agent.json": "{...}", "tools/create_lead.tool.json": "{...}"}
	"""
	agent_doc = frappe.get_doc("Agent", agent_name)
	bundle = {}

	# Export agent
	agent_data = _export_agent(agent_doc)
	safe_name = agent_name.replace(" ", "_").lower()
	bundle[f"agents/{safe_name}.agent.json"] = json.dumps(agent_data, indent=2, ensure_ascii=False)

	# Export tools
	for row in agent_doc.agent_tool or []:
		if row.tool:
			tool_doc = frappe.get_doc("Agent Tool Function", row.tool)
			tool_data = _export_tool(tool_doc)
			tool_safe = (row.tool or "").replace(".", "_")
			bundle[f"tools/{tool_safe}.tool.json"] = json.dumps(tool_data, indent=2, ensure_ascii=False)

	# Export prompt if template mode
	if agent_doc.prompt_mode == "Template" and agent_doc.agent_prompt:
		prompt_doc = frappe.get_doc("Agent Prompt", agent_doc.agent_prompt)
		prompt_data = _export_prompt(prompt_doc)
		slug = prompt_doc.slug or prompt_doc.name
		bundle[f"prompts/{slug}.prompt.json"] = json.dumps(prompt_data, indent=2, ensure_ascii=False)

	# Export knowledge sources
	for row in agent_doc.agent_knowledge or []:
		if row.knowledge_source:
			ks_doc = frappe.get_doc("Knowledge Source", row.knowledge_source)
			ks_data = _export_knowledge(ks_doc)
			source_safe = (ks_doc.source_name or "").replace(" ", "_")
			bundle[f"knowledge/{source_safe}.knowledge.json"] = json.dumps(ks_data, indent=2, ensure_ascii=False)

	# Export triggers for this agent
	triggers = frappe.get_all(
		"Agent Trigger",
		filters={"agent": agent_name},
		pluck="name",
	)
	for tname in triggers:
		trigger_doc = frappe.get_doc("Agent Trigger", tname)
		trigger_data = _export_trigger(trigger_doc)
		trigger_safe = (trigger_doc.trigger_name or tname).replace(" ", "_").lower()
		bundle[f"triggers/{trigger_safe}.trigger.json"] = json.dumps(trigger_data, indent=2, ensure_ascii=False)

	return bundle


@frappe.whitelist()
def export_definition_api(doctype: str, name: str) -> dict:
	"""Whitelisted API for exporting a single definition."""
	return export_definition(doctype, name)


@frappe.whitelist()
def export_agent_bundle_api(agent_name: str) -> dict:
	"""Whitelisted API for exporting an agent bundle."""
	return export_agent_bundle(agent_name)
