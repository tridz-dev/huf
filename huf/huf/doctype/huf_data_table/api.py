import json
import re

import frappe
from frappe import _

from huf.permissions import has_capability

from .validators import (
	LAYOUT_FIELD_TYPES,
	get_search_fields,
	resolve_autoname,
	validate_and_prepare_fields,
)

# Data tables do not have a dedicated capability yet; reuse flow capabilities
# as the closest admin-level permission boundary.
_WRITE_CAPABILITY = "flows.manage"
_READ_CAPABILITY = "flows.use"


def _require_write():
	if not has_capability(frappe.session.user, _WRITE_CAPABILITY):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_read():
	if not has_capability(frappe.session.user, _READ_CAPABILITY):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def create_data_table(
	table_name: str,
	fields: str | list[dict],
	description: str = "",
	icon: str = "",
	autoname_method: str = "Autoincrement",
	title_field: str = "",
) -> dict:
	"""Create a new data table (DocType + registry entry).

	Requires: flows.manage
	"""
	_require_write()
	if isinstance(fields, str):
		fields = json.loads(fields)

	table_name = table_name.strip()
	if not table_name:
		frappe.throw("Table name is required")

	doctype_name = f"HF {table_name}"

	if frappe.db.exists("DocType", doctype_name):
		frappe.throw(f"Table '{table_name}' already exists")

	if frappe.db.exists("Huf Data Table", {"table_name": table_name}):
		frappe.throw(f"Table '{table_name}' already exists")

	validated_fields = validate_and_prepare_fields(fields)

	autoname = resolve_autoname(autoname_method, title_field)

	dt = frappe.new_doc("DocType")
	dt.update(
		{
			"name": doctype_name,
			"module": "Huf",
			"custom": 1,
			"fields": validated_fields,
			"istable": 0,
			"issingle": 0,
			"autoname": autoname,
			"title_field": title_field or "",
			"search_fields": get_search_fields(validated_fields),
			"sort_field": "modified",
			"sort_order": "DESC",
			"track_changes": 1,
			"allow_rename": 1,
		}
	)
	dt.set(
		"permissions",
		[
			{
				"role": "System Manager",
				"read": 1,
				"write": 1,
				"create": 1,
				"delete": 1,
				"print": 1,
				"email": 1,
				"share": 1,
			}
		],
	)
	dt.insert()

	data_field_count = len([f for f in validated_fields if f["fieldtype"] not in LAYOUT_FIELD_TYPES])

	registry = frappe.new_doc("Huf Data Table")
	registry.update(
		{
			"table_name": table_name,
			"doctype_name": doctype_name,
			"description": description,
			"icon": icon,
			"field_count": data_field_count,
			"autoname_method": autoname_method,
			"title_field_name": title_field,
		}
	)
	registry.insert()

	return {
		"success": True,
		"data": {
			"name": registry.name,
			"table_name": table_name,
			"doctype_name": doctype_name,
		},
	}


@frappe.whitelist()
def update_data_table(
	name: str,
	fields: str | list[dict] | None = None,
	description: str | None = None,
	icon: str | None = None,
) -> dict:
	"""Update table structure (add/remove/reorder fields, update metadata).

	Requires: flows.manage
	"""
	_require_write()
	registry = frappe.get_doc("Huf Data Table", name)

	if fields is not None:
		if isinstance(fields, str):
			fields = json.loads(fields)

		validated_fields = validate_and_prepare_fields(fields)

		dt = frappe.get_doc("DocType", registry.doctype_name)
		dt.fields = []
		for field_data in validated_fields:
			dt.append("fields", field_data)
		dt.search_fields = get_search_fields(validated_fields)
		dt.save()

		registry.field_count = len([f for f in validated_fields if f["fieldtype"] not in LAYOUT_FIELD_TYPES])

	if description is not None:
		registry.description = description
	if icon is not None:
		registry.icon = icon

	registry.save()

	return {"success": True, "data": {"name": registry.name}}


@frappe.whitelist()
def delete_data_table(name: str) -> dict:
	"""Delete a data table and all its records.

	Requires: flows.manage
	"""
	_require_write()
	registry = frappe.get_doc("Huf Data Table", name)
	doctype_name = registry.doctype_name

	record_count = 0
	try:
		record_count = frappe.db.count(doctype_name)
	except Exception:
		pass

	if frappe.db.exists("DocType", doctype_name):
		frappe.delete_doc("DocType", doctype_name, force=True)

	frappe.delete_doc("Huf Data Table", name)

	return {"success": True, "data": {"deleted_records": record_count}}


