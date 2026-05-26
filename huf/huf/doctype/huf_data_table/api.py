import json

import frappe

from .validators import (
	LAYOUT_FIELD_TYPES,
	get_search_fields,
	resolve_autoname,
	validate_and_prepare_fields,
)


@frappe.whitelist()
def create_data_table(
	table_name: str,
	fields: str | list[dict],
	description: str = "",
	icon: str = "",
	autoname_method: str = "Autoincrement",
	title_field: str = "",
) -> dict:
	"""Create a new data table (DocType + registry entry)."""
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
	dt.insert(ignore_permissions=True)

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
	registry.insert(ignore_permissions=True)

	frappe.db.commit()

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
	"""Update table structure (add/remove/reorder fields, update metadata)."""
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
		dt.save(ignore_permissions=True)

		registry.field_count = len(
			[f for f in validated_fields if f["fieldtype"] not in LAYOUT_FIELD_TYPES]
		)

	if description is not None:
		registry.description = description
	if icon is not None:
		registry.icon = icon

	registry.save(ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"name": registry.name}}


@frappe.whitelist()
def delete_data_table(name: str) -> dict:
	"""Delete a data table and all its records."""
	registry = frappe.get_doc("Huf Data Table", name)
	doctype_name = registry.doctype_name

	record_count = 0
	try:
		record_count = frappe.db.count(doctype_name)
	except Exception:
		pass

	if frappe.db.exists("DocType", doctype_name):
		frappe.delete_doc("DocType", doctype_name, force=True, ignore_permissions=True)

	frappe.delete_doc("Huf Data Table", name, ignore_permissions=True)
	frappe.db.commit()

	return {"success": True, "data": {"deleted_records": record_count}}


@frappe.whitelist()
def get_table_record_counts(names: str | list[str]) -> dict:
	"""Get live record counts for a list of Huf data tables (by registry name).

	Standard REST can't count records across dynamic DocTypes,
	so this helper exists for the listing page enrichment.
	"""
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
	"""Get complete table schema (fields with all properties)."""
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
