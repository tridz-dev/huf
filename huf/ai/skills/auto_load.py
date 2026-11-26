"""Auto-load rule for skills attached to an agent.

A skill attachment (Agent Skill row) is injected into the system prompt up
front when it is Mandatory, or when it is Optional and both the Skill's
``auto_load`` flag and the attachment row's ``auto_load`` flag are on. A
missing value counts as on. Optional skills that are not injected stay
listed by name and description and can be loaded on demand.
"""

from __future__ import annotations


def _flag_on(value) -> bool:
	"""Treat an unset flag as on; otherwise use its truthiness."""
	if value is None:
		return True
	return bool(int(value)) if isinstance(value, str | int | float) else bool(value)


def is_injected_up_front(skill, row) -> bool:
	"""Return True when the skill's instructions and prompts are injected up front."""
	if (getattr(row, "mode", None) or "Mandatory") == "Mandatory":
		return True
	return _flag_on(getattr(skill, "auto_load", None)) and _flag_on(getattr(row, "auto_load", None))


def format_skill_content(skill, prompt_bodies: list[str]) -> str:
	"""Render a skill's instructions and prompt bodies for the load_skill tool."""
	parts = []
	instructions = (getattr(skill, "instructions", None) or "").strip()
	if instructions:
		parts.append(instructions)
	parts.extend(body for body in prompt_bodies if body)
	if not parts:
		return f"Skill '{skill.skill_name}' has no instructions."
	return f"Skill '{skill.skill_name}' loaded:\n\n" + "\n\n".join(parts)
