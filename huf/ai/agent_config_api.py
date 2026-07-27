"""Section-oriented Agent configuration API.

The Agent DocType remains the canonical runtime aggregate. These endpoints
only change the editor transport boundary: callers load and save one cohesive
section at a time instead of round-tripping every field and child table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import get_datetime


AGENT_SECTIONS: dict[str, tuple[str, ...]] = {
	"general": (
		"agent_name",
		"provider",
		"model",
		"temperature",
		"top_p",
		"disabled",
		"run_immediately",
		"description",
		"instructions",
		"prompt_mode",
		"agent_prompt",
		"prompt_version_locked",
		"template_version_at_attach",
		"copied_from_prompt",
		"enable_prompt_caching",
		"cache_control_type",
		"cache_system_message",
		"cache_conversation_history",
		"is_system",
		"last_run",
		"total_run",
	),
	"behavior": (
		"allow_chat",
		"persist_conversation",
		"persist_user_history",
		"enable_multi_run",
		"default_plan",
	),
	"tools": ("agent_tool", "agent_mcp_server"),
	"knowledge": ("agent_knowledge",),
	"skills": ("agent_skill",),
	"permissions": ("allow_guest", "allowed_users", "allowed_roles"),
	"advanced": (
		"context_strategy",
		"summary_model",
		"summary_ratio",
		"summary_prompt_mode",
		"summary_prompt_template",
		"summary_prompt_version_locked",
		"summary_template_version_at_attach",
		"summary_prompt",
		"copied_from_summary_prompt",
		"history_limit",
		"max_knowledge_tokens",
		"max_turns",
		"max_context_chars",
		"enable_conversation_data",
		"inject_conversation_data",
		"conversation_data_api_permission",
		"autonaming_of_conversation_title",
		"enable_memory",
		"memory_policy",
		"enable_memory_search_tool",
		"enable_memory_write_tool",
		"agent_color",
		"show_tool_execution_details",
		"image_generation_model",
		"tts_model",
		"tts_voice",
		"stt_model",
		"allow_file_upload",
		"enable_ocr",
		"max_upload_size_mb",
		"allow_code_execution",
		"execution_profile",
		"execution_shared_dir_limit_mb",
		"allow_ssh",
		"ssh_connections",
	),
}

READ_ONLY_FIELDS = {
	"is_system",
	"last_run",
	"total_run",
	"copied_from_prompt",
	"copied_from_summary_prompt",
}


def _get_section_fields(section: str) -> tuple[str, ...]:
	try:
		return AGENT_SECTIONS[section]
	except KeyError:
		frappe.throw(
			_("Unknown Agent configuration section: {0}").format(section),
			frappe.ValidationError,
		)


def _serialize_value(value):
	if isinstance(value, list):
		return [row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else row for row in value]
	return value


def _parse_values(values) -> dict:
	if isinstance(values, str):
		values = json.loads(values)
	if not isinstance(values, Mapping):
		frappe.throw(_("Section values must be a JSON object."), frappe.ValidationError)
	return dict(values)


def _assert_revision(agent_doc, expected_modified: str) -> None:
	if not expected_modified:
		frappe.throw(_("The Agent revision is required. Reload this section and try again."), frappe.ValidationError)
	if get_datetime(agent_doc.modified) != get_datetime(expected_modified):
		raise frappe.TimestampMismatchError(
			_("This Agent changed after the section was loaded. Reload the section before saving.")
		)


def _section_response(agent_doc, section: str) -> dict:
	return {
		"name": agent_doc.name,
		"section": section,
		"modified": str(agent_doc.modified),
		"values": {
			field: _serialize_value(agent_doc.get(field))
			for field in _get_section_fields(section)
		},
	}


@frappe.whitelist()
def get_agent_section(agent_name: str, section: str) -> dict:
	"""Return one editor section and the revision it was read from."""
	agent_doc = frappe.get_doc("Agent", agent_name)
	agent_doc.check_permission("read")
	return _section_response(agent_doc, section)


@frappe.whitelist(methods=["POST"])
def update_agent_section(
	agent_name: str,
	section: str,
	values,
	expected_modified: str,
) -> dict:
	"""Revision-check and replace the editable values in one Agent section."""
	fields = set(_get_section_fields(section))
	editable_fields = fields - READ_ONLY_FIELDS
	parsed_values = _parse_values(values)
	unknown_fields = set(parsed_values) - editable_fields
	if unknown_fields:
		frappe.throw(
			_("Fields do not belong to section {0}: {1}").format(
				section, ", ".join(sorted(unknown_fields))
			),
			frappe.ValidationError,
		)

	agent_doc = frappe.get_doc("Agent", agent_name)
	agent_doc.check_permission("write")
	_assert_revision(agent_doc, expected_modified)

	new_agent_name = parsed_values.pop("agent_name", None)
	if new_agent_name is not None:
		new_agent_name = str(new_agent_name).strip()
		if not new_agent_name:
			frappe.throw(_("Agent name is required."), frappe.ValidationError)
		if new_agent_name != agent_doc.name:
			frappe.rename_doc("Agent", agent_doc.name, new_agent_name)
			agent_doc = frappe.get_doc("Agent", new_agent_name)

	for field, value in parsed_values.items():
		agent_doc.set(field, value)

	agent_doc.save()
	return _section_response(agent_doc, section)
