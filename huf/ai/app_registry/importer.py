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


def parse_version(version_str: str | None) -> tuple[int, ...]:
	"""
	Parse version string into comparable tuple.

	Args:
		version_str: Version string like "1.0", "1.2.3", "2.0.0-beta"

	Returns:
		Tuple of integers for comparison. Non-numeric parts are treated as 0.
	"""
	if not version_str:
		return (0,)

	# Remove common suffixes like -beta, -alpha, -rc
	version_str = version_str.split("-")[0]

	try:
		parts = version_str.split(".")
		return tuple(int(p) for p in parts if p.isdigit())
	except (ValueError, AttributeError):
		return (0,)


def compare_versions(v1: str | None, v2: str | None) -> int:
	"""
	Compare two version strings.

	Args:
		v1: First version string
		v2: Second version string

	Returns:
		-1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
	"""
	parsed1 = parse_version(v1)
	parsed2 = parse_version(v2)

	# Pad shorter tuple with zeros
	max_len = max(len(parsed1), len(parsed2))
	parsed1 = parsed1 + (0,) * (max_len - len(parsed1))
	parsed2 = parsed2 + (0,) * (max_len - len(parsed2))

	if parsed1 < parsed2:
		return -1
	elif parsed1 > parsed2:
		return 1
	else:
		return 0


def should_skip_import(
	existing_doc: "frappe.Document",
	new_payload: dict,
	definition_type: str
) -> tuple[bool, str]:
	"""
	Determine if import should be skipped based on version comparison.

	Args:
		existing_doc: Existing DocType document
		new_payload: New definition payload
		definition_type: Type of definition

	Returns:
		Tuple of (should_skip, reason)
	"""
	# Get versions
	existing_version = getattr(existing_doc, "version", None)
	new_version = new_payload.get("version")

	# If no versions specified, always update (current behavior)
	if not existing_version and not new_version:
		return (False, "No versions specified, proceeding with update")

	# If only new version specified, update
	if not existing_version and new_version:
		return (False, f"New version {new_version} (no existing version)")

	# If only existing version specified, update (assume new is latest)
	if existing_version and not new_version:
		return (False, f"No new version (existing: {existing_version})")

	# Compare versions
	comparison = compare_versions(new_version, existing_version)

	if comparison < 0:
		return (True, f"New version {new_version} is older than existing {existing_version}")
	elif comparison == 0:
		# Same version - check if content changed by comparing key fields
		key_field = TYPE_CONFIG.get(definition_type, (None, None))[1]
		if key_field:
			existing_value = getattr(existing_doc, key_field, None)
			new_value = new_payload.get(key_field)
			if existing_value == new_value:
				return (True, f"Version {new_version} unchanged, skipping")

	return (False, f"Updating from {existing_version} to {new_version}")
