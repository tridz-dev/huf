# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt
"""
skill_loader.py
---------------
Core logic for loading and injecting Skills into agent execution.

Skills are the "missing middle layer" between tools (actions) and prompts
(one-off instructions). They provide reusable workflow knowledge that agents
can load on demand.

Progressive loading model (mirrors Claude/OpenCode ecosystem):
  Level 1 - Metadata  : Always in system prompt (~50 tokens per skill)
  Level 2 - Content   : Injected for Mandatory skills / loaded on demand for Optional
"""

import frappe
from agents import FunctionTool


def get_agent_skills(agent_doc):
	"""
	Return ordered list of skill rows linked to this agent.
	Each row has: skill (name), mode, priority, description (fetched).
	Only returns skills whose Skill document is active.
	"""
	if not hasattr(agent_doc, "agent_skill") or not agent_doc.agent_skill:
		return []

	rows = sorted(agent_doc.agent_skill, key=lambda r: -(r.priority or 0))

	active_skills = []
	for row in rows:
		try:
			skill_doc = frappe.get_doc("Skill", row.skill)
			if not skill_doc.is_active:
				continue
			active_skills.append(
				{
					"skill_name": skill_doc.skill_name,
					"display_name": skill_doc.display_name,
					"description": skill_doc.description or "",
					"content": skill_doc.content or "",
					"mode": row.mode or "Optional",
					"priority": row.priority or 0,
				}
			)
		except frappe.DoesNotExistError:
			frappe.log_error(
				f"Skill '{row.skill}' linked to agent '{agent_doc.name}' does not exist.",
				"Skill Loader Warning",
			)
			continue

	return active_skills


def build_skill_instructions(agent_doc):
	"""
	Build a skills block to append to the agent's system prompt.

	- Mandatory skills: full content injected immediately.
	- Optional skills: only name + description (agent uses load_skill tool to read more).

	Returns an empty string if no skills are attached.
	"""
	skills = get_agent_skills(agent_doc)
	if not skills:
		return ""

	mandatory = [s for s in skills if s["mode"] == "Mandatory"]
	optional = [s for s in skills if s["mode"] == "Optional"]

	parts = []

	# --- Mandatory skills ---
	if mandatory:
		parts.append("\n\n## Skills (Active)")
		parts.append(
			"The following skills contain domain-specific workflows and best practices. "
			"Apply them whenever relevant to the user's request.\n"
		)
		for skill in mandatory:
			parts.append(f"### {skill['display_name']}")
			if skill["description"]:
				parts.append(f"_{skill['description']}_\n")
			if skill["content"]:
				parts.append(skill["content"])
			parts.append("")

	# --- Optional skills (discovery metadata only) ---
	if optional:
		parts.append("\n\n## Available Skills (load on demand)")
		parts.append(
			"The following skills are available but not yet loaded. "
			"Use the `load_skill` tool to read a skill's full instructions when the user's "
			"request matches its description.\n"
		)
		for skill in optional:
			parts.append(f"- **{skill['display_name']}** (`{skill['skill_name']}`): {skill['description']}")
		parts.append(
			"\nCall `load_skill(skill_name=<name>)` to retrieve the full workflow instructions for a skill."
		)

	return "\n".join(parts)


def create_load_skill_tool(agent_doc):
	"""
	Create a FunctionTool that lets the agent load full skill content on demand.
	Only created when the agent has at least one Optional skill.

	Returns None if there are no optional skills.
	"""
	skills = get_agent_skills(agent_doc)
	optional_skills = [s for s in skills if s["mode"] == "Optional"]

	if not optional_skills:
		return None

	# Build lookup by skill_name for fast access inside the tool handler
	skill_map = {s["skill_name"]: s for s in optional_skills}
	available_names = list(skill_map.keys())

	async def _on_invoke(ctx, args_json):
		import json

		try:
			args = json.loads(args_json) if isinstance(args_json, str) else args_json
		except Exception:
			return json.dumps({"error": "Invalid arguments. Expected JSON with 'skill_name'."})

		skill_name = args.get("skill_name", "").strip()
		if not skill_name:
			return json.dumps({"error": "skill_name is required."})

		if skill_name not in skill_map:
			return json.dumps(
				{
					"error": f"Skill '{skill_name}' is not available for this agent.",
					"available_skills": available_names,
				}
			)

		skill = skill_map[skill_name]
		if not skill["content"]:
			return json.dumps(
				{
					"skill_name": skill_name,
					"display_name": skill["display_name"],
					"description": skill["description"],
					"content": "(No content defined for this skill)",
				}
			)

		return json.dumps(
			{
				"skill_name": skill_name,
				"display_name": skill["display_name"],
				"description": skill["description"],
				"content": skill["content"],
			}
		)

	params_schema = {
		"type": "object",
		"properties": {
			"skill_name": {
				"type": "string",
				"description": (
					f"The skill to load. Available: {', '.join(available_names)}. "
					"Use the exact skill_name (slug format)."
				),
			}
		},
		"required": ["skill_name"],
		"additionalProperties": False,
	}

	return FunctionTool(
		name="load_skill",
		description=(
			"Load the full instructions for an available skill. "
			"Call this when the user's request matches a skill's description. "
			f"Available skills: {', '.join(available_names)}."
		),
		params_json_schema=params_schema,
		on_invoke_tool=_on_invoke,
	)
