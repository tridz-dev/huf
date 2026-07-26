"""
Hub builder tools — typed, capability-gated tools for the hub chat.

These handlers let privileged users (System Manager / Huf Manager) create
huf data tables, draft agents, edit agent prompts, attach tools, and publish
agents from an agent conversation. Every mutating tool enforces the builder
capability up front, and the creation/edit/publish tools follow a two-phase
contract: call with ``confirm=False`` to preview a diff, then again with
``confirm=True`` to apply. Nothing mutates without ``confirm=True``.

Secrets are never read out: provider key checks use ``get_password`` for
presence only.
"""

import json

import frappe
from frappe import _

from huf.ai.sdk_tools import _sanitize_for_doctype

BUILDER_ROLES = ("System Manager", "Huf Manager")

# Fields that would let a chat session wire arbitrary code or HTTP endpoints
# into a tool. Builder-created tools stay declarative; an admin completes
# these in the desk UI.
_FORBIDDEN_TOOL_FIELDS = ("function_path", "base_url", "http_headers")


def _require_builder_capability():
	"""Throw unless the session user is a System Manager or Huf Manager."""
	if not set(frappe.get_roles()) & set(BUILDER_ROLES):
		frappe.throw(
			_("Only System Managers or Huf Managers can use builder tools."),
			frappe.PermissionError,
		)


def _provider_has_key(provider: str) -> bool:
	"""Presence check only — the key value never leaves get_password."""
	if not provider or not frappe.db.exists("AI Provider", provider):
		return False
	try:
		return bool(frappe.get_doc("AI Provider", provider).get_password("api_key"))
	except frappe.ValidationError:
		# Frappe raises "Password not found" when no password row exists at all.
		return False


def _get_agent(agent_name: str):
	if not frappe.db.exists("Agent", agent_name):
		frappe.throw(_("Agent '{0}' does not exist.").format(agent_name))
	return frappe.get_doc("Agent", agent_name)


def _check_system_agent_editable(agent):
	"""Mirror the backend lock: system agents are System-Manager-only."""
	if agent.is_system and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Agent '{0}' is a system agent. Only System Managers can modify it.").format(
				agent.agent_name
			),
			frappe.PermissionError,
		)


def _require_doc_permission(doctype: str, permission: str, name: str | None = None):
	"""Enforce Frappe document-level permission in addition to role checks."""
	if not frappe.has_permission(doctype, permission, doc=name):
		frappe.throw(
			_("You don't have permission to {0} {1} records.").format(
				permission, doctype
			),
			frappe.PermissionError,
		)


def _parse_list(value, fieldname: str) -> list:
	"""Accept a list or a JSON-encoded list (LLMs often stringify arguments)."""
	if value is None:
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			frappe.throw(_("'{0}' must be a list or a JSON-encoded list.").format(fieldname))
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("'{0}' must be a list or a JSON-encoded list.").format(fieldname))
	return list(value)


def create_huf_table(
	table_name: str,
	fields,
	description: str = "",
	icon: str = "",
	autoname_method: str = "Autoincrement",
	title_field: str = "",
	confirm: bool = False,
) -> dict:
	"""Create a huf data table (custom DocType + registry entry).

	Wraps the HUF Data Table API — field definitions are validated by the
	existing validators. Returns the new DocType name and its live schema.
	"""
	_require_builder_capability()
	_require_doc_permission("Huf Data Table", "create")

	from huf.huf.doctype.huf_data_table.api import create_data_table, get_table_schema
	from huf.huf.doctype.huf_data_table.validators import (
		get_search_fields,
		resolve_autoname,
		validate_and_prepare_fields,
	)

	if isinstance(fields, str):
		fields = json.loads(fields)

	table_name = table_name.strip()
	if not table_name:
		frappe.throw(_("Table name is required"))

	doctype_name = f"HF {table_name}"

	if frappe.db.exists("DocType", doctype_name):
		frappe.throw(f"Table '{table_name}' already exists")

	if frappe.db.exists("Huf Data Table", {"table_name": table_name}):
		frappe.throw(f"Table '{table_name}' already exists")

	validated_fields = validate_and_prepare_fields(fields)
	autoname = resolve_autoname(autoname_method, title_field)
	search_fields = get_search_fields(validated_fields)

	diff = {
		"table_name": table_name,
		"doctype_name": doctype_name,
		"description": description,
		"icon": icon,
		"autoname_method": autoname_method,
		"autoname": autoname,
		"title_field": title_field,
		"search_fields": search_fields,
		"fields": validated_fields,
	}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to create the table.",
		}

	result = create_data_table(
		table_name=table_name,
		fields=fields,
		description=description,
		icon=icon,
		autoname_method=autoname_method,
		title_field=title_field,
	)
	data = result.get("data", {})
	schema = get_table_schema(data["name"])

	return {
		"created": True,
		"doctype": data.get("doctype_name"),
		"schema": schema,
		"diff": diff,
	}


