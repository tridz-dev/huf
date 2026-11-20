"""Row-level and summary endpoints for Huf Data Tables (bulk ops, summary, tool signature)."""

import json

import frappe
from frappe import _

from .api import (
	_TYPES_TO_ACTION,
	_PARAM_TOOL_TYPES,
	_require_read,
	_resolve_table_registry,
	_sync_tool_params,
	_table_field_params,
	_compute_access,
	TABLE_ACTION_MAP,
)

ALLOWED_OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "like", "not like", "in", "not in", "is", "between"}
MAX_BULK_ROWS = 5000
RESERVED_KEYS = frozenset(
	("name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "doctype", "parent", "parentfield", "parenttype")
)


def strip_reserved(values):
	"""Drop server-controlled keys from an incoming row/values dict."""
	if not isinstance(values, dict):
		return {}
	return {k: v for k, v in values.items() if k not in RESERVED_KEYS}


def _loads(value, default):
	if value is None or value == "":
		return default
	return json.loads(value) if isinstance(value, str) else value


def validate_filters(filters):
	"""Reject filter operators outside the allow-list. Accepts list of [f, op, v] / [dt, f, op, v] or dict."""
	if not filters:
		return filters
	if isinstance(filters, dict):
		for value in filters.values():
			if isinstance(value, (list, tuple)) and value:
				_check_operator(value[0])
		return filters
	for entry in filters:
		if isinstance(entry, (list, tuple)):
			op = entry[2] if len(entry) >= 4 else entry[1] if len(entry) >= 2 else None
			_check_operator(op)
		elif isinstance(entry, dict) and "operator" in entry:
			_check_operator(entry["operator"])
	return filters


def _check_operator(op):
	if str(op).strip().lower() not in ALLOWED_OPERATORS:
		frappe.throw(_("Filter operator not allowed: {0}").format(op), frappe.ValidationError)


def build_record_query(doctype_name, fields, filters, search) -> dict:
	"""Build get_list kwargs (fields, filters, or_filters) with validated filters."""
	if isinstance(fields, str):
		try:
			fields = json.loads(fields)
		except ValueError:
			fields = [fields]
	if isinstance(filters, str) and filters:
		filters = json.loads(filters)
	validate_filters(filters)
	or_filters = []
	if search and search.strip():
		text = f"%{search.strip()}%"
		meta = frappe.get_meta(doctype_name)
		if meta.search_fields:
			or_filters = [[f.strip(), "like", text] for f in meta.search_fields.split(",")]
		name_field = meta.title_field or "name"
		if name_field not in (meta.search_fields or ""):
			or_filters.append([name_field, "like", text])
	return {"fields": fields, "filters": filters, "or_filters": or_filters}


def count_records(doctype_name, query) -> int:
	"""Total rows matching the same filters/search as the page query."""
	if not query["or_filters"]:
		return frappe.db.count(doctype_name, filters=query["filters"] or None)
	rows = frappe.get_list(
		doctype_name,
		fields=[{"COUNT": "name", "as": "total"}],
		filters=query["filters"],
		or_filters=query["or_filters"],
		limit_page_length=0,
	)
	return int(rows[0]["total"]) if rows else 0


def _check_bulk(names_or_rows):
	if len(names_or_rows) > MAX_BULK_ROWS:
		frappe.throw(_("Too many rows (max {0})").format(MAX_BULK_ROWS))


def _require_table(doctype_name):
	if not frappe.db.exists("Huf Data Table", {"doctype_name": doctype_name}):
		frappe.throw(_("Unknown data table: {0}").format(doctype_name))


@frappe.whitelist(methods=["POST"])
def bulk_insert_rows(doctype_name: str, rows: str | list) -> dict:
	"""Insert many rows; per-row errors are collected, valid rows still insert."""
	_require_read()
	_require_table(doctype_name)
	rows = _loads(rows, [])
	_check_bulk(rows)
	inserted, errors = [], []
	for index, row in enumerate(rows):
		try:
			doc = frappe.get_doc({**strip_reserved(row), "doctype": doctype_name})
			doc.insert()
			inserted.append(doc.name)
		except Exception as exc:
			errors.append({"index": index, "message": str(exc)})
	return {"inserted": inserted, "errors": errors}


@frappe.whitelist(methods=["POST"])
def bulk_update_rows(doctype_name: str, names: str | list, values: str | dict) -> dict:
	_require_read()
	_require_table(doctype_name)
	names, values = _loads(names, []), _loads(values, {})
	_check_bulk(names)
	updated = 0
	for name in names:
		doc = frappe.get_doc(doctype_name, name)
		doc.check_permission("write")
		doc.update(strip_reserved(values))
		doc.save()
		updated += 1
	return {"updated": updated}


@frappe.whitelist(methods=["POST"])
def bulk_delete_rows(doctype_name: str, names: str | list) -> dict:
	"""Delete rows via frappe.delete_doc (Deleted Document rows are kept for restore)."""
	_require_read()
	_require_table(doctype_name)
	names = _loads(names, [])
	_check_bulk(names)
	deleted = 0
	for name in names:
		frappe.delete_doc(doctype_name, name)
		deleted += 1
	return {"deleted": deleted}


@frappe.whitelist(methods=["POST"])
def restore_rows(doctype_name: str, names: str | list) -> dict:
	"""Restore rows deleted by bulk_delete_rows from their Deleted Document records."""
	_require_read()
	_require_table(doctype_name)
	names = _loads(names, [])
	_check_bulk(names)
	if not (frappe.has_permission(doctype_name, "create") and frappe.has_permission(doctype_name, "read")):
		frappe.throw(_("You do not have permission to restore rows."), frappe.PermissionError)
	can_admin = frappe.has_permission("Deleted Document", "write")
	restored = 0
	for name in names:
		deleted_name = frappe.db.get_value(
			"Deleted Document",
			{"deleted_doctype": doctype_name, "deleted_name": name, "restored": 0},
			["name", "owner"],
			order_by="creation desc",
			as_dict=True,
		)
		# Deleted Document.owner is the user who deleted the row. Anything the caller
		# did not delete (or does not exist) is skipped identically: no existence leak.
		if not deleted_name or not (can_admin or deleted_name.owner == frappe.session.user):
			continue
		deleted = frappe.get_doc("Deleted Document", deleted_name.name)
		doc = frappe.get_doc(json.loads(deleted.data))
		original = {k: doc.get(k) for k in ("owner", "creation", "modified", "modified_by")}
		doc.flags.from_restore = True
		# Document.insert() renames to a fresh name (autoincrement/hash) unless set_name is given;
		# without it the row comes back under a new id and lookups by the old name find nothing.
		doc.insert(set_name=str(deleted.deleted_name))
		frappe.db.set_value(doc.doctype, doc.name, original, update_modified=False)
		deleted.db_set({"restored": 1, "new_name": doc.name})
		restored += 1
	return {"restored": restored}


def _tools_for(doctype_name: str) -> list:
	return frappe.get_all(
		"Agent Tool Function",
		filters={"reference_doctype": doctype_name, "types": ["in", list(_TYPES_TO_ACTION)]},
		fields=["name", "types"],
	)


def resync_table_tools(doctype_name: str) -> None:
	"""Re-sync agent tool params after a schema change."""
	for tool in _tools_for(doctype_name):
		if tool.types in _PARAM_TOOL_TYPES:
			_sync_tool_params(tool.name, doctype_name, tool.types)


def remove_table_tools(doctype_name: str) -> None:
	"""Delete the table's Agent Tool Functions and the Agent.agent_tool links to them."""
	names = [tool.name for tool in _tools_for(doctype_name)]
	if not names:
		return
	frappe.db.delete("Agent Tool", {"parenttype": "Agent", "tool": ["in", names]})
	for name in names:
		frappe.delete_doc("Agent Tool Function", name, force=True, ignore_permissions=True)


@frappe.whitelist()
def list_tables_summary() -> list:
	"""All tables with counts and agent access, using a fixed number of queries plus one count per table."""
	_require_read()
	registries = frappe.get_all(
		"Huf Data Table",
		fields=["name", "table_name", "description", "table_group", "icon", "field_count", "modified", "doctype_name"],
		order_by="modified desc",
	)
	doctypes = [r.doctype_name for r in registries]
	tool_info = {}
	if doctypes:
		for tool in frappe.get_all(
			"Agent Tool Function",
			filters={"reference_doctype": ["in", doctypes], "types": ["in", list(_TYPES_TO_ACTION)]},
			fields=["name", "types", "reference_doctype"],
		):
			tool_info[tool.name] = tool
	agents_by_doctype: dict = {}
	if tool_info:
		links = frappe.get_all(
			"Agent Tool", filters={"parenttype": "Agent", "tool": ["in", list(tool_info)]}, fields=["parent", "tool"]
		)
		agent_names = dict(
			frappe.get_all("Agent", filters={"name": ["in", list({link.parent for link in links})]}, fields=["name", "agent_name"], as_list=True)
		)
		for link in links:
			tool = tool_info[link.tool]
			entry = agents_by_doctype.setdefault(tool.reference_doctype, {}).setdefault(link.parent, set())
			entry.add(_TYPES_TO_ACTION[tool.types])
	result = []
	for reg in registries:
		try:
			record_count = frappe.db.count(reg.doctype_name)
		except (frappe.DoesNotExistError, frappe.DataError):
			record_count = 0
		agents = [
			{
				"agent": agent,
				"agent_name": agent_names.get(agent) or agent,
				"actions": [a for a in TABLE_ACTION_MAP if a in actions],
			}
			for agent, actions in sorted(agents_by_doctype.get(reg.doctype_name, {}).items())
		]
		result.append({
			"name": reg.name,
			"table_name": reg.table_name,
			"description": reg.description,
			"table_group": reg.table_group,
			"icon": reg.icon,
			"field_count": reg.field_count,
			"record_count": record_count,
			"modified": reg.modified,
			"agents": agents,
		})
	return result


@frappe.whitelist()
def get_table_dependencies(table_id: str) -> dict:
	"""What deleting the table would affect: records, agents with access, flows mentioning it."""
	_require_read()
	registry = _resolve_table_registry(table_id)
	try:
		record_count = frappe.db.count(registry.doctype_name)
	except (frappe.DoesNotExistError, frappe.DataError):
		record_count = 0
	agents = [
		{"agent": entry["agent"], "agent_name": entry["agent_name"]}
		for entry in _compute_access(registry.doctype_name)
	]
	flows = []
	for needle in {registry.doctype_name, registry.table_name}:
		for flow in frappe.get_all(
			"Flow Definition",
			filters=[["definition_json", "like", f"%{needle}%"]],
			fields=["name", "flow_name"],
		):
			flows.append({"name": flow.name, "title": flow.flow_name or flow.name})
	unique = {flow["name"]: flow for flow in flows}
	return {"record_count": record_count, "agents": agents, "flows": list(unique.values())}


def _signature_params(doctype_name: str, types: str) -> list[dict]:
	if types in _PARAM_TOOL_TYPES:
		raw = _table_field_params(doctype_name, types)
		params = [
			{
				"name": row["fieldname"],
				"type": row["type"],
				"required": bool(row["required"]),
				"description": row["description"],
				"options": row["options"],
			}
			for row in raw
		]
	else:
		params = []
	if types in {"Get Document", "Update Document", "Delete Document"}:
		params.insert(0, {"name": "name", "type": "string", "required": True, "description": "Record ID", "options": ""})
	return params


@frappe.whitelist()
def get_table_tool_signature(table_id: str) -> dict:
	"""The tool signatures an agent would see for this table (live from the schema)."""
	from .api import _TOOL_DESCRIPTIONS, _table_tool_name

	_require_read()
	registry = _resolve_table_registry(table_id)
	tools = []
	for action, specs in TABLE_ACTION_MAP.items():
		for types, _permission in specs:
			tools.append({
				"action": action,
				"tool_name": _table_tool_name(registry.doctype_name, types),
				"description": _TOOL_DESCRIPTIONS[types].format(label=registry.table_name),
				"params": _signature_params(registry.doctype_name, types),
			})
	return {"tools": tools}


@frappe.whitelist()
def get_table_agent_activity(table_id: str, limit: int = 20) -> list:
	"""Recent tool calls against the table's tools (best effort; [] if none)."""
	_require_read()
	registry = _resolve_table_registry(table_id)
	names = [tool.name for tool in _tools_for(registry.doctype_name)]
	if not names:
		return []
	calls = frappe.get_all(
		"Agent Tool Call",
		filters={"tool": ["in", names]},
		fields=["agent_run", "tool", "status", "creation"],
		order_by="creation desc",
		limit_page_length=min(int(limit), 100),
	)
	runs = [c.agent_run for c in calls if c.agent_run]
	agent_of = dict(
		frappe.get_all("Agent Run", filters={"name": ["in", runs]}, fields=["name", "agent"], as_list=True)
	) if runs else {}
	return [
		{"agent": agent_of.get(c.agent_run), "tool": c.tool, "status": c.status, "timestamp": c.creation}
		for c in calls
	]
