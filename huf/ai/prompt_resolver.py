# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Centralised prompt resolution for Agents.

Every backend path that needs the agent's effective prompt MUST call
``resolve_prompt(agent_doc)`` instead of reading ``agent_doc.instructions``
directly.  This keeps the Template / Local / version-lock logic in one
place and guarantees consistent behaviour across sync runs, streaming,
triggers, and orchestration.
"""

import frappe
from frappe import _


DEFAULT_SUMMARY_PROMPT = """You are maintaining a rolling summary of a conversation.

1. Update the 'Existing Summary' by incorporating the 'New Messages'.
2. Keep the summary concise but retain key details (names, decisions, technical context).
3. Output ONLY the new summary text.

Data:
{summary_data}"""


def resolve_prompt(agent_doc):
	"""Return the effective prompt text for an agent.

	Args:
		agent_doc: A loaded Agent document (``frappe.get_doc("Agent", …)``).

	Returns:
		str: The resolved prompt body, or ``None`` if the agent has no
		     prompt configured.

	Resolution rules
	-----------------
	* **Local mode** (default, backward-compatible): returns
	  ``agent_doc.instructions`` directly.
	* **Template mode**:
	  - If ``prompt_version_locked`` is set, load the exact version that
	    was recorded in ``template_version_at_attach``.
	  - Otherwise load the latest version of the linked Agent Prompt.
	"""
	mode = getattr(agent_doc, "prompt_mode", None) or "Local"

	if mode == "Template":
		return _resolve_template_prompt(agent_doc)

	# Local mode — straightforward
	return agent_doc.instructions or None


def resolve_summary_prompt(agent_doc):
	"""Return the effective summary prompt text for an agent.

	Follows the same Template / Local / version-lock semantics as
	``resolve_prompt``.  When no custom summary prompt is configured,
	returns the system default template.

	Args:
		agent_doc: A loaded Agent document.

	Returns:
		str: The resolved summary prompt body.
	"""
	mode = getattr(agent_doc, "summary_prompt_mode", None) or "Local"

	if mode == "Template":
		return _resolve_summary_template_prompt(agent_doc)

	# Local mode — use the agent's local summary prompt if provided,
	# otherwise fall back to the system default.
	return agent_doc.summary_prompt or DEFAULT_SUMMARY_PROMPT


def _resolve_template_prompt(agent_doc):
	"""Resolve prompt from the linked Agent Prompt template."""
	prompt_name = agent_doc.agent_prompt
	if not prompt_name:
		return agent_doc.instructions or None

	if agent_doc.prompt_version_locked and agent_doc.template_version_at_attach:
		return _get_locked_version_body(prompt_name, agent_doc.template_version_at_attach)

	# Not locked — use the linked prompt directly (which should be is_latest)
	prompt_body = frappe.db.get_value("Agent Prompt", prompt_name, "prompt_body")
	return prompt_body or agent_doc.instructions or None


def _resolve_summary_template_prompt(agent_doc):
	"""Resolve summary prompt from the linked Agent Summary Prompt template."""
	prompt_name = agent_doc.summary_prompt_template
	if not prompt_name:
		return agent_doc.summary_prompt or DEFAULT_SUMMARY_PROMPT

	if (
		getattr(agent_doc, "summary_prompt_version_locked", 0)
		and getattr(agent_doc, "summary_template_version_at_attach", None)
	):
		body = _get_locked_version_body(
			prompt_name,
			agent_doc.summary_template_version_at_attach,
			doctype="Agent Summary Prompt",
		)
		return body or agent_doc.summary_prompt or DEFAULT_SUMMARY_PROMPT

	prompt_body = frappe.db.get_value("Agent Summary Prompt", prompt_name, "prompt_body")
	return prompt_body or agent_doc.summary_prompt or DEFAULT_SUMMARY_PROMPT


def _get_locked_version_body(prompt_name, target_version, doctype="Agent Prompt"):
	"""Walk the version lineage to find the exact version body.

	The ``prompt_name`` on the Agent may point to the latest version.
	If the agent is locked to an earlier version we need to find the
	row whose ``version`` matches ``target_version`` within the same
	prompt group.
	"""
	# First check if the linked prompt itself is the right version
	prompt_doc_data = frappe.db.get_value(
		doctype, prompt_name, ["prompt_body", "version", "prompt_group"], as_dict=True
	)
	if not prompt_doc_data:
		return None

	if prompt_doc_data.version == target_version:
		return prompt_doc_data.prompt_body

	# Look up the correct version within the same prompt group
	if prompt_doc_data.prompt_group:
		match = frappe.db.get_value(
			doctype,
			{"prompt_group": prompt_doc_data.prompt_group, "version": target_version},
			"prompt_body",
		)
		if match:
			return match

	# Fallback: return the linked prompt body
	return prompt_doc_data.prompt_body