@frappe.whitelist()
def get_table_record_counts(names: str | list[str]) -> dict:
	"""Get live record counts for a list of Huf data tables (by registry name).

	Standard REST can't count records across dynamic DocTypes,
	so this helper exists for the listing page enrichment.

	Requires: flows.use
	"""
	_require_read()
	if isinstance(names, str):
		names = json.loads(names)

	counts = {}
	for name in names:
		try:
			registry = frappe.get_doc("Huf Data Table", name)
			counts[name] = frappe.db.count(registry.doctype_name)
		except Exception:
			counts[name] = 0

	return counts


@frappe.whitelist()
def get_table_schema(name: str) -> dict:
	"""Get complete table schema (fields with all properties).

	Requires: flows.use
	"""
	_require_read()
	registry = frappe.get_doc("Huf Data Table", name)
	meta = frappe.get_meta(registry.doctype_name)

	fields = []
	for field in meta.fields:
		fields.append(
			{
				"fieldname": field.fieldname,
				"fieldtype": field.fieldtype,
				"label": field.label,
				"reqd": field.reqd,
				"unique": field.unique,
				"read_only": field.read_only,
				"hidden": field.hidden,
				"default": field.default,
				"options": field.options,
				"description": field.description,
				"in_list_view": field.in_list_view,
				"non_negative": field.non_negative,
				"idx": field.idx,
			}
		)

	return {
		"name": registry.name,
		"table_name": registry.table_name,
		"doctype_name": registry.doctype_name,
		"description": registry.description,
		"icon": registry.icon,
		"autoname_method": registry.autoname_method,
		"title_field_name": registry.title_field_name,
		"fields": fields,
	}


# ---------------------------------------------------------------------------
# Agent access scaffolding ("Add to agent")
# ---------------------------------------------------------------------------

# Plain user-facing action -> (Agent Tool Function.types, required_permission) specs.
# "view" intentionally scaffolds TWO tools: an agent that can list but not read a
# single record is useless. All scaffolding/idempotency logic derives from this one
# mapping — do not duplicate it.
# TODO (Advanced drawer): expose the remaining `types` values (Submit/Cancel Document,
# Get/Set Value, bulk "Multiple" variants, ...) behind an advanced UI when needed.
TABLE_ACTION_MAP: dict[str, tuple[tuple[str, str], ...]] = {
	"view": (("Get List", "read"), ("Get Document", "read")),
	"create": (("Create Document", "create"),),
	"edit": (("Update Document", "write"),),
	"delete": (("Delete Document", "delete"),),
}

# Reverse lookup derived from TABLE_ACTION_MAP: types -> plain action.
_TYPES_TO_ACTION: dict[str, str] = {
	types: action for action, specs in TABLE_ACTION_MAP.items() for types, _ in specs
}

# Agent Tool Type category assigned to scaffolded tools (created on demand).
_TABLE_TOOL_TYPE = "Data Table"

# Tool types whose generated schema is driven by the tool's `parameters` child
# rows (see AgentToolFunction.build_params_json_from_table /
# prepare_function_params). For these we scaffold parameter rows from the
# table's DocType meta so the LLM gets a real field schema:
# - Create Document: properties come ONLY from parameters (without rows the
#   schema is an empty object with additionalProperties: False — the LLM
#   literally cannot supply any field values).
# - Update Document: same, plus document_id (auto-added by the controller).
# - Get List: parameters become typed `filters.properties` (filters stay open
#   via additionalProperties: True, so this only documents the real fields).
_PARAM_TOOL_TYPES = {"Get List", "Create Document", "Update Document"}

# HUF Table fieldtype -> Agent Function Params `type` (string / integer /
# number / boolean). The controller passes param.type straight into JSON
# Schema "type", so "float" is deliberately NOT used (invalid JSON Schema);
# every float-ish type maps to "number". All remaining HUF-table data
# fieldtypes (Data, Small Text, Text, Long Text, Date, Datetime, Time, Phone,
# Color, Link, Select) map to "string".
_FIELD_TYPE_TO_PARAM_TYPE = {
	"Int": "integer",
	"Float": "number",
	"Currency": "number",
	"Percent": "number",
	"Duration": "integer",
	"Rating": "number",
	"Check": "boolean",
}

# Fieldtypes that are layout/presentational, never data an LLM should set.
_PARAM_EXCLUDED_FIELD_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading"}

_TOOL_DESCRIPTIONS = {
	"Get List": "List records from {label} with optional filters",
	"Get Document": "Get a single {label} record by ID",
	"Create Document": "Create a new {label} record",
	"Update Document": "Update an existing {label} record",
	"Delete Document": "Delete a {label} record",
}


