# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""Whitelisted save endpoint used by the prompt forms."""

import frappe
from frappe import _
from frappe.utils import cint

from huf.ai.prompts.versioning import save_prompt_changes
from huf.permissions import has_capability


def _require(capability: str) -> None:
	if not has_capability(frappe.session.user, capability):
		frappe.throw(_("You don't have permission to perform this action."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def save_prompt(prompt_name, values, summary=0):
	"""Save a prompt from the form.

	A changed ``prompt_body`` creates the next version and moves unlocked
	agents (and skills) to it; metadata-only changes update the row in place.

	Args:
		prompt_name: Name of the latest Agent Prompt (or Agent Summary Prompt).
		values:      Dict (or JSON string) of fields to save.
		summary:     Truthy to target Agent Summary Prompt.

	Returns:
		dict: ``{"name", "version", "versioned", "changed"}``

	Requires: agent.create
	"""
	_require("agent.create")
	doctype = "Agent Summary Prompt" if cint(summary) else "Agent Prompt"
	return save_prompt_changes(doctype, prompt_name, frappe.parse_json(values) or {})
