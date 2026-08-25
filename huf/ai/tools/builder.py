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

from huf.ai.app_seeding import apps_loader
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


_MAX_RECENT_RESOURCES = 10


def _get_conversation_data(conversation_id: str | None) -> dict:
	"""Read and parse Agent Conversation.conversation_data as a dict.

	Mirrors huf.ai.tools.lazy_discovery._get_conversation_data / _load_state's
	shape ({"version": 1, "scope": {}, "items": [...]})  but this module only
	needs the raw dict form to stash a "_recent_resources" key on it directly
	(recent-resource tracking is unrelated to the items-list convention lazy
	discovery uses for its own state).
	"""
	if not conversation_id:
		return {}
	data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
	if not data_json:
		return {}
	try:
		data = json.loads(data_json)
	except (json.JSONDecodeError, TypeError):
		return {}
	return data if isinstance(data, dict) else {}


def _set_conversation_data(conversation_id: str, data: dict) -> None:
	frappe.db.set_value(
		"Agent Conversation", conversation_id, "conversation_data",
		json.dumps(data, ensure_ascii=False, indent=2),
	)


def _record_recent_resource(conversation_id: str | None, resource_type: str, name: str) -> None:
	"""Append a {type, name, created_at} entry to conversation_data._recent_resources.

	Newest first, capped at _MAX_RECENT_RESOURCES. No-ops when there is no
	conversation context (e.g. a tool invoked outside a conversation run) —
	recent-resource tracking is a convenience for "make that an App"-style
	follow-ups, not a hard requirement for creation to succeed.
	"""
	if not conversation_id or not frappe.db.exists("Agent Conversation", conversation_id):
		return
	data = _get_conversation_data(conversation_id)
	recent = data.get("_recent_resources")
	if not isinstance(recent, list):
		recent = []
	recent.insert(0, {"type": resource_type, "name": name, "created_at": frappe.utils.now()})
	data["_recent_resources"] = recent[:_MAX_RECENT_RESOURCES]
	_set_conversation_data(conversation_id, data)