def _resolve_table_registry(table: str):
	"""Resolve a Huf Data Table by registry docname or by table_name."""
	if frappe.db.exists("Huf Data Table", table):
		return frappe.get_doc("Huf Data Table", table)
	name = frappe.db.get_value("Huf Data Table", {"table_name": table}, "name")
	if name:
		return frappe.get_doc("Huf Data Table", name)
	frappe.throw(_("Unknown data table: {0}").format(table))


def _table_tool_name(doctype_name: str, types: str) -> str:
	"""Deterministic tool/doc name for a (doctype, types) pair.

	The human-readable form is "{doctype_name} - {types}" (e.g. "HF Customers - Get
	List"); Agent Tool Function names may only contain [a-zA-Z0-9_-], so anything
	else is collapsed to "_". Determinism is what makes scaffolding idempotent.
	"""
	return re.sub(r"[^a-zA-Z0-9_-]", "_", f"{doctype_name} - {types}")


def _ensure_table_tool_type() -> str:
	if not frappe.db.exists("Agent Tool Type", _TABLE_TOOL_TYPE):
		frappe.get_doc({"doctype": "Agent Tool Type", "name1": _TABLE_TOOL_TYPE}).insert()
	return _TABLE_TOOL_TYPE


def _table_field_params(doctype_name: str, types: str) -> list[dict]:
	"""Build Agent Function Params rows for a scaffolded tool from DocType meta.

	Exclusion rule: layout/presentational fieldtypes (Section Break, Column
	Break, Tab Break, HTML, Heading), hidden fields and read-only fields —
	none of those are values an LLM should supply.

	`required` is carried only for Create Document: marking a field required on
	an Update tool would force the LLM to resend every required field on every
	update (the controller already requires document_id there), and Get List
	filters are never mandatory. Select `options` are carried so the controller
	emits them as a JSON Schema enum (it only does so for type "string").
	"""
	rows = []
	for field in frappe.get_meta(doctype_name).fields:
		if field.fieldtype in _PARAM_EXCLUDED_FIELD_TYPES or field.hidden or field.read_only:
			continue
		rows.append(
			{
				"label": field.label or field.fieldname,
				"fieldname": field.fieldname,
				"type": _FIELD_TYPE_TO_PARAM_TYPE.get(field.fieldtype, "string"),
				"required": 1 if (types == "Create Document" and field.reqd) else 0,
				"description": field.description or "",
				"options": field.options if field.fieldtype == "Select" and field.options else "",
			}
		)
	return rows


def _sync_tool_params(tool_name: str, doctype_name: str, types: str) -> None:
	"""Refresh an existing scaffolded tool's parameters to match the table's
	current fields (no-op for tool types that don't use parameters).

	Refreshing matters because a stale schema is a silent bug: the generated
	schema sets additionalProperties: False, so a field added to the table
	after scaffolding would be impossible for the LLM to set. The refresh only
	happens through the deterministic tool name, i.e. tools this feature owns.
	Tradeoff: hand-edited parameter rows on such a tool are replaced. Rows are
	only rewritten when they differ, so re-running without a schema change is
	a no-op (no duplicate rows, no needless saves).
	"""
	if types not in _PARAM_TOOL_TYPES:
		return
	desired = _table_field_params(doctype_name, types)
	tool = frappe.get_doc("Agent Tool Function", tool_name)
	current = [
		{
			"label": row.label or "",
			"fieldname": row.fieldname or "",
			"type": row.type or "",
			"required": 1 if row.required else 0,
			"description": row.description or "",
			"options": row.options or "",
		}
		for row in tool.parameters
	]
	if current == desired:
		return
	tool.set("parameters", desired)
	tool.save()


def _scaffold_tool(doctype_name: str, table_label: str, types: str, permission: str) -> str:
	"""Return the deterministic tool name, creating the Agent Tool Function if missing.

	Only document fields are set here; `params` and `function_definition` are
	auto-generated by the Agent Tool Function controller on save. For tool
	types in _PARAM_TOOL_TYPES the `parameters` child rows are scaffolded from
	the table's DocType meta (and refreshed on reuse) so the generated schema
	exposes the table's real fields.
	"""
	tool_name = _table_tool_name(doctype_name, types)
	if frappe.db.exists("Agent Tool Function", tool_name):
		_sync_tool_params(tool_name, doctype_name, types)
		return tool_name

	description = _TOOL_DESCRIPTIONS.get(types, f"{types} on {{label}}").format(label=table_label)
	doc = {
		"doctype": "Agent Tool Function",
		"tool_name": tool_name,
		"description": description,
		"types": types,
		"reference_doctype": doctype_name,
		"required_permission": permission,
		"tool_type": _ensure_table_tool_type(),
	}
	if types in _PARAM_TOOL_TYPES:
		doc["parameters"] = _table_field_params(doctype_name, types)
	frappe.get_doc(doc).insert()
	return tool_name


