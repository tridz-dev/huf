import json
import re

import frappe
from frappe import _
from frappe.model import display_fieldtypes, no_value_fields, table_fields

from huf.permissions import (
	DEFAULT_ROLE_CAPABILITIES,
	HUF_ROLE_FRAPPE_ROLE_MAP,
	SYSTEM_MANAGER,
	has_capability,
)

from .permissions import sync_data_table_permissions
from .validators import (
	LAYOUT_FIELD_TYPES,
	get_search_fields,
	resolve_autoname,
	validate_and_prepare_fields,
)

_MANAGE_CAPABILITY = "data.tables.manage"
_VIEW_CAPABILITIES = {
	"data.tables.manage",
	"data.records.view_own",
	"data.records.view_all",
}
_WRITE_CAPABILITIES = {
	"data.tables.manage",
	"data.records.create",
	"data.records.edit_own",
	"data.records.edit_all",
}


def _has_any_capability(capabilities: set[str]) -> bool:
	return any(has_capability(frappe.session.user, capability) for capability in capabilities)


def _require_data_manage():
	"""Throw if the current user cannot manage data tables."""
	if not has_capability(frappe.session.user, _MANAGE_CAPABILITY):
		frappe.throw(
			_("You don't have permission to manage data tables."),
			frappe.PermissionError,
		)


def _require_data_view():
	if not _has_any_capability(_VIEW_CAPABILITIES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_write():
	_require_data_manage()


def _require_read():
	_require_data_view()


def _import_permitted_roles() -> list[str]:
	"""Frappe roles allowed to import into generated HF DocTypes.

	Mirrors the HUF capability gate: every default Huf role holding the
	write capability maps to a backing Frappe role that receives an
	import-enabled DocPerm on generated tables.
	"""
	roles = {SYSTEM_MANAGER}
	for huf_role, capabilities in DEFAULT_ROLE_CAPABILITIES.items():
		if _WRITE_CAPABILITIES.intersection(capabilities):
			frappe_role = HUF_ROLE_FRAPPE_ROLE_MAP.get(huf_role)
			if frappe_role:
				roles.add(frappe_role)
	return [r for r in sorted(roles) if r == SYSTEM_MANAGER or frappe.db.exists("Role", r)]


def _table_permission_row(role: str) -> dict:
	return {
		"role": role,
		"read": 1,
		"write": 1,
		"create": 1,
		"delete": 1,
		"print": 1,
		"email": 1,
		"share": 1,
		"import": 1,
	}


def _ensure_import_enabled(doctype_name: str) -> None:
	"""Retrofit allow_import + import DocPerm onto a generated HF DocType.

	Tables created before bulk-import support lack these flags, and
	Frappe's Data Import validates against them.
	"""
	dt = frappe.get_doc("DocType", doctype_name)
	changed = False
	if not dt.allow_import:
		dt.allow_import = 1
		changed = True

	existing = {p.role: p for p in dt.permissions}
	for role in _import_permitted_roles():
		perm = existing.get(role)
		if perm is None:
			dt.append("permissions", _table_permission_row(role))
			changed = True
		elif not perm.get("import"):
			perm.set("import", 1)
			changed = True

	if changed:
		dt.save(ignore_permissions=True)


@frappe.whitelist()
def create_data_table(
	table_name: str,
	fields: str | list[dict],
	description: str = "",
	table_group: str = "",
	icon: str = "",
	autoname_method: str = "Autoincrement",
	title_field: str = "",
) -> dict:
	"""Create a new data table (DocType + registry entry).

	Requires: data.tables.manage
	"""
	_require_data_manage()

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
			"allow_import": 1,
		}
	)
	dt.set(
		"permissions",
		[_table_permission_row(role) for role in _import_permitted_roles()],
	)
	dt.insert()

	data_field_count = len([f for f in validated_fields if f["fieldtype"] not in LAYOUT_FIELD_TYPES])

	registry = frappe.new_doc("Huf Data Table")
	registry.update(
		{
			"table_name": table_name,
			"doctype_name": doctype_name,
			"description": description,
			"table_group": table_group,
			"icon": icon,
			"field_count": data_field_count,
			"autoname_method": autoname_method,
			"title_field_name": title_field,
		}
	)
	registry.insert(ignore_permissions=True)

	# Sync permissions so all roles with data.* capabilities get access
	# to this new table immediately.
	sync_data_table_permissions()

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
	table_group: str | None = None,
	icon: str | None = None,
) -> dict:
	"""Update table structure (add/remove/reorder fields, update metadata).

	Requires: data.tables.manage
	"""
	_require_data_manage()

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
	if table_group is not None:
		registry.table_group = table_group
	if icon is not None:
		registry.icon = icon

	registry.save()

	return {"success": True, "data": {"name": registry.name}}


