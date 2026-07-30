"""
Hub builder tools — typed, capability-gated tools for the hub chat.

These handlers let privileged users (System Manager / Huf Manager) create
huf data tables, manage table rows, draft agents, edit agent prompts, attach
tools, and publish agents from an agent conversation. Every mutating tool
enforces the builder capability up front, and the creation/edit/publish
tools follow a two-phase contract: call with ``confirm=False`` to preview a
diff, then again with ``confirm=True`` to apply. Nothing mutates without
``confirm=True``.

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

# Tool types that execute declaratively against a reference_doctype via the
# handle_* functions in huf.ai.sdk_tools — no function_path or HTTP endpoint
# needed, so they work the moment they are created.
_DECLARATIVE_TYPES = (
	"Create Document",
	"Create Multiple Documents",
	"Get Document",
	"Get Multiple Documents",
	"Get List",
	"Update Document",
	"Update Multiple Documents",
	"Delete Document",
	"Delete Multiple Documents",
	"Get Value",
	"Set Value",
)


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
		return bool(frappe.get_doc("AI Provider", provider).get_password("api_key", raise_exception=False))
	except Exception:
		# Frappe raises AuthenticationError ("Password not found") when no password row exists at all.
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


def _as_bool(value) -> bool:
	"""Coerce LLM-sent booleans — "false"/"0"/"no" strings must not be truthy."""
	if isinstance(value, str):
		return value.strip().lower() in ("true", "1", "yes")
	return bool(value)


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


def _parse_dict(value, fieldname: str) -> dict:
	"""Accept a dict or a JSON-encoded object (LLMs often stringify arguments)."""
	if value is None:
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except (ValueError, TypeError):
			frappe.throw(_("'{0}' must be an object or a JSON-encoded object.").format(fieldname))
	if not isinstance(value, dict):
		frappe.throw(_("'{0}' must be an object or a JSON-encoded object.").format(fieldname))
	return dict(value)


def _get_table_registry(table_name: str):
	"""Resolve a Huf Data Table registry row by table_name or registry name."""
	registry_name = frappe.db.get_value("Huf Data Table", {"table_name": table_name}, "name")
	if not registry_name and frappe.db.exists("Huf Data Table", table_name):
		registry_name = table_name
	if not registry_name:
		frappe.throw(_("Huf data table '{0}' does not exist.").format(table_name))
	return frappe.get_doc("Huf Data Table", registry_name)


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
	confirm = _as_bool(confirm)

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

	registry_name = frappe.db.get_value("Huf Data Table", {"table_name": table_name}, "name")
	if registry_name or frappe.db.exists("DocType", doctype_name):
		if registry_name:
			registry = frappe.get_doc("Huf Data Table", registry_name)
			schema = get_table_schema(registry.name)
			return {
				"created": False,
				"already_exists": True,
				"table": registry.table_name,
				"doctype": registry.doctype_name,
				"schema": schema,
				"message": (
					f"Table '{table_name}' already exists as '{registry.doctype_name}'. "
					"Do not create it again — proceed to use it "
					"(list_table_rows / add_table_row / update_table_row / delete_table_row)."
				),
			}
		frappe.throw(
			_(
				"DocType '{0}' already exists but is not a registered huf data table. "
				"Choose a different table name."
			).format(doctype_name)
		)

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
	allow_chat: bool = True,
	confirm: bool = False,
) -> dict:
	"""Create a disabled (draft) Agent with a local prompt.

	The agent is created with disabled=1 so it cannot run until published
	via publish_agent. If the provider has no API key configured the draft
	is still created, but the result carries a warning flag.

	allow_chat defaults to True: hub-built agents are meant to be chatted
	with (e.g. managing data tables), and only chat-enabled agents appear
	in the chat UI pickers.
	"""
	_require_builder_capability()
	confirm = _as_bool(confirm)
	allow_chat = _as_bool(allow_chat)

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
			"allow_chat": 1 if allow_chat else 0,
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

	result = {"created": True, "agent": agent.name, "disabled": True, "allow_chat": allow_chat, "diff": diff}
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
	confirm = _as_bool(confirm)
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
	confirm = _as_bool(confirm)
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
	confirm = _as_bool(confirm)
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
	types: str,
	reference_doctype: str,
	tool_type: str = "Builder",
	parameters=None,
	confirm: bool = False,
	**kwargs,
) -> dict:
	"""Create a WORKING declarative document Agent Tool Function.

	The tool is bound to reference_doctype and executes immediately via the
	built-in document handlers — attach it to an agent with attach_agent_tools
	and it is callable right away. Only declarative document types are allowed
	(_DECLARATIVE_TYPES); Custom Function, code, and HTTP tools cannot be
	created by this tool.

	Parameter friction reducers: Select fields get their options auto-filled
	from the reference DocType's meta when missing, and parameters naming
	fields that don't exist on the DocType are dropped (reported in
	``dropped_params``) instead of failing the whole creation.
	"""
	_require_builder_capability()
	_require_doc_permission("Agent Tool Function", "create")
	confirm = _as_bool(confirm)

	forbidden = [key for key in _FORBIDDEN_TOOL_FIELDS if kwargs.get(key)]
	if forbidden:
		frappe.throw(
			_(
				"Builder tools cannot set {0}. Only declarative document tools can be "
				"created — code and HTTP tools are not allowed."
			).format(", ".join(forbidden))
		)

	if types not in _DECLARATIVE_TYPES:
		frappe.throw(
			_(
				"Tool type '{0}' is not supported. create_agent_tool only creates "
				"declarative document tools: {1}. Custom Function, code, and HTTP tools "
				"cannot be created by this tool."
			).format(types, ", ".join(_DECLARATIVE_TYPES))
		)

	if not reference_doctype or not frappe.db.exists("DocType", reference_doctype):
		frappe.throw(_("Reference DocType '{0}' does not exist.").format(reference_doctype))
	_require_doc_permission(reference_doctype, "read")

	if frappe.db.exists("Agent Tool Function", tool_name):
		frappe.throw(_("Agent Tool Function '{0}' already exists.").format(tool_name))

	tool_type_missing = not frappe.db.exists("Agent Tool Type", tool_type)

	ref_meta = frappe.get_meta(reference_doctype)

	rows = []
	dropped_params = []
	for raw in _parse_list(parameters, "parameters"):
		if not isinstance(raw, dict):
			frappe.throw(_("Each parameter must be an object with fieldname/type."))
		row = _sanitize_for_doctype("Agent Function Params", raw)
		fieldname = row.get("fieldname") or raw.get("parameter_name") or raw.get("name")
		if not fieldname:
			frappe.throw(_("Each parameter needs a fieldname."))

		target_meta = ref_meta
		child_table_name = row.get("child_table_name")
		if child_table_name:
			child_field = ref_meta.get_field(child_table_name)
			target_meta = frappe.get_meta(child_field.options) if child_field else None
		ref_field = target_meta.get_field(fieldname) if target_meta else None
		if not ref_field:
			dropped_params.append(fieldname)
			continue

		row.setdefault("label", fieldname.replace("_", " ").title())
		row["fieldname"] = fieldname
		row.setdefault("type", "string")
		if ref_field.fieldtype == "Select" and not row.get("options"):
			row["options"] = ref_field.options or ""
		rows.append(row)

	payload = {
		"doctype": "Agent Tool Function",
		"tool_name": tool_name,
		"description": description,
		"types": types,
		"reference_doctype": reference_doctype,
		"tool_type": tool_type,
		"parameters": rows,
	}

	diff = {
		"payload": payload,
		"tool_type_will_be_created": tool_type_missing,
		"dropped_params": dropped_params,
	}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"dropped_params": dropped_params,
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
		"dropped_params": dropped_params,
		"diff": diff,
		"message": (
			f"Tool '{doc.name}' is a working document tool bound to '{reference_doctype}'. "
			"Attach it to an agent with attach_agent_tools to make it callable."
		),
	}


def list_table_rows(
	table_name: str,
	filters=None,
	fields=None,
	limit: int = 20,
	start: int = 0,
) -> dict:
	"""Read rows from a huf data table (its generated dynamic DocType).

	Read-only. table_name may be the human table name or the Huf Data Table
	registry name. filters follows the frappe.get_list filter format.
	"""
	_require_builder_capability()
	_require_doc_permission("Huf Data Table", "read")

	registry = _get_table_registry(table_name)
	doctype_name = registry.doctype_name
	_require_doc_permission(doctype_name, "read")

	if isinstance(filters, str):
		filters = json.loads(filters)
	field_list = _parse_list(fields, "fields") or ["*"]

	rows = frappe.get_list(
		doctype_name,
		filters=filters or None,
		fields=field_list,
		limit_start=int(start),
		limit=int(limit),
		order_by="modified desc",
	)

	return {
		"table": registry.table_name,
		"doctype": doctype_name,
		"rows": rows,
		"total": frappe.db.count(doctype_name, filters=filters or None),
		"limit": int(limit),
		"start": int(start),
	}


def add_table_row(table_name: str, data, confirm: bool = False) -> dict:
	"""Two-phase insert of a row into a huf data table.

	confirm=False: returns the proposed row, validated against the dynamic
	DocType's meta (unknown fields are dropped). confirm=True: inserts.
	"""
	_require_builder_capability()
	_require_doc_permission("Huf Data Table", "write")
	confirm = _as_bool(confirm)

	registry = _get_table_registry(table_name)
	doctype_name = registry.doctype_name
	_require_doc_permission(doctype_name, "create")

	proposed = _sanitize_for_doctype(doctype_name, _parse_dict(data, "data"))

	diff = {"doctype": doctype_name, "data": proposed}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to add the row.",
		}

	doc = frappe.get_doc({"doctype": doctype_name, **proposed})
	doc.insert()

	return {"created": True, "row": doc.name, "doctype": doctype_name, "diff": diff}


def update_table_row(table_name: str, row_name: str, data, confirm: bool = False) -> dict:
	"""Two-phase update of a row in a huf data table.

	confirm=False: returns an old/new diff of the proposed changes without
	saving. confirm=True: applies and saves.
	"""
	_require_builder_capability()
	_require_doc_permission("Huf Data Table", "write")
	confirm = _as_bool(confirm)

	registry = _get_table_registry(table_name)
	doctype_name = registry.doctype_name
	if not frappe.db.exists(doctype_name, row_name):
		frappe.throw(
			_("Row '{0}' does not exist in table '{1}'.").format(row_name, registry.table_name)
		)
	_require_doc_permission(doctype_name, "write")

	doc = frappe.get_doc(doctype_name, row_name)
	proposed = _sanitize_for_doctype(doctype_name, _parse_dict(data, "data"))

	diff = {
		field: {"old": doc.get(field), "new": value}
		for field, value in proposed.items()
		if doc.get(field) != value
	}

	if not confirm:
		return {
			"updated": False,
			"confirm_required": True,
			"row": row_name,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to apply.",
		}

	for field, value in proposed.items():
		doc.set(field, value)
	if diff:
		doc.save()

	return {"updated": bool(diff), "row": doc.name, "diff": diff}


def delete_table_row(table_name: str, row_name: str, confirm: bool = False) -> dict:
	"""Two-phase delete of a row from a huf data table.

	confirm=False: previews the deletion. confirm=True: deletes the row.
	"""
	_require_builder_capability()
	_require_doc_permission("Huf Data Table", "write")
	confirm = _as_bool(confirm)

	registry = _get_table_registry(table_name)
	doctype_name = registry.doctype_name
	if not frappe.db.exists(doctype_name, row_name):
		frappe.throw(
			_("Row '{0}' does not exist in table '{1}'.").format(row_name, registry.table_name)
		)
	_require_doc_permission(doctype_name, "delete")

	diff = {"doctype": doctype_name, "row": {"old": row_name, "new": None}}

	if not confirm:
		return {
			"deleted": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to delete the row.",
		}

	frappe.delete_doc(doctype_name, row_name)

	return {"deleted": True, "row": row_name, "diff": diff}


def list_provider_options() -> dict:
	"""List AI Providers with their configuration status and models.

	Read-only. ``configured`` is a presence check only — API key values never
	leave ``get_password``. Also returns a ``suggested`` provider+model pair:
	the first configured provider and its default chat model (reusing the
	hub orchestrator's preferred-model logic).
	"""
	_require_builder_capability()
	_require_doc_permission("AI Provider", "read")

	from huf.ai.app_seeding.hub_orchestrator import _default_model_for_provider

	providers = []
	suggested = None
	for name in frappe.get_all("AI Provider", pluck="name", order_by="creation asc"):
		models = frappe.get_all(
			"AI Model",
			filters={"provider": name},
			pluck="name",
			order_by="creation asc",
		)
		configured = _provider_has_key(name)
		providers.append(
			{
				"name": name,
				"provider_name": name,
				"configured": configured,
				"models": models,
			}
		)
		if configured and suggested is None:
			model = _default_model_for_provider(name)
			if model:
				suggested = {"provider": name, "model": model}

	return {"providers": providers, "suggested": suggested}