def resolve_recent_resource(resource_type: str, conversation_id: str | None = None) -> dict:
	"""Resolve "that agent"/"the app I just made" to a concrete document name.

	Inspects the current Agent Conversation's conversation_data for
	"_recent_resources" (populated by draft_agent/draft_app on confirmed
	creation) and returns the newest entry matching resource_type.

	Still requires _require_doc_permission on the Agent Conversation being
	read: without it, a builder-capability holder could pass an arbitrary
	conversation_id belonging to a different user and learn which
	Agents/Apps were recently created there (Phase 13 hardening finding —
	conversation_id is normally auto-populated from run context, not
	user-supplied, but the parameter accepts an explicit override and must
	not trust it blindly).
	"""
	_require_builder_capability()
	if conversation_id:
		_require_doc_permission("Agent Conversation", "read", conversation_id)

	data = _get_conversation_data(conversation_id)
	recent = data.get("_recent_resources")
	if not isinstance(recent, list):
		return {
			"found": False,
			"message": f"No recent {resource_type} found in this conversation.",
		}

	for entry in recent:
		if isinstance(entry, dict) and entry.get("type") == resource_type:
			return {"found": True, "name": entry.get("name"), "type": resource_type}

	return {
		"found": False,
		"message": f"No recent {resource_type} found in this conversation.",
	}


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
	conversation_id: str | None = None,
) -> dict:
	"""Create a disabled (draft) Agent with a local prompt.

	The agent is created with disabled=1 so it cannot run until published
	via publish_agent. If the provider has no API key configured the draft
	is still created, but the result carries a warning flag.

	allow_chat defaults to True: hub-built agents are meant to be chatted
	with (e.g. managing data tables), and only chat-enabled agents appear
	in the chat UI pickers.

	conversation_id is auto-injected from the run context (see
	huf.ai.sdk_tools._merge_run_context) — it is not something the model
	needs to supply. On a confirmed creation it is recorded to the
	conversation's "_recent_resources" so later turns can resolve
	"the agent I just made" via resolve_recent_resource.
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
	_record_recent_resource(conversation_id, "agent", agent.name)

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


def list_agents(limit: int = 20) -> dict:
	"""List Agents the caller can see (read-only).

	Respects Agent read permission; returns only lightweight identifying
	fields, capped at ``limit``. Use get_agent for more detail on a single
	agent, and this to discover an existing agent to turn into an App
	(draft_app).
	"""
	_require_builder_capability()
	_require_doc_permission("Agent", "read")

	agents = frappe.get_list(
		"Agent",
		fields=["agent_name", "description", "disabled", "is_system"],
		limit=int(limit),
		order_by="modified desc",
	)

	return {"agents": agents, "limit": int(limit)}


def get_agent(agent_name: str) -> dict:
	"""Get a single Agent's summary (read-only).

	Deliberately excludes instructions/prompt content and any secrets — use
	this to check whether an agent exists and is suitable to back an App
	(draft_app), not to read its prompt.
	"""
	_require_builder_capability()
	_require_doc_permission("Agent", "read", agent_name)

	agent = _get_agent(agent_name)

	return {
		"agent_name": agent.agent_name,
		"description": agent.description,
		"provider": agent.provider,
		"model": agent.model,
		"disabled": agent.disabled,
		"is_system": agent.is_system,
		"allow_chat": agent.allow_chat,
	}


def list_apps(limit: int = 20) -> dict:
	"""List HUF App registry records the caller can see (read-only).

	Mirrors list_agents. Use this to discover existing Apps before deciding
	whether to draft_app a new one or update_app an existing one.
	"""
	_require_builder_capability()
	_require_doc_permission("HUF App", "read")

	apps = frappe.get_list(
		"HUF App",
		fields=["app_id", "title", "description", "route", "category", "enabled"],
		limit=int(limit),
		order_by="modified desc",
	)

	return {"apps": apps, "limit": int(limit)}


def get_app(app_id: str) -> dict:
	"""Get a single HUF App record's summary (read-only).

	Mirrors get_agent.
	"""
	_require_builder_capability()
	_require_doc_permission("HUF App", "read", app_id)

	if not frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App '{0}' does not exist.").format(app_id))
	app = frappe.get_doc("HUF App", app_id)

	return {
		"app_id": app.app_id,
		"title": app.title,
		"description": app.description,
		"route": app.route,
		"icon": app.icon,
		"category": app.category,
		"agent": app.get("agent") if app.meta.has_field("agent") else None,
		"enabled": app.enabled,
	}


def draft_app(
	app_id: str,
	title: str,
	agent_name: str,
	description: str = "",
	route: str | None = None,
	category: str = "Other",
	confirm: bool = False,
	conversation_id: str | None = None,
) -> dict:
	"""Two-phase creation of a chat-authored HUF App backed by an Agent.

	agent_name must resolve to an existing, accessible Agent (it is not
	cloned, only linked). confirm=False computes and returns the proposed
	App fields as a diff without touching the database; confirm=True calls
	apps_loader.create_app_from_agent to actually create it.

	conversation_id is auto-injected from the run context (see
	huf.ai.sdk_tools._merge_run_context) — it is not something the model
	needs to supply. On a confirmed creation it is recorded to the
	conversation's "_recent_resources" so later turns can resolve
	"make that an App" / "the app I just made" via resolve_recent_resource.
	"""
	_require_builder_capability()
	_require_doc_permission("Agent", "read", agent_name)
	confirm = _as_bool(confirm)

	if not frappe.db.exists("Agent", agent_name):
		frappe.throw(_("Agent '{0}' does not exist.").format(agent_name))
	if frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App '{0}' already exists.").format(app_id))

	diff = {
		"app_id": app_id,
		"title": title,
		"description": description,
		"agent": agent_name,
		"route": route or f"/apps/{app_id}",
		"category": category,
	}

	if not confirm:
		return {
			"created": False,
			"confirm_required": True,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to create the App.",
		}

	result = apps_loader.create_app_from_agent(
		app_id=app_id,
		title=title,
		agent_name=agent_name,
		description=description,
		route=route,
		category=category,
	)
	_record_recent_resource(conversation_id, "app", app_id)

	return {"created": True, "app": result, "diff": diff}


def update_app(app_id: str, confirm: bool = False, **fields) -> dict:
	"""Two-phase partial update of an existing HUF App record.

	confirm=False: returns an old/new diff of the proposed field changes
	without saving. confirm=True: applies via apps_loader.update_app.
	"""
	_require_builder_capability()
	_require_doc_permission("HUF App", "write", app_id)
	confirm = _as_bool(confirm)

	if not frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App '{0}' does not exist.").format(app_id))

	if "agent" in fields and fields["agent"]:
		_require_doc_permission("Agent", "read", fields["agent"])
		if not frappe.db.exists("Agent", fields["agent"]):
			frappe.throw(_("Agent '{0}' does not exist.").format(fields["agent"]))

	app = frappe.get_doc("HUF App", app_id)
	diff = {
		field: {"old": app.get(field), "new": value}
		for field, value in fields.items()
		if app.meta.has_field(field) and app.get(field) != value
	}

	if not confirm:
		return {
			"updated": False,
			"confirm_required": True,
			"app": app_id,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to apply.",
		}

	result = apps_loader.update_app(app_id, **fields)

	return {"updated": bool(diff), "app": result, "diff": diff}


def install_app(app_id: str, confirm: bool = False) -> dict:
	"""Two-phase, idempotent install (enable) of an HUF App.

	confirm=False: reports the app's current enabled state and what will
	change, without mutating anything. confirm=True: calls
	apps_loader.install_app, which is itself idempotent — re-running it for
	an already-enabled app never duplicates the record.
	"""
	_require_builder_capability()
	_require_doc_permission("HUF App", "write", app_id)
	confirm = _as_bool(confirm)

	if not frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App '{0}' does not exist.").format(app_id))

	currently_enabled = bool(frappe.db.get_value("HUF App", app_id, "enabled"))
	diff = {"enabled": {"old": currently_enabled, "new": True}}

	if not confirm:
		return {
			"installed": False,
			"confirm_required": True,
			"app": app_id,
			"already_installed": currently_enabled,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to install the App.",
		}

	result = apps_loader.install_app(app_id)

	return {"installed": True, "app": result, "diff": diff}


# MIME types allowed for app icons (covers common formats; SVG flagged for
# sanitization gap noted in §F of the plan — platform-wide SVG handling is
# deferred, but this validator ensures the gap is explicit and auditable).
_ICON_MIME_ALLOWLIST = {
	"image/png",
	"image/jpeg",
	"image/webp",
	"image/svg+xml",
}


def set_app_icon(app_id: str, source: str, value: str, confirm: bool = False) -> dict:
	"""Two-phase app icon setter supporting three sources of icon data.

	source is one of:
	- "path": value is a site-local asset path (validated to start with "/",
	  no URL scheme). Reuses the same validation rule as apps_loader._validate_route.
	- "uploaded": value is a File doc name (looked up via frappe.get_doc("File", ...)).
	  File must exist and its content_type must be in _ICON_MIME_ALLOWLIST.
	  SVG uploads are flagged in comments as needing sanitization (platform-wide gap).
	- "generated": value is an image generation prompt (str). Calls
	  handle_generate_image and uses the resulting file.

	All three branches follow the two-phase confirm contract: confirm=False
	returns a diff with confirm_required=True; confirm=True applies the mutation
	via apps_loader.update_app or fallback frappe.db.set_value.

	Requires _require_builder_capability() + _require_doc_permission("HUF App", "write", app_id).
	"""
	_require_builder_capability()
	_require_doc_permission("HUF App", "write", app_id)
	confirm = _as_bool(confirm)
	source = (source or "").strip().lower()

	if not frappe.db.exists("HUF App", app_id):
		frappe.throw(_("HUF App '{0}' does not exist.").format(app_id))

	if source not in ("path", "uploaded", "generated"):
		frappe.throw(
			_("source must be one of: 'path', 'uploaded', 'generated' (got '{0}')").format(source)
		)

	current_icon = frappe.db.get_value("HUF App", app_id, "icon") or ""
	resolved_icon_value = None

	# Validate and resolve the icon value based on source
	if source == "path":
		# Validate as a site-local path: must start with "/" and not contain URL scheme
		if not value.startswith("/"):
			frappe.throw(
				_("Icon path must be an absolute site-local path beginning with '/'")
			)
		if "://" in value or value.startswith("//"):
			frappe.throw(
				_("Icon path must not contain a URL scheme (external URLs are not allowed)")
			)
		resolved_icon_value = value

	elif source == "uploaded":
		# Look up the File doc and validate content_type
		if not frappe.db.exists("File", value):
			frappe.throw(_("File '{0}' does not exist.").format(value))
		file_doc = frappe.get_doc("File", value)
		content_type = file_doc.content_type or ""

		if content_type not in _ICON_MIME_ALLOWLIST:
			frappe.throw(
				_(
					"File content type '{0}' is not allowed for icons. "
					"Allowed types: {1}"
				).format(content_type, ", ".join(sorted(_ICON_MIME_ALLOWLIST)))
			)

		# SVG files require sanitization (currently a platform-wide gap; this
		# gap is documented in the plan's §F. Flagging explicitly for audit trail).
		if content_type == "image/svg+xml":
			frappe.log_warning(
				f"SVG icon upload for app '{app_id}': platform-wide SVG sanitization gap noted in plan §F",
				"SVG Icon Upload"
			)

		# Use the file's file path/URL as the icon value
		resolved_icon_value = file_doc.file_url or f"/files/{file_doc.file_name}"

	elif source == "generated":
		# Call handle_generate_image; the function is async, so we run it via
		# asyncio.run() in a separate event loop (builder tools are synchronous).
		import asyncio

		# Get the agent configured for this app (if any) for context
		agent_name = frappe.db.get_value("HUF App", app_id, "agent")
		if not agent_name:
			frappe.throw(
				_(
					"Cannot generate an icon: this app has no linked Agent. "
					"Link an Agent to the app first via update_app(app_id, agent=...)"
				)
			)

		try:
			from huf.ai.handlers.media import handle_generate_image

			# Run the async function in a new event loop (asyncio.run creates one)
			result = asyncio.run(
				handle_generate_image(
					prompt=value,
					agent_name=agent_name,
					n=1,
					size="1024x1024",
					quality="standard",
				)
			)

			if not result.get("success"):
				frappe.throw(
					_("Image generation failed: {0}").format(
						result.get("error", "Unknown error")
					)
				)

			images = result.get("images", [])
			if not images:
				frappe.throw(_("Image generation returned no images."))

			# Use the first (and only, since n=1) generated image's file_id or URL
			first_image = images[0]
			resolved_icon_value = first_image.get("url") or first_image.get("file_id")

			if not resolved_icon_value:
				frappe.throw(_("Image generation returned no usable URL or file ID."))

		except asyncio.DeprecationWarning:
			# Python 3.10+ warns about nested event loops in some contexts;
			# try an alternative if asyncio.run fails (e.g., in a sync context
			# that already has a running loop). Fall back to a direct sync wrapper.
			try:
				from huf.ai.handlers.media import handle_generate_image as sync_wrapper
				import sys

				if sys.version_info >= (3, 10):
					# Use asyncio.ensure_future or similar for already-running loop
					loop = asyncio.get_event_loop()
					result = loop.run_until_complete(
						sync_wrapper(
							prompt=value,
							agent_name=agent_name,
							n=1,
							size="1024x1024",
							quality="standard",
						)
					)
				else:
					result = asyncio.run(
						sync_wrapper(
							prompt=value,
							agent_name=agent_name,
							n=1,
							size="1024x1024",
							quality="standard",
						)
					)

				if not result.get("success"):
					frappe.throw(
						_("Image generation failed: {0}").format(
							result.get("error", "Unknown error")
						)
					)

				images = result.get("images", [])
				if not images:
					frappe.throw(_("Image generation returned no images."))

				first_image = images[0]
				resolved_icon_value = first_image.get("url") or first_image.get("file_id")

				if not resolved_icon_value:
					frappe.throw(_("Image generation returned no usable URL or file ID."))

			except Exception as e:
				frappe.throw(
					_("Image generation failed with exception: {0}").format(str(e))
				)

	# Build the diff (old icon → new icon)
	diff = {"icon": {"old": current_icon, "new": resolved_icon_value}}

	if not confirm:
		return {
			"set": False,
			"confirm_required": True,
			"app": app_id,
			"source": source,
			"diff": diff,
			"message": "Review the diff and call again with confirm=True to set the icon.",
		}

	# Apply the mutation: try update_app first, fall back to db.set_value
	try:
		# update_app exists in apps_loader and handles validation/save
		apps_loader.update_app(app_id, icon=resolved_icon_value)
	except AttributeError:
		# Fallback: update_app doesn't exist yet (pre-Phase 2 state)
		frappe.db.set_value("HUF App", app_id, "icon", resolved_icon_value)

	return {
		"set": True,
		"app": app_id,
		"source": source,
		"icon": resolved_icon_value,
		"diff": diff,
	}


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
