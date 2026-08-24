# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Self-seeded "HUF Design System Reference" Skill.

Per A.7/D.3: huf never self-seeds its own reference content today - the
app_seeding pipeline only ingests other installed apps' content *into* huf.
This module follows the exact same idempotent-upsert pattern already proven
for the Hub Orchestrator Agent itself (huf.ai.app_seeding.hub_orchestrator):
no versioned JSON file, a plain idempotent create-or-update function, called
from huf.install after_install/after_migrate, using the same
`_seeding_flag()`-style insert-or-update and idempotent child-table append.

The Skill's `instructions` field is deliberately short (2-3 paragraphs, not
the full component list) - the full allowlist with props/examples is served
token-cheaply on demand by the `list_app_components` tool instead, matching
the token-efficiency rationale documented for #640/#641 (A.6/D.3).

Entry point: create_design_system_skill(), called from huf.install
after_install and after_migrate right after create_hub_orchestrator_agent().
"""

from contextlib import contextmanager

import frappe

logger = frappe.logger("huf")

SKILL_NAME = "HUF Design System Reference"

SKILL_INSTRUCTIONS = """When you need to show the user structured UI (a card, a table, a stat, a \
progress bar, tabs, a badge, an alert) instead of plain text, use the \
`list_app_components` and `render_app_component` tools rather than hand-writing \
JSX or guessing at shadcn/ui component names and props. The frontend only \
renders JSX for components it explicitly whitelists, so a hand-authored \
component name or prop that isn't on that list simply won't render.

Call `list_app_components()` first to see the small set of components you're \
allowed to use, each with its accepted props and a short example. Then call \
`render_app_component(component, props, confirm=False)` to preview the exact \
`<artifact>` markup that will be produced, and call it again with \
`confirm=True` once you're ready to relay that markup verbatim in your reply.

This mirrors the existing `render_mermaid`/`render_chart` tools: you pass \
small structured data, the backend deterministically templates the markup, \
and you never free-form JSX or Mermaid syntax by hand.
"""

SKILL_DESCRIPTION = (
	"Reference for the design-system-aware component rendering tools "
	"(list_app_components / render_app_component)."
)


def get_skill_manifest() -> dict:
	"""Manifest for the `huf_skills` hook (see huf/hooks.py).

	huf.ai.skills.hooks.sync_app_skills scans every installed app's `huf_skills`
	hook on every migrate and deletes any "App Provided" Skill not found in that
	scan (orphan cleanup) -- including skills provided by huf itself, since it
	scans huf like any other installed app. Without this manifest declaring the
	skill, sync_app_skills would try to delete it on every single migrate (it
	correctly fails, since the skill is attached to Hub Orchestrator, but the
	failure-logging path has an unrelated framework bug that turns that into a
	hard migrate failure). This function is the fix: it makes sync_app_skills
	see the skill as still declared, so it upserts instead of deleting it.
	create_design_system_skill() below still does its own idempotent
	insert/update immediately at install/migrate time (before sync_app_skills
	runs, per hooks.py's after_migrate ordering) so the skill and its
	Hub Orchestrator attachment exist without waiting on a second sync pass.
	"""
	return {
		"name": SKILL_NAME,
		"title": SKILL_NAME,
		"description": SKILL_DESCRIPTION,
		"instructions": SKILL_INSTRUCTIONS,
		"tools": ["list_app_components", "render_app_component"],
	}


@contextmanager
def _seeding_flag():
	"""Set frappe.flags.in_seeding so any is_system-style guards pass, then restore."""
	previous = getattr(frappe.flags, "in_seeding", False)
	frappe.flags.in_seeding = True
	try:
		yield
	finally:
		frappe.flags.in_seeding = previous


def _attach_skill_tools(skill) -> bool:
	"""Attach the two design-system render tools to the Skill doc, idempotently."""
	existing = {row.tool for row in skill.get("skill_tools") or []}
	added = False
	for tool_name in ("list_app_components", "render_app_component"):
		if tool_name not in existing and frappe.db.exists("Agent Tool Function", tool_name):
			skill.append("skill_tools", {"tool": tool_name})
			added = True
	return added


def _attach_skill_to_hub_orchestrator() -> bool:
	"""Attach the Skill to Hub Orchestrator's agent_skill child table, mode=Mandatory.

	Idempotent append, mirroring hub_orchestrator.py's _attach_builder_tools().
	"""
	if not frappe.db.exists("Agent", "Hub Orchestrator"):
		return False

	agent = frappe.get_doc("Agent", "Hub Orchestrator")
	existing = {row.skill for row in agent.get("agent_skill") or []}
	if SKILL_NAME in existing:
		return False

	agent.append("agent_skill", {"skill": SKILL_NAME, "mode": "Mandatory"})
	with _seeding_flag():
		agent.save(ignore_permissions=True)
	logger.info(f"Attached '{SKILL_NAME}' skill to Hub Orchestrator.")
	return True


def create_design_system_skill() -> bool:
	"""
	Idempotently create (or update) the "HUF Design System Reference" Skill
	and attach it to Hub Orchestrator's agent_skill child table.

	Returns True if the Skill document was newly created.
	"""
	created = False

	if frappe.db.exists("Skill", SKILL_NAME):
		skill = frappe.get_doc("Skill", SKILL_NAME)
		skill.title = SKILL_NAME
		skill.description = SKILL_DESCRIPTION
		skill.instructions = SKILL_INSTRUCTIONS
		skill.source_type = "App Provided"
		skill.provider_app = "huf"
		skill.auto_load = 1
		skill.status = "Active"
		_attach_skill_tools(skill)
		with _seeding_flag():
			skill.save(ignore_permissions=True)
	else:
		skill = frappe.get_doc(
			{
				"doctype": "Skill",
				"skill_name": SKILL_NAME,
				"title": SKILL_NAME,
				"description": SKILL_DESCRIPTION,
				"instructions": SKILL_INSTRUCTIONS,
				"source_type": "App Provided",
				"provider_app": "huf",
				"auto_load": 1,
				"status": "Active",
			}
		)
		_attach_skill_tools(skill)
		with _seeding_flag():
			skill.insert(ignore_permissions=True)
		created = True
		logger.info(f"'{SKILL_NAME}' skill seeded.")

	_attach_skill_to_hub_orchestrator()
	return created
