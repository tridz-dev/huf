# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Version creation for Agent Prompt / Agent Summary Prompt.

``save_prompt_changes`` backs the prompt form: a changed body creates a new
immutable version, a metadata-only change updates the row, an unchanged save
does nothing.  The DocType controllers never version, so seeding, import and
Desk writes keep editing rows in place.
"""

import frappe
from frappe import _
from frappe.utils import cint

# Fields copied onto a new version, and the ones the form may change (slug is
# fixed after creation).
META_FIELDS = ("title", "category", "description", "visibility", "is_active", "tags")

# Agent fields that point at a prompt row, per prompt doctype.
AGENT_LINKS = {
	"Agent Prompt": {
		"mode": "prompt_mode",
		"link": "agent_prompt",
		"locked": "prompt_version_locked",
		"version": "template_version_at_attach",
	},
	"Agent Summary Prompt": {
		"mode": "summary_prompt_mode",
		"link": "summary_prompt_template",
		"locked": "summary_prompt_version_locked",
		"version": "summary_template_version_at_attach",
	},
}


def _same(field, current, new):
	if field == "is_active":
		return cint(current) == cint(new)
	return (current or "") == (new or "")


def move_links(doctype, old_name, new_name, new_version):
	"""Point unlocked agents, and skills, from the old row to the new version.

	Version-locked agents stay on the old row so they keep the old body.
	"""
	cfg = AGENT_LINKS[doctype]
	agents = frappe.get_all(
		"Agent",
		filters={cfg["mode"]: "Template", cfg["link"]: old_name, cfg["locked"]: 0},
		pluck="name",
	)
	for agent_name in agents:
		frappe.db.set_value(
			"Agent",
			agent_name,
			{cfg["link"]: new_name, cfg["version"]: new_version},
			update_modified=False,
		)
	if doctype == "Agent Prompt":
		frappe.db.set_value("Skill Prompt", {"prompt": old_name}, "prompt", new_name, update_modified=False)


def create_version(doctype, current, prompt_body, **overrides):
	"""Insert V(n+1) of ``current`` and move the links of unlocked consumers."""
	values = {f: getattr(current, f, None) for f in META_FIELDS}
	values.update({k: v for k, v in overrides.items() if v is not None and k in META_FIELDS})
	new_version = cint(current.version) + 1

	frappe.db.set_value(doctype, current.name, "is_latest", 0, update_modified=False)
	new_doc = frappe.get_doc(
		{
			"doctype": doctype,
			**values,
			"prompt_body": prompt_body,
			"is_system": 0,
			"version": new_version,
			"is_latest": 1,
			"previous_version": current.name,
			"forked_from": current.forked_from,
			"prompt_group": current.prompt_group or current.name,
		}
	)
	new_doc.insert()
	move_links(doctype, current.name, new_doc.name, new_version)
	return new_doc


def save_prompt_changes(doctype, name, values):
	"""Apply a form save.  Returns ``{"name", "version", "versioned", "changed"}``."""
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")

	if not cint(doc.is_latest):
		frappe.throw(_("Older versions are read-only. Edit the latest version instead."))

	meta = {f: values[f] for f in META_FIELDS if f in values}
	body = values.get("prompt_body")
	body_changed = body is not None and body != doc.prompt_body
	meta_changed = any(not _same(f, getattr(doc, f, None), v) for f, v in meta.items())

	if body_changed:
		if cint(doc.is_system):
			frappe.throw(_("System prompts cannot be versioned by users."))
		new_doc = create_version(doctype, doc, body, **meta)
		return {"name": new_doc.name, "version": cint(new_doc.version), "versioned": True, "changed": True}

	if meta_changed:
		doc.update(meta)
		doc.save()
	return {"name": doc.name, "version": cint(doc.version), "versioned": False, "changed": meta_changed}
