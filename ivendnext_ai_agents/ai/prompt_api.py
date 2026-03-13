# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Whitelisted API methods for Agent Prompt management.

Provides server-side operations for the prompt template system:
- Creating new versions (immutable model)
- Forking prompts
- Detaching agents from templates
- Saving local prompts as templates
- Retrieving version history
"""

import frappe
from frappe import _
from frappe.utils import cint


@frappe.whitelist()
def create_new_version(prompt_name, prompt_body, title=None, description=None):
	"""Create a new immutable version of an existing Agent Prompt.

	The current prompt is marked as ``is_latest = 0`` and a new row is
	inserted with an incremented version number.  All agents that are
	**not** version-locked will automatically pick up the new version
	because they link to the latest via ``agent_prompt``.

	Args:
		prompt_name: Name (ID) of the current Agent Prompt to version.
		prompt_body: The updated prompt text for the new version.
		title:       Optional new title (inherits from previous if omitted).
		description: Optional new description.

	Returns:
		dict: ``{"name": "<new_prompt_name>", "version": <int>}``
	"""
	current = frappe.get_doc("Agent Prompt", prompt_name)

	if current.is_system:
		frappe.throw(_("System prompts cannot be versioned by users."))

	new_version = cint(current.version) + 1

	# Mark current as no longer latest
	frappe.db.set_value("Agent Prompt", prompt_name, "is_latest", 0, update_modified=False)

	new_prompt = frappe.get_doc({
		"doctype": "Agent Prompt",
		"title": title or current.title,
		"category": current.category,
		"description": description or current.description,
		"prompt_body": prompt_body,
		"visibility": current.visibility,
		"is_active": current.is_active,
		"is_system": 0,
		"tags": current.tags,
		"version": new_version,
		"is_latest": 1,
		"previous_version": prompt_name,
		"forked_from": current.forked_from,
		"prompt_group": current.prompt_group or prompt_name,
	})
	new_prompt.insert(ignore_permissions=True)

	# Update agents that point to the old version and are NOT locked
	_update_agent_links(prompt_name, new_prompt.name, new_version)

	frappe.db.commit()

	return {"name": new_prompt.name, "version": new_version}


def _update_agent_links(old_prompt_name, new_prompt_name, new_version):
	"""Point unlocked agents from old prompt to new version."""
	agents = frappe.get_all(
		"Agent",
		filters={
			"prompt_mode": "Template",
			"agent_prompt": old_prompt_name,
			"prompt_version_locked": 0,
		},
		pluck="name",
	)
	for agent_name in agents:
		frappe.db.set_value(
			"Agent", agent_name,
			{
				"agent_prompt": new_prompt_name,
				"template_version_at_attach": new_version,
			},
			update_modified=False,
		)


@frappe.whitelist()
def fork_prompt(prompt_name, title=None):
	"""Fork (copy) a prompt template into a new independent lineage.

	Creates a version-1 prompt with ``forked_from`` pointing to the
	source.  The fork has its own ``prompt_group`` so subsequent
	versions are tracked independently.

	Args:
		prompt_name: Name of the prompt to fork.
		title:       Optional title for the fork (defaults to
		             ``"<original title> (Fork)"``).

	Returns:
		dict: ``{"name": "<new_prompt_name>", "version": 1}``
	"""
	source = frappe.get_doc("Agent Prompt", prompt_name)

	forked = frappe.get_doc({
		"doctype": "Agent Prompt",
		"title": title or f"{source.title} (Fork)",
		"category": source.category,
		"description": source.description,
		"prompt_body": source.prompt_body,
		"visibility": "Private",
		"is_active": 1,
		"is_system": 0,
		"tags": source.tags,
		"version": 1,
		"is_latest": 1,
		"previous_version": None,
		"forked_from": prompt_name,
	})
	forked.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"name": forked.name, "version": 1}


@frappe.whitelist()
def detach_from_template(agent_name):
	"""Detach an agent from its linked prompt template.

	Copies the current resolved prompt body into the agent's
	``instructions`` field, switches to Local mode, and records
	``copied_from_prompt`` for traceability.

	Args:
		agent_name: Name of the Agent to detach.

	Returns:
		dict: ``{"success": True, "prompt_mode": "Local"}``
	"""
	agent = frappe.get_doc("Agent", agent_name)

	if (agent.prompt_mode or "Local") != "Template":
		frappe.throw(_("Agent is already in Local mode."))

	if not agent.agent_prompt:
		frappe.throw(_("No template is attached to detach from."))

	# Resolve the current prompt body
	from ivendnext_ai_agents.ai.prompt_resolver import resolve_prompt
	prompt_text = resolve_prompt(agent)

	agent.instructions = prompt_text or ""
	agent.copied_from_prompt = agent.agent_prompt
	agent.agent_prompt = None
	agent.prompt_mode = "Local"
	agent.prompt_version_locked = 0
	agent.template_version_at_attach = 0
	agent.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "prompt_mode": "Local"}


@frappe.whitelist()
def save_as_template(agent_name, title, category=None, visibility="Private", description=None):
	"""Save an agent's local prompt as a new Agent Prompt template.

	Creates a new Agent Prompt from the agent's current ``instructions``
	and optionally switches the agent to Template mode.

	Args:
		agent_name:  Name of the Agent.
		title:       Title for the new template.
		category:    Optional category link.
		visibility:  Public / App / Private (default Private).
		description: Optional description.

	Returns:
		dict: ``{"name": "<prompt_name>", "version": 1}``
	"""
	agent = frappe.get_doc("Agent", agent_name)

	if not agent.instructions:
		frappe.throw(_("Agent has no instructions to save as a template."))

	prompt = frappe.get_doc({
		"doctype": "Agent Prompt",
		"title": title,
		"category": category,
		"description": description or agent.description,
		"prompt_body": agent.instructions,
		"visibility": visibility,
		"is_active": 1,
		"is_system": 0,
		"version": 1,
		"is_latest": 1,
	})
	prompt.insert(ignore_permissions=True)
	frappe.db.commit()

	return {"name": prompt.name, "version": 1}


@frappe.whitelist()
def attach_template(agent_name, prompt_name, lock_version=0):
	"""Attach an Agent Prompt template to an agent.

	Switches the agent to Template mode and links the specified prompt.
	Optionally locks to the current version.

	Args:
		agent_name:   Name of the Agent.
		prompt_name:  Name of the Agent Prompt to attach.
		lock_version: Whether to lock to the current version (0 or 1).

	Returns:
		dict: ``{"success": True, "prompt_mode": "Template", "version": <int>}``
	"""
	agent = frappe.get_doc("Agent", agent_name)
	prompt = frappe.get_doc("Agent Prompt", prompt_name)

	if not prompt.is_active:
		frappe.throw(_("Cannot attach an inactive prompt template."))

	agent.prompt_mode = "Template"
	agent.agent_prompt = prompt_name
	agent.prompt_version_locked = cint(lock_version)
	agent.template_version_at_attach = prompt.version
	agent.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "prompt_mode": "Template", "version": prompt.version}


@frappe.whitelist()
def get_version_history(prompt_name):
	"""Return the full version history for a prompt lineage.

	Walks backward through ``previous_version`` links to build the
	version chain, or queries by ``prompt_group`` for efficiency.

	Args:
		prompt_name: Name of any prompt in the lineage.

	Returns:
		list[dict]: Ordered list of versions (newest first) with
		            ``name``, ``version``, ``title``, ``is_latest``,
		            ``modified``, and ``owner``.
	"""
	prompt_group = frappe.db.get_value("Agent Prompt", prompt_name, "prompt_group")

	if not prompt_group:
		# Single prompt, no lineage
		doc = frappe.get_doc("Agent Prompt", prompt_name)
		return [{
			"name": doc.name,
			"version": doc.version,
			"title": doc.title,
			"is_latest": doc.is_latest,
			"modified": str(doc.modified),
			"owner": doc.owner,
		}]

	versions = frappe.get_all(
		"Agent Prompt",
		filters={"prompt_group": prompt_group},
		fields=["name", "version", "title", "is_latest", "modified", "owner"],
		order_by="version desc",
	)

	return versions