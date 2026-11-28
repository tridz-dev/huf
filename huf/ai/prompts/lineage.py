# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Lookups across the version lineage of Agent Prompt / Agent Summary Prompt.

Every version of a prompt is its own row, and all rows of one lineage share
``prompt_group``.  Several rows can therefore carry the same title, so any
lookup by title or slug must land on the ``is_latest`` row.
"""

import frappe
from frappe import _

PROMPT_DOCTYPES = ("Agent Prompt", "Agent Summary Prompt")


def latest_row(doctype, name):
	"""Return the name of the latest version in the lineage of ``name``."""
	if not name:
		return name
	data = frappe.db.get_value(doctype, name, ["prompt_group", "is_latest"], as_dict=True)
	if not data or data.is_latest or not data.prompt_group:
		return name
	latest = frappe.db.get_value(doctype, {"prompt_group": data.prompt_group, "is_latest": 1}, "name")
	return latest or name


def find_latest_by_field(doctype, fieldname, value):
	"""Name of the latest row whose ``fieldname`` equals ``value``, else ``None``."""
	rows = frappe.get_all(
		doctype,
		filters={fieldname: value},
		fields=["name"],
		order_by="is_latest desc, version desc, creation desc",
		limit=1,
	)
	return latest_row(doctype, rows[0].name) if rows else None


def find_seed_target(doctype, key_field, key_val):
	"""Existing document a seed upsert must update (the latest version for prompts)."""
	if doctype in PROMPT_DOCTYPES:
		return find_latest_by_field(doctype, key_field, key_val)
	return frappe.db.get_value(doctype, {key_field: key_val})


def resolve_prompt_link(item, warnings, doctype="Agent Prompt"):
	"""Resolve a skill manifest prompt reference to the latest prompt row name."""
	if not item:
		return None
	if isinstance(item, dict):
		candidates = [
			("slug", item.get("slug") or item.get("name")),
			("title", item.get("prompt")),
			("title", item.get("title")),
		]
	else:
		candidates = [("slug", str(item)), ("title", str(item))]

	for fieldname, value in candidates:
		if not value:
			continue
		found = find_latest_by_field(doctype, fieldname, value)
		if found:
			return found
		if fieldname == "slug" and frappe.db.exists(doctype, value):
			return latest_row(doctype, value)

	label = next((v for _f, v in candidates if v), "")
	warnings.append(_("Referenced {0} '{1}' does not exist; skipping.").format(doctype, label))
	return None
