# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - DocType upsert logic

from __future__ import annotations

import frappe

# Map definition type to (DocType, key_field)
TYPE_CONFIG = {
	"provider": ("AI Provider", "provider_name"),
	"model": ("AI Model", "model_name"),
	"prompt": ("Agent Prompt", "slug"),
	"tool": ("Agent Tool Function", "tool_name"),
	"knowledge": ("Knowledge Source", "source_name"),
	"agent": ("Agent", "agent_name"),
	"trigger": ("Agent Trigger", "trigger_name"),
}


def upsert_definition(
	doctype: str,
	key_field: str,
	key_value: str,
	payload: dict,
	*,
	skip_sensitive: bool = False,
) -> str | None:
	"""
	Create or update a DocType document.

	Args:
		doctype: Target DocType name
		key_field: Field used as primary key for lookup
		key_value: Value of the key field
		payload: Full payload (will be filtered for insert/update)
		skip_sensitive: If True, do not overwrite Password/encrypted fields (for AI Provider)

	Returns:
		Document name if successful, None otherwise.
	"""
	# Filter payload to only include valid doctype fields
	meta = frappe.get_meta(doctype)
	allowed = {f.fieldname for f in meta.fields}
	filtered = {k: v for k, v in payload.items() if k in allowed and v is not None}

	# Never overwrite api_key from file definitions
	if skip_sensitive and "api_key" in filtered:
		del filtered["api_key"]

	existing = frappe.db.get_value(doctype, {key_field: key_value}, "name")

	if existing:
		doc = frappe.get_doc(doctype, existing)
		# For update: exclude read_only, auto-calculated fields from overwrite
		for k, v in list(filtered.items()):
			if meta.get_field(k) and meta.get_field(k).read_only:
				del filtered[k]
		doc.update(filtered)
		doc.save(ignore_permissions=True)
		return doc.name

	# Insert
	filtered["doctype"] = doctype
	doc = frappe.get_doc(filtered)
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def import_definition(
	definition_type: str,
	payload: dict,
	*,
	skip_sensitive: bool = False,
) -> str | None:
	"""
	Import a single normalised definition.

	Args:
		definition_type: Singular type (agent, tool, etc.)
		payload: Normalised payload from normaliser
		skip_sensitive: Skip overwriting sensitive fields (for providers)

	Returns:
		Document name if successful, None otherwise.
	"""
	config = TYPE_CONFIG.get(definition_type)
	if not config:
		return None

	doctype, key_field = config
	key_value = payload.get(key_field)
	if not key_value:
		return None

	skip_sensitive = skip_sensitive or (definition_type == "provider")
	return upsert_definition(
		doctype,
		key_field,
		key_value,
		payload,
		skip_sensitive=skip_sensitive,
	)