@frappe.whitelist()
def delete_data_table(name: str) -> dict:
	"""Delete a data table and all its records.

	Requires: data.tables.manage
	"""
	_require_data_manage()

	registry = frappe.get_doc("Huf Data Table", name)
	doctype_name = registry.doctype_name

	record_count = 0
	try:
		record_count = frappe.db.count(doctype_name)
	except (frappe.DoesNotExistError, frappe.DataError):
		record_count = 0

	if frappe.db.exists("DocType", doctype_name):
		frappe.delete_doc("DocType", doctype_name, force=True)

	frappe.delete_doc("Huf Data Table", name)

	return {"success": True, "data": {"deleted_records": record_count}}


@frappe.whitelist()
def get_table_record_counts(names: str | list[str]) -> dict:
	"""Get live record counts for a list of Huf data tables (by registry name).

	Standard REST can't count records across dynamic DocTypes,
	so this helper exists for the listing page enrichment.

	Requires: data records view capability.
	"""
	_require_read()
	if isinstance(names, str):
		names = json.loads(names)

	counts = {}
	for name in names:
		try:
			registry = frappe.get_doc("Huf Data Table", name)
			counts[name] = frappe.db.count(registry.doctype_name)
		except (frappe.DoesNotExistError, frappe.DataError):
			counts[name] = 0

	return counts


