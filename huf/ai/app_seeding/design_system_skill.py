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

source_type is deliberately "Local", not "App Provided": huf.ai.skills.hooks
.sync_app_skills's orphan-cleanup pass deletes any "App Provided" Skill it
doesn't find declared via a `huf_skills` hook on THIS pass -- and its
per-app scan-caching (keyed on hooks.py's mtime) means an app can be
legitimately skipped on a given migrate even though its declaration hasn't
changed, which the cleanup pass then misreads as "no longer declared" and
deletes anyway (a real, pre-existing bug in that caching/cleanup
interaction, out of scope to fix here). A first attempt at fixing this by
declaring the skill via a `huf_skills` hook entry still hit the same
caching bug on a later migrate. "Local" sidesteps the entire orphan-cleanup
subsystem: it isn't scanned, isn't a hook-discovered skill, and is
semantically accurate -- create_design_system_skill() *is* a local,
directly-authored skill (the same relationship Hub Orchestrator itself has
to app_seeding.hub_orchestrator: self-seeded, not externally discovered).

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
		skill.source_type = "Local"
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
				"source_type": "Local",
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