def _compute_access(doctype_name: str, agent: str | None = None) -> list[dict]:
	"""Which agents have tools for this doctype attached, mapped back to plain actions.

	An agent counts as having "view" when it has EITHER Get List or Get Document;
	the attached tool names are included so partial state stays visible.
	"""
	tools = frappe.get_all(
		"Agent Tool Function",
		filters={"reference_doctype": doctype_name, "types": ["in", list(_TYPES_TO_ACTION)]},
		fields=["name", "types"],
	)
	if not tools:
		return []

	tool_types = {t.name: t.types for t in tools}
	filters = {"parenttype": "Agent", "tool": ["in", list(tool_types)]}
	if agent:
		filters["parent"] = agent

	by_agent: dict[str, dict] = {}
	for link in frappe.get_all("Agent Tool", filters=filters, fields=["parent", "tool"]):
		entry = by_agent.setdefault(link.parent, {"actions": set(), "tools": []})
		entry["tools"].append(link.tool)
		action = _TYPES_TO_ACTION.get(tool_types.get(link.tool))
		if action:
			entry["actions"].add(action)

	return [
		{
			"agent": agent_name,
			"agent_name": frappe.db.get_value("Agent", agent_name, "agent_name") or agent_name,
			"actions": [a for a in TABLE_ACTION_MAP if a in entry["actions"]],
			"tools": sorted(entry["tools"]),
		}
		for agent_name, entry in sorted(by_agent.items())
	]


@frappe.whitelist()
def get_table_agent_access(table: str) -> list:
	"""Which agents currently have access to this HUF Table, and with which actions.

	Returns: [{"agent": <name>, "agent_name": <label>, "actions": [...], "tools": [...]}]

	Requires: flows.use
	"""
	_require_read()
	registry = _resolve_table_registry(table)
	return _compute_access(registry.doctype_name)


@frappe.whitelist()
def set_table_agent_access(table: str, agent: str, actions: str | list) -> dict:
	"""Make the agent's access to this table EXACTLY `actions` (idempotent).

	- Reuses the existing Agent Tool Function doc for each (table, action) pair when
	  one already exists under the deterministic tool name; otherwise creates it.
	- Attaches tools to the agent's `agent_tool` child table only if not already linked.
	- Detaches child rows for actions NOT in `actions`; tool docs are never deleted.
	- Returns the resulting state in the same shape as get_table_agent_access.

	Requires: flows.manage
	"""
	_require_write()
	if isinstance(actions, str):
		actions = json.loads(actions)
	actions = [str(a).strip().lower() for a in actions]
	unknown = [a for a in actions if a not in TABLE_ACTION_MAP]
	if unknown:
		frappe.throw(_("Unknown action(s): {0}").format(", ".join(unknown)))

	registry = _resolve_table_registry(table)
	doctype_name = registry.doctype_name
	agent_doc = frappe.get_doc("Agent", agent)

	wanted_tools = set()
	for action in actions:
		for types, permission in TABLE_ACTION_MAP[action]:
			wanted_tools.add(_scaffold_tool(doctype_name, registry.table_name, types, permission))

	# Attach wanted tools (no duplicate child rows).
	changed = False
	existing = {row.tool for row in agent_doc.agent_tool}
	for tool_name in sorted(wanted_tools - existing):
		agent_doc.append("agent_tool", {"tool": tool_name})
		changed = True

	# Detach attached tools for this table whose action is not wanted.
	attached = [row.tool for row in agent_doc.agent_tool]
	if attached:
		attached_meta = {
			t.name: t
			for t in frappe.get_all(
				"Agent Tool Function",
				filters={"name": ["in", attached], "reference_doctype": doctype_name},
				fields=["name", "types"],
			)
		}
		detach = {
			name
			for name, t in attached_meta.items()
			if _TYPES_TO_ACTION.get(t.types) and _TYPES_TO_ACTION[t.types] not in actions
		}
		if detach:
			kept = [row for row in agent_doc.agent_tool if row.tool not in detach]
			if len(kept) != len(agent_doc.agent_tool):
				agent_doc.agent_tool = kept
				changed = True

	if changed:
		agent_doc.save()

	for entry in _compute_access(doctype_name, agent=agent_doc.name):
		return entry
	return {
		"agent": agent_doc.name,
		"agent_name": agent_doc.agent_name,
		"actions": [],
		"tools": [],
	}
