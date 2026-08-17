# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Single source of truth for the opt-in-but-vetoable chat capabilities:
ask_user, rich_elements, and document_artifacts.

Each capability is granted per-Agent (``allow_<name>``, default on — matches
pre-existing behavior) and can be force-disabled per-AI-Model
(``disable_<name>``, default off) so a local/small/API-only model can be
configured once to conserve prompt context, regardless of what any agent
using it requests. Both the tool-availability gate
(``huf.ai.tool_registry.PermissionAwareToolRegistry``) and the system-prompt
instruction-injection gate (``huf.ai.agent_integration.AgentManager``) call
this helper so they can never drift out of sync with each other.
"""

import frappe

_AGENT_ALLOW_FIELD = {
	"ask_user": "allow_ask_user",
	"rich_elements": "allow_rich_elements",
	"document_artifacts": "allow_document_artifacts",
}

_AI_MODEL_DISABLE_FIELD = {
	"ask_user": "disable_ask_user",
	"rich_elements": "disable_rich_elements",
	"document_artifacts": "disable_document_artifacts",
}


def capability_enabled(agent_doc, model_name, name: str) -> bool:
	"""True when capability `name` is usable for this agent + model.

	Args:
		agent_doc: The Agent document (or anything with the allow_* attrs).
		model_name: The effective "AI Model" link name in use for this run
			(falls back to agent_doc.model if not given). May be falsy if
			unresolved yet, in which case only the agent's own flag applies.
		name: One of "ask_user", "rich_elements", "document_artifacts".
	"""
	allow_field = _AGENT_ALLOW_FIELD.get(name)
	if allow_field is None:
		raise ValueError(f"Unknown chat capability: {name!r}")

	if not getattr(agent_doc, allow_field, True):
		return False

	model_name = model_name or getattr(agent_doc, "model", None)
	if not model_name:
		return True

	disable_field = _AI_MODEL_DISABLE_FIELD[name]
	forced_off = frappe.db.get_value("AI Model", model_name, disable_field)
	return not bool(forced_off)