def draft_agent(
	agent_name: str,
	provider: str,
	model: str,
	instructions: str,
	description: str = "",
	confirm: bool = False,
) -> dict:
	"""Create a disabled (draft) Agent with a local prompt.

	The agent is created with disabled=1 so it cannot run until published
	via publish_agent. If the provider has no API key configured the draft
	is still created, but the result carries a warning flag.
	"""
	_require_builder_capability()

	if frappe.db.exists("Agent", agent_name):
		frappe.throw(_("Agent '{0}' already exists.").format(agent_name))
	if not frappe.db.exists("AI Provider", provider):
		frappe.throw(
			_("AI Provider '{0}' does not exist. Create and configure it first.").format(provider)
		)
	_require_doc_permission("AI Provider", "read", provider)
	if not frappe.db.exists("AI Model", model):
		frappe.throw(_("AI Model '{0}' does not exist.").format(model))
	_require_doc_permission("AI Model", "read", model)

	_require_doc_permission("Agent", "create")

	payload = _sanitize_for_doctype(
		"Agent",
		{
			"agent_name": agent_name,
			"provider": provider,
			"model": model,
			"instructions": instructions,
			"description": description,
			"prompt_mode": "Local",
			"disabled": 1,
		},
	)

	diff = {"payload": payload}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to create the draft agent.",
		}

	agent = frappe.get_doc({"doctype": "Agent", **payload})
	agent.insert()

	result = {"created": True, "agent": agent.name, "disabled": True, "diff": diff}
	if not _provider_has_key(provider):
		result["warning"] = (
			f"Provider '{provider}' has no API key configured. "
			"The agent will stay unpublished until a key is set in AI Provider settings."
		)
	return result


def update_agent_prompt(
	agent_name: str,
	instructions: str | None = None,
	agent_prompt: str | None = None,
	confirm: bool = False,
) -> dict:
	"""Two-phase update of an agent's prompt.

	confirm=False: returns a diff of proposed changes without saving.
	confirm=True: applies and saves. Setting agent_prompt switches the
	agent to Template prompt mode.
	"""
	_require_builder_capability()
	agent = _get_agent(agent_name)
	_check_system_agent_editable(agent)
	_require_doc_permission("Agent", "write", agent.name)

	proposed = {}
	if instructions is not None and instructions != (agent.instructions or ""):
		proposed["instructions"] = instructions
	if agent_prompt is not None:
		if not frappe.db.exists("Agent Prompt", agent_prompt):
			frappe.throw(_("Agent Prompt '{0}' does not exist.").format(agent_prompt))
		if agent_prompt != (agent.agent_prompt or ""):
			proposed["agent_prompt"] = agent_prompt
			if agent.prompt_mode != "Template":
				proposed["prompt_mode"] = "Template"

	diff = {
		field: {"old": agent.get(field) or "", "new": value}
		for field, value in proposed.items()
	}

	if not confirm:
		return {
			"updated": False,
			"confirm_required": True,
			"agent": agent.name,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to apply.",
		}

	for field, value in proposed.items():
		agent.set(field, value)
	if proposed:
		agent.save()

	return {"updated": bool(proposed), "agent": agent.name, "diff": diff}


def attach_agent_tools(agent_name: str, tool_names, confirm: bool = False) -> dict:
	"""Two-phase replacement of an agent's tool list.

	tool_names is the full proposed set of Agent Tool Function names (not an
	additive delta). confirm=False returns the current vs proposed rows;
	confirm=True applies and saves.
	"""
	_require_builder_capability()
	agent = _get_agent(agent_name)
	_check_system_agent_editable(agent)
	_require_doc_permission("Agent", "write", agent.name)

	tool_names = _parse_list(tool_names, "tool_names")
	for tool_name in tool_names:
		if not frappe.db.exists("Agent Tool Function", tool_name):
			frappe.throw(
				_("Agent Tool Function '{0}' does not exist. Create it first.").format(tool_name)
			)

	current = [row.tool for row in agent.get("agent_tool") or []]
	diff = {
		"agent_tool": {
			"old": current,
			"new": tool_names,
		}
	}

	if not confirm:
		return {
			"updated": False,
			"confirm_required": True,
			"agent": agent.name,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to apply.",
		}

	agent.set("agent_tool", [{"tool": tool_name} for tool_name in tool_names])
	agent.save()

	return {"updated": True, "agent": agent.name, "diff": diff}


