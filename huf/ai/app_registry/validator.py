# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - type-specific validation

from __future__ import annotations

from dataclasses import dataclass, field

import frappe


@dataclass
class ValidationResult:
	errors: list[str] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)

	@property
	def is_valid(self) -> bool:
		return len(self.errors) == 0


def validate_provider(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("provider_name"):
		r.errors.append("provider_name is required")
	return r


def validate_model(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("model_name"):
		r.errors.append("model_name is required")
	if not data.get("provider"):
		r.errors.append("provider is required")
	return r


def validate_prompt(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("title"):
		r.errors.append("title is required")
	if not data.get("slug"):
		r.errors.append("slug is required")
	if not data.get("prompt_body"):
		r.errors.append("prompt_body is required and must be non-empty")
	elif not str(data.get("prompt_body", "")).strip():
		r.errors.append("prompt_body must be non-empty")
	return r


def _validate_function_path(path: str) -> bool:
	"""Validate that function_path resolves to a callable."""
	try:
		func = frappe.get_attr(path)
		return callable(func)
	except Exception:
		return False


def validate_tool(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("tool_name"):
		r.errors.append("tool_name is required")
	if not data.get("description"):
		r.errors.append("description is required")

	types_val = data.get("types", "App Provided")
	if types_val in ("Custom Function", "App Provided"):
		func_path = data.get("function_path")
		if not func_path:
			r.errors.append("function_path is required when types is Custom Function or App Provided")
		elif not _validate_function_path(func_path):
			r.errors.append(f"function_path '{func_path}' is not importable or not callable")

	params = data.get("parameters")
	if params is not None and not isinstance(params, (list, tuple)):
		r.errors.append("parameters must be an array")
	return r


def validate_knowledge(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("source_name"):
		r.errors.append("source_name is required")
	return r


def validate_agent(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("agent_name"):
		r.errors.append("agent_name is required")
	if not data.get("provider"):
		r.errors.append("provider is required")
	if not data.get("model"):
		r.errors.append("model is required")

	# Warnings for missing references (we'll omit them during normalisation)
	provider = data.get("provider")
	if provider and not frappe.db.exists("AI Provider", provider):
		r.warnings.append(f"referenced provider '{provider}' does not exist")

	model = data.get("model")
	if model and not frappe.db.exists("AI Model", model):
		r.warnings.append(f"referenced model '{model}' does not exist")

	return r


def validate_trigger(data: dict) -> ValidationResult:
	r = ValidationResult()
	if not data.get("trigger_name"):
		r.errors.append("trigger_name is required")
	if not data.get("agent"):
		r.errors.append("agent is required")
	else:
		agent = data.get("agent")
		if not frappe.db.exists("Agent", agent):
			r.errors.append(f"referenced agent '{agent}' does not exist")

	trigger_type = data.get("trigger_type")
	if trigger_type == "Doc Event":
		if not data.get("reference_doctype"):
			r.errors.append("reference_doctype is required for Doc Event triggers")
		elif not frappe.db.exists("DocType", data.get("reference_doctype")):
			r.errors.append(f"reference_doctype '{data.get('reference_doctype')}' does not exist")
		if not data.get("doc_event"):
			r.errors.append("doc_event is required for Doc Event triggers")

	if trigger_type == "Schedule" and not data.get("scheduled_interval"):
		r.errors.append("scheduled_interval is required for Schedule triggers")

	return r


VALIDATORS = {
	"provider": validate_provider,
	"model": validate_model,
	"prompt": validate_prompt,
	"tool": validate_tool,
	"knowledge": validate_knowledge,
	"agent": validate_agent,
	"trigger": validate_trigger,
}


def validate(data: dict, definition_type: str) -> ValidationResult:
	"""
	Validate a definition against type-specific rules.

	Args:
		data: Parsed JSON definition
		definition_type: Singular type (agent, tool, prompt, etc.)

	Returns:
		ValidationResult with errors and warnings.
	"""
	fn = VALIDATORS.get(definition_type)
	if fn:
		return fn(data)
	return ValidationResult(errors=[f"Unknown definition type: {definition_type}"])