@frappe.whitelist()
def get_table_schema(name: str) -> dict:
	"""Get complete table schema (fields with all properties).

	Requires: data records view capability.
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
		"table_group": registry.table_group,
		"icon": registry.icon,
		"autoname_method": registry.autoname_method,
		"title_field_name": registry.title_field_name,
		"fields": fields,
	}


@frappe.whitelist()
def get_bulk_import_template_url(table_id: str, export_records: bool | str = False) -> dict:
	"""Generate a CSV import template for a Huf data table and return its download URL.

	Uses Frappe's Data Import exporter. The template is stored as a private
	File so the SPA can download it through the authenticated file route.

	Requires: data records view capability for blank templates, data.tables.manage for exports.
	"""
	export_data = bool(frappe.parse_json(export_records))
	if export_data:
		_require_write()
	else:
		_require_read()

	registry = frappe.get_doc("Huf Data Table", table_id)
	doctype_name = registry.doctype_name
	meta = frappe.get_meta(doctype_name)

	fieldnames = ["name"] + [
		f.fieldname
		for f in meta.fields
		if f.fieldtype not in (display_fieldtypes + no_value_fields + table_fields)
	]

	# Imported lazily: pulls in xlsx/openpyxl chains not needed elsewhere.
	from frappe.core.doctype.data_import.exporter import Exporter
	from frappe.utils.csvutils import to_csv

	exporter = Exporter(
		doctype_name,
		export_fields={doctype_name: fieldnames},
		export_data=export_data,
		file_type="CSV",
	)
	csv_content = to_csv(exporter.get_csv_array_for_export())

	file_name = f"{registry.table_name}-import-template.csv"
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": csv_content,
			"is_private": 1,
		}
	)
	file_doc.insert(ignore_permissions=True)

	return {
		"success": True,
		"data": {
			"file_url": file_doc.file_url,
			"file_name": file_doc.file_name,
		},
	}


@frappe.whitelist()
def start_table_bulk_import(table_id: str, file_url: str) -> dict:
	"""Create a Frappe Data Import for a Huf data table and enqueue the import.

	Equivalent to Frappe's `form_start_import`, but gated on the HUF
	`data.tables.manage` capability instead of Data Import DocType DocPerms.

	Requires: data.tables.manage
	"""
	_require_write()

	registry = frappe.get_doc("Huf Data Table", table_id)
	doctype_name = registry.doctype_name

	if not frappe.db.exists("File", {"file_url": file_url}):
		frappe.throw(_("Import file not found: {0}").format(file_url))

	# Older tables predate allow_import; retrofit before Data Import validates.
	_ensure_import_enabled(doctype_name)

	data_import = frappe.get_doc(
		{
			"doctype": "Data Import",
			"reference_doctype": doctype_name,
			"import_type": "Insert New Records",
			"import_file": file_url,
			"mute_emails": 1,
		}
	)
	# Bypass Data Import DocType DocPerms (System Manager only); the HUF
	# capability gate above is the authorization boundary. Validation of the
	# target DocType's allow_import/import DocPerm still runs in validate().
	data_import.insert(ignore_permissions=True)

	enqueued = data_import.start_import()

	return {
		"success": True,
		"data": {
			"import_name": data_import.name,
			"status": data_import.status,
			"enqueued": bool(enqueued),
		},
	}


@frappe.whitelist()
def get_table_bulk_import_status(import_name: str) -> dict:
	"""Get status and error details for a Data Import against a Huf data table.

	Requires: data records view capability.
	"""
	_require_read()

	data_import = frappe.get_doc("Data Import", import_name)
	if not frappe.db.exists("Huf Data Table", {"doctype_name": data_import.reference_doctype}):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	log_counts = frappe.get_all(
		"Data Import Log",
		fields=[{"COUNT": "*", "as": "count"}, "success"],
		filters={"data_import": import_name},
		group_by="success",
	)

	success_count = 0
	failed_count = 0
	for log in log_counts:
		if log.get("success"):
			success_count = log.get("count")
		else:
			failed_count = log.get("count")

	error_logs = frappe.get_all(
		"Data Import Log",
		fields=["row_indexes", "messages", "exception"],
		filters={"data_import": import_name, "success": 0},
		order_by="log_index",
		limit_page_length=50,
	)

	return {
		"success": True,
		"data": {
			"import_name": import_name,
			"status": data_import.status,
			"success": success_count,
			"failed": failed_count,
			"total": data_import.payload_count,
			"errors": [
				{
					"row_indexes": log.row_indexes,
					"messages": log.messages,
					"exception": log.exception,
				}
				for log in error_logs
			],
		},
	}


@frappe.whitelist()
def get_table_records(
	doctype_name: str,
	fields: str | list[str] = '*',
	filters: str | list | None = None,
	search: str | None = None,
	limit: int = 20,
	start: int = 0,
	order_by: str = 'modified desc',
) -> dict:
	"""Get records for a table with optional search across configured fields."""
	_require_read()

	if isinstance(fields, str):
		try:
			fields = json.loads(fields)
		except ValueError:
			fields = [fields]
	if isinstance(filters, str) and filters:
		filters = json.loads(filters)

	or_filters = []
	if search and search.strip():
		search_text = search.strip()
		meta = frappe.get_meta(doctype_name)
		if meta.search_fields:
			for fieldname in meta.search_fields.split(','):
				or_filters.append([fieldname.strip(), 'like', f'%{search_text}%'])
		name_field = meta.title_field or 'name'
		if name_field not in (meta.search_fields or ''):
			or_filters.append([name_field, 'like', f'%{search_text}%'])

	records = frappe.get_list(
		doctype_name,
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		limit_page_length=limit + 1,
		limit_start=start,
		order_by=order_by,
	)
	has_more = len(records) > limit
	if has_more:
		records = records[:limit]
	return {'items': records, 'hasMore': has_more}


# Agent access scaffolding: one deterministic tool set per Huf Data Table.
TABLE_ACTION_MAP = {
	'view': (('Get List', 'read'), ('Get Document', 'read')),
	'create': (('Create Document', 'create'),),
	'edit': (('Update Document', 'write'),),
	'delete': (('Delete Document', 'delete'),),
}
_TYPES_TO_ACTION = {types: action for action, specs in TABLE_ACTION_MAP.items() for types, _ in specs}
_TABLE_TOOL_TYPE = 'Data Table'
_PARAM_TOOL_TYPES = {'Get List', 'Create Document', 'Update Document'}
_FIELD_TYPE_TO_PARAM_TYPE = {
	'Data': 'string', 'Text': 'string', 'Small Text': 'string', 'Long Text': 'string',
	'Int': 'integer', 'Float': 'number', 'Currency': 'number', 'Percent': 'number',
	'Check': 'boolean', 'Date': 'string', 'Datetime': 'string', 'Time': 'string',
	'Link': 'string', 'Select': 'string', 'Phone': 'string',
}
_PARAM_EXCLUDED_FIELD_TYPES = {'Section Break', 'Column Break', 'Tab Break', 'HTML', 'Heading'}
_TOOL_DESCRIPTIONS = {
	'Get List': 'List records from {label} with optional filters',
	'Get Document': 'Get a single {label} record by ID',
	'Create Document': 'Create a new {label} record',
	'Update Document': 'Update an existing {label} record',
	'Delete Document': 'Delete a {label} record',
}


def _resolve_table_registry(table: str):
	if frappe.db.exists('Huf Data Table', table):
		return frappe.get_doc('Huf Data Table', table)
	name = frappe.db.get_value('Huf Data Table', {'table_name': table}, 'name')
	if name:
		return frappe.get_doc('Huf Data Table', name)
	frappe.throw(_('Unknown data table: {0}').format(table))


def _table_tool_name(doctype_name: str, types: str) -> str:
	return re.sub(r'[^a-zA-Z0-9_-]', '_', f'{doctype_name} - {types}')


def _ensure_table_tool_type() -> str:
	if not frappe.db.exists('Agent Tool Type', _TABLE_TOOL_TYPE):
		frappe.get_doc({'doctype': 'Agent Tool Type', 'name1': _TABLE_TOOL_TYPE}).insert()
	return _TABLE_TOOL_TYPE


def _table_field_params(doctype_name: str, types: str) -> list[dict]:
	rows = []
	for field in frappe.get_meta(doctype_name).fields:
		if field.fieldtype in _PARAM_EXCLUDED_FIELD_TYPES or field.hidden or field.read_only:
			continue
		rows.append({
			'label': field.label or field.fieldname,
			'fieldname': field.fieldname,
			'type': _FIELD_TYPE_TO_PARAM_TYPE.get(field.fieldtype, 'string'),
			'required': 1 if types == 'Create Document' and field.reqd else 0,
			'description': field.description or '',
			'options': field.options if field.fieldtype == 'Select' and field.options else '',
		})
	return rows


def _sync_tool_params(tool_name: str, doctype_name: str, types: str) -> None:
	if types not in _PARAM_TOOL_TYPES:
		return
	tool = frappe.get_doc('Agent Tool Function', tool_name)
	desired = _table_field_params(doctype_name, types)
	current = [
		{'label': row.label or '', 'fieldname': row.fieldname or '', 'type': row.type or '',
		 'required': 1 if row.required else 0, 'description': row.description or '', 'options': row.options or ''}
		for row in tool.parameters
	]
	if current != desired:
		tool.set('parameters', desired)
		tool.save()


def _scaffold_tool(doctype_name: str, table_label: str, types: str, permission: str) -> str:
	tool_name = _table_tool_name(doctype_name, types)
	if frappe.db.exists('Agent Tool Function', tool_name):
		_sync_tool_params(tool_name, doctype_name, types)
		return tool_name
	doc = {
		'doctype': 'Agent Tool Function',
		'tool_name': tool_name,
		'description': _TOOL_DESCRIPTIONS[types].format(label=table_label),
		'types': types,
		'reference_doctype': doctype_name,
		'required_permission': permission,
		'tool_type': _ensure_table_tool_type(),
	}
	if types in _PARAM_TOOL_TYPES:
		doc['parameters'] = _table_field_params(doctype_name, types)
	frappe.get_doc(doc).insert()
	return tool_name


def _compute_access(doctype_name: str, agent: str | None = None) -> list[dict]:
	tools = frappe.get_all(
		'Agent Tool Function',
		filters={'reference_doctype': doctype_name, 'types': ['in', list(_TYPES_TO_ACTION)]},
		fields=['name', 'types'],
	)
	if not tools:
		return []
	tool_types = {tool.name: tool.types for tool in tools}
	filters = {'parenttype': 'Agent', 'tool': ['in', list(tool_types)]}
	if agent:
		filters['parent'] = agent
	by_agent = {}
	for link in frappe.get_all('Agent Tool', filters=filters, fields=['parent', 'tool']):
		entry = by_agent.setdefault(link.parent, {'actions': set(), 'tools': []})
		entry['tools'].append(link.tool)
		action = _TYPES_TO_ACTION.get(tool_types.get(link.tool))
		if action:
			entry['actions'].add(action)
	return [
		{
			'agent': name,
			'agent_name': frappe.db.get_value('Agent', name, 'agent_name') or name,
			'actions': [action for action in TABLE_ACTION_MAP if action in entry['actions']],
			'tools': sorted(entry['tools']),
		}
		for name, entry in sorted(by_agent.items())
	]


@frappe.whitelist()
def get_table_agent_access(table: str) -> list:
	_require_read()
	return _compute_access(_resolve_table_registry(table).doctype_name)


@frappe.whitelist()
def get_tables_agent_counts() -> dict:
	_require_read()
	counts = {}
	for registry in frappe.get_all('Huf Data Table', fields=['doctype_name']):
		agents = {entry['agent'] for entry in _compute_access(registry.doctype_name)}
		if agents:
			counts[registry.doctype_name] = len(agents)
	return counts


@frappe.whitelist()
def set_table_agent_access(table: str, agent: str, actions: str | list) -> dict:
	_require_write()
	if isinstance(actions, str):
		actions = json.loads(actions)
	actions = [str(action).strip().lower() for action in actions]
	unknown = [action for action in actions if action not in TABLE_ACTION_MAP]
	if unknown:
		frappe.throw(_('Unknown action(s): {0}').format(', '.join(unknown)))
	registry = _resolve_table_registry(table)
	agent_doc = frappe.get_doc('Agent', agent)
	wanted = {
		_scaffold_tool(registry.doctype_name, registry.table_name, types, permission)
		for action in actions
		for types, permission in TABLE_ACTION_MAP[action]
	}
	changed = False
	existing = {row.tool for row in agent_doc.agent_tool}
	for tool_name in sorted(wanted - existing):
		agent_doc.append('agent_tool', {'tool': tool_name})
		changed = True
	attached = [row.tool for row in agent_doc.agent_tool]
	attached_meta = {
		tool.name: tool
		for tool in frappe.get_all(
			'Agent Tool Function',
			filters={'name': ['in', attached], 'reference_doctype': registry.doctype_name},
			fields=['name', 'types'],
		)
	}
	detach = {
		name for name, tool in attached_meta.items()
		if _TYPES_TO_ACTION.get(tool.types) and _TYPES_TO_ACTION[tool.types] not in actions
	}
	if detach:
		agent_doc.agent_tool = [row for row in agent_doc.agent_tool if row.tool not in detach]
		changed = True
	if changed:
		agent_doc.save()
	for entry in _compute_access(registry.doctype_name, agent=agent_doc.name):
		return entry
	return {'agent': agent_doc.name, 'agent_name': agent_doc.agent_name, 'actions': [], 'tools': []}


@frappe.whitelist()
def apply_data_permissions() -> dict:
	"""
	Rebuild DocType permissions for all data tables.

	Called by the Huf Role on_update hook whenever role capabilities change.
	"""
	_require_data_manage()
	sync_data_table_permissions()
	return {"success": True}