def publish_agent(agent_name: str, confirm: bool = False) -> dict:
	"""Two-phase publish: flip an agent from disabled draft to enabled.

	Refuses to publish when the agent's provider has no API key configured.
	Already-enabled agents are a no-op.
	"""
	_require_builder_capability()
	agent = _get_agent(agent_name)
	_check_system_agent_editable(agent)
	_require_doc_permission("Agent", "write", agent.name)

	if not agent.disabled:
		return {
			"published": True,
			"changed": False,
			"agent": agent.name,
			"disabled": False,
			"message": "Agent is already published.",
		}

	if not _provider_has_key(agent.provider):
		return {
			"published": False,
			"error": f"Provider '{agent.provider}' has no API key configured.",
			"remediation": (
				f"Open the AI Provider '{agent.provider}' in the desk UI, set its API key, "
				"then call publish_agent again."
			),
		}

	diff = {"disabled": {"old": 1, "new": 0}}

	if not confirm:
		return {
			"published": False,
			"confirm_required": True,
			"agent": agent.name,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to apply.",
		}

	agent.disabled = 0
	agent.save()

	return {"published": True, "changed": True, "agent": agent.name, "disabled": False}


def create_agent_tool(
	tool_name: str,
	description: str,
	tool_type: str = "Builder",
	parameters=None,
	confirm: bool = False,
	**kwargs,
) -> dict:
	"""Create a declarative Agent Tool Function record.

	The tool is created with types="Custom Function" and its parameter
	schema, but WITHOUT a function_path or HTTP endpoint — an admin must
	wire the implementation in the desk UI before the tool can run. This
	tool cannot create arbitrary code or HTTP tools.
	"""
	_require_builder_capability()
	_require_doc_permission("Agent Tool Function", "create")

	forbidden = [key for key in _FORBIDDEN_TOOL_FIELDS if kwargs.get(key)]
	if forbidden:
		frappe.throw(
			_(
				"Builder tools cannot set {0}. Create the declarative tool record and "
				"let an admin wire the implementation in the desk UI."
			).format(", ".join(forbidden))
		)

	if frappe.db.exists("Agent Tool Function", tool_name):
		frappe.throw(_("Agent Tool Function '{0}' already exists.").format(tool_name))

	tool_type_missing = not frappe.db.exists("Agent Tool Type", tool_type)

	rows = []
	for raw in _parse_list(parameters, "parameters"):
		if not isinstance(raw, dict):
			frappe.throw(_("Each parameter must be an object with fieldname/type."))
		row = _sanitize_for_doctype("Agent Function Params", raw)
		fieldname = row.get("fieldname") or raw.get("parameter_name") or raw.get("name")
		if not fieldname:
			frappe.throw(_("Each parameter needs a fieldname."))
		row.setdefault("label", fieldname.replace("_", " ").title())
		row["fieldname"] = fieldname
		row.setdefault("type", "string")
		rows.append(row)

	payload = {
		"doctype": "Agent Tool Function",
		"tool_name": tool_name,
		"description": description,
		"types": "Custom Function",
		"tool_type": tool_type,
		"parameters": rows,
	}

	diff = {
		"payload": payload,
		"tool_type_will_be_created": tool_type_missing,
	}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to create the tool.",
		}

	if tool_type_missing:
		type_doc = frappe.new_doc("Agent Tool Type")
		type_doc.name1 = tool_type
		type_doc.insert(ignore_permissions=True)

	doc = frappe.get_doc(payload)
	doc.insert()

	return {
		"created": True,
		"tool_name": doc.name,
		"requires_admin_completion": True,
		"diff": diff,
		"message": (
			"Declarative tool record created without an implementation. An admin must set "
			"the function_path in the desk UI before this tool can run — do not treat it as "
			"callable yet."
		),
	}
