"""
Document CRUD handler functions for Huf Agent tools.

These handlers are invoked by the SDK tool system (via sdk_tools.py)
and the Flow Engine (via flow_tool_executor.py). They wrap low-level
Frappe database operations with permission checks, validation, and
consistent error handling.
"""

import json
from datetime import date, datetime, time

import frappe

from huf.ai.tool_functions import (
	attach_file_to_document,
	cancel_document,
	create_documents,
	delete_documents,
	get_documents,
	get_report_result,
	get_value,
	set_value,
	submit_document,
	update_documents,
)


def _sanitize_for_doctype(doctype: str, data: dict) -> dict:
	"""Keep only valid fields for doctype and sanitize child tables."""
	try:
		meta = frappe.get_meta(doctype)
		valid_fields = {df.fieldname for df in meta.fields}
		cleaned = {}

		for key, value in (data or {}).items():
			if key not in valid_fields:
				continue

			df = meta.get_field(key)
			if df.fieldtype == "Table":
				if isinstance(value, list):
					cleaned[key] = [
						_sanitize_for_doctype(df.options, row) for row in value if isinstance(row, dict)
					]
			else:
				cleaned[key] = value

		return cleaned
	except Exception:
		return data or {}


def handle_create_document(reference_doctype=None, ignore_permissions=False, **kwargs):
	"""
	Create a new document.

	Args:
		reference_doctype (str): DocType of the document
		ignore_permissions (bool): Bypass permission checks (used for allowed Guest tools)
		**kwargs: Fields of the document

	Returns:
		dict: Created document data
	"""
	try:
		if not reference_doctype:
			return {"success": False, "error": "No reference doctype provided."}

		if not frappe.db.exists("DocType", reference_doctype):
			return {"success": False, "error": f"DocType '{reference_doctype}' does not exist."}

		if not ignore_permissions and not frappe.has_permission(reference_doctype, "create"):
			return {
				"success": False,
				"error": f"You do not have permission to create {reference_doctype}",
				"permission_denied": True,
			}

		# Support both flat kwargs and a "doc" wrapper {"doc": {"field": "value"}}
		if "doc" in kwargs and isinstance(kwargs["doc"], dict):
			doc_fields = kwargs.pop("doc")
			kwargs.update(doc_fields)

		doc = frappe.get_doc({"doctype": reference_doctype, **kwargs})
		doc.insert(ignore_permissions=ignore_permissions)

		doc_dict = doc.as_dict()
		for k, v in doc_dict.items():
			if isinstance(v, (datetime, date, time)):
				doc_dict[k] = str(v)

		return {"success": True, "result": doc_dict, "message": f"{reference_doctype} created"}
	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_create_document: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_delete_document(document_id=None, reference_doctype=None, ignore_permissions=False, **kwargs):
	"""
	Delete a document.

	Args:
		document_id (str): ID of the document
		reference_doctype (str): DocType of the document
		ignore_permissions (bool): Bypass permission checks

	Returns:
		dict: Deletion result
	"""
	try:
		if not reference_doctype:
			reference_doctype = frappe.flags.get("current_function_doctype")

		if not reference_doctype:
			return {"success": False, "error": "No reference doctype provided."}

		if not frappe.db.exists(reference_doctype, document_id):
			return {
				"success": False,
				"error": f"Document {document_id} not found in {reference_doctype}",
			}

		# Pre-check delete permission
		if not ignore_permissions and not frappe.has_permission(
			reference_doctype, "delete", doc=document_id
		):
			return {
				"success": False,
				"error": f"You do not have delete permission on {reference_doctype} {document_id}",
				"permission_denied": True,
			}

		frappe.delete_doc(reference_doctype, document_id, ignore_permissions=ignore_permissions)

		return {"success": True, "message": f"{reference_doctype} {document_id} deleted"}
	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_delete_document: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_get_list(
	filters=None, fields=None, limit=0, order_by="modified desc", reference_doctype=None, **kwargs
):
	"""
	Get a list of documents from a doctype.

	Args:
		filters (dict): Filters to apply
		fields (list): Fields to include in the result
		limit (int): Maximum number of documents to return
		order_by (str): Order by clause
		reference_doctype (str): DocType to get list from

	Returns:
		dict: List of documents with metadata
	"""
	try:
		if not reference_doctype:
			reference_doctype = frappe.flags.get("current_function_doctype")

		if not reference_doctype:
			return {
				"success": False,
				"error": "No reference doctype provided. Please specify a valid DocType.",
			}

		if not frappe.db.exists("DocType", reference_doctype):
			return {"success": False, "error": f"DocType '{reference_doctype}' does not exist."}

		meta = frappe.get_meta(reference_doctype)
		valid_fields = ["name", "creation", "modified", "modified_by", "owner", "docstatus"]
		for df in meta.fields:
			valid_fields.append(df.fieldname)

		if not fields:
			fields = ["name", "modified"]

		filtered_fields = []
		invalid_fields = []
		for field in fields:
			if field in valid_fields:
				filtered_fields.append(field)
			else:
				invalid_fields.append(field)

		if invalid_fields:
			warning = (
				f"Fields {', '.join(invalid_fields)} do not exist in "
				f"DocType '{reference_doctype}' and were ignored."
			)
			if not filtered_fields:
				filtered_fields = ["name", "modified"]
		else:
			warning = None

		if filters and isinstance(filters, dict):
			cleaned_filters = {}
			invalid_filter_fields = []

			for key, value in filters.items():
				base_field = key.split()[0] if " " in key else key
				if base_field in valid_fields:
					cleaned_filters[key] = value
				else:
					invalid_filter_fields.append(base_field)

			if invalid_filter_fields:
				filters = cleaned_filters
				filter_warning = (
					f"Filter fields {', '.join(invalid_filter_fields)} do not exist in "
					f"DocType '{reference_doctype}' and were ignored."
				)
				warning = f"{warning}\n{filter_warning}" if warning else filter_warning

		page_length = limit if limit and int(limit) > 0 else None

		result = frappe.get_all(
			reference_doctype,
			filters=filters,
			fields=filtered_fields,
			limit_page_length=page_length,
			order_by=order_by,
		)

		for item in result:
			for key, value in item.items():
				if isinstance(value, (datetime, date, time)):
					item[key] = str(value)

		response = {"success": True, "result": result}

		if warning:
			response["warning"] = warning

		response["valid_fields"] = valid_fields[:20]
		if len(valid_fields) > 20:
			response["valid_fields_note"] = f"Showing first 20 of {len(valid_fields)} available fields"

		return response
	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_get_list: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_update_document(
	document_id=None, data=None, reference_doctype=None, ignore_permissions=False, **kwargs
):
	"""Update a document in the database."""
	if data is None:
		data = {}
		for key, value in kwargs.items():
			if key not in ["document_id", "reference_doctype", "ignore_permissions"]:
				data[key] = value

	if not reference_doctype:
		reference_doctype = frappe.flags.get("current_function_doctype")

	if not reference_doctype:
		return {"success": False, "error": "No reference doctype provided."}

	if not frappe.db.exists(reference_doctype, document_id):
		return {"success": False, "error": f"{reference_doctype} {document_id} not found"}

	if not ignore_permissions and not frappe.has_permission(
		reference_doctype, "write", doc=document_id
	):
		return {
			"success": False,
			"error": f"You do not have write permission on {reference_doctype} {document_id}",
			"permission_denied": True,
		}

	try:
		doc = frappe.get_doc(reference_doctype, document_id)

		for field, value in data.items():
			doc.set(field, value)

		doc.save(ignore_permissions=ignore_permissions)
		frappe.db.commit()

		return {
			"success": True,
			"result": doc.as_dict(),
			"message": f"{reference_doctype} {document_id} updated successfully.",
		}
	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_update_document: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_get_document(document_id=None, reference_doctype=None, **filters):
	"""
	Enhanced Get Document handler.
	Allows fetching by any field (like email, mobile_no, etc.) instead of only document_id.
	"""
	try:
		if not reference_doctype:
			reference_doctype = frappe.flags.get("current_function_doctype")

		if not reference_doctype:
			return {"success": False, "error": "No reference doctype provided."}

		if not frappe.db.exists("DocType", reference_doctype):
			return {"success": False, "error": f"DocType '{reference_doctype}' does not exist."}

		if document_id:
			if not frappe.db.exists(reference_doctype, document_id):
				return {
					"success": False,
					"error": f"Document '{document_id}' not found in '{reference_doctype}'",
				}
			doc_name = document_id
		else:
			valid_fields = [f.fieldname for f in frappe.get_meta(reference_doctype).fields]
			applied_filters = {k: v for k, v in filters.items() if k in valid_fields and v}

			if not applied_filters:
				return {
					"success": False,
					"error": "No valid filter fields provided to find the document.",
				}

			doc_name = frappe.db.get_value(reference_doctype, applied_filters, "name")
			if not doc_name:
				return {
					"success": False,
					"error": f"No {reference_doctype} found matching filters {applied_filters}",
				}

		doc = frappe.get_doc(reference_doctype, doc_name)
		doc.check_permission()
		doc.apply_fieldlevel_read_permissions()

		return {
			"success": True,
			"result": doc.as_dict(),
			"message": f"{reference_doctype} '{doc_name}' fetched successfully",
		}

	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_get_document: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_get_documents(reference_doctype: str, document_ids: list, **kwargs):
	"""
	Get multiple documents by id.

	This backs the "Get Multiple Documents" tool type.
	"""
	try:
		if not reference_doctype:
			reference_doctype = frappe.flags.get("current_function_doctype")

		if not reference_doctype:
			return {"success": False, "error": "No reference doctype provided."}

		if not isinstance(document_ids, list) or not document_ids:
			return {"success": False, "error": "document_ids must be a non-empty list"}

		docs = get_documents(reference_doctype, document_ids)
		return {"success": True, "result": docs, "count": len(docs)}
	except Exception as e:
		frappe.log_error(title="SDK Functions Debug", message=f"Error in handle_get_documents: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_create_documents(reference_doctype: str, documents: list = None, data: list = None, **kwargs):
	"""
	Create multiple documents.
	Accepts either 'documents' or 'data' depending on schema auto-generation.
	"""
	docs = documents or data or []
	sanitized = [_sanitize_for_doctype(reference_doctype, d) for d in docs if isinstance(d, dict)]
	return create_documents(reference_doctype, sanitized)


def handle_update_documents(reference_doctype: str, documents: list = None, data: list = None, **kwargs):
	"""Update multiple documents."""
	docs = documents or data or []
	sanitized = []
	for d in docs:
		if not isinstance(d, dict):
			continue
		d = dict(d)
		doc_id = d.get("document_id") or d.get("name")
		if not doc_id:
			continue
		fields = {k: v for k, v in d.items() if k not in ("document_id", "name")}
		fields = _sanitize_for_doctype(reference_doctype, fields)
		sanitized.append({"document_id": doc_id, **fields})
	return update_documents(reference_doctype, sanitized)


def handle_delete_documents(reference_doctype: str, document_ids: list, **kwargs):
	"""Delete multiple documents."""
	return delete_documents(reference_doctype, document_ids or [])


def handle_submit_document(
	reference_doctype: str = None, document_id: str = None, ignore_permissions=False, **kwargs
):
	"""Submit a document."""
	if not reference_doctype:
		reference_doctype = frappe.flags.get("current_function_doctype")
	if not reference_doctype:
		return {"success": False, "error": "No reference doctype provided."}
	if not document_id:
		return {"success": False, "error": "document_id is required"}

	if not ignore_permissions and not frappe.has_permission(
		reference_doctype, "submit", doc=document_id
	):
		return {"success": False, "error": "No permission to submit"}

	doc = frappe.get_doc(reference_doctype, document_id)
	doc.submit()
	return {"success": True, "message": "Submitted"}


def handle_cancel_document(
	reference_doctype: str = None, document_id: str = None, ignore_permissions=False, **kwargs
):
	"""Cancel a document."""
	if not reference_doctype:
		reference_doctype = frappe.flags.get("current_function_doctype")
	if not reference_doctype:
		return {"success": False, "error": "No reference doctype provided."}
	if not document_id:
		return {"success": False, "error": "document_id is required"}

	if not ignore_permissions and not frappe.has_permission(
		reference_doctype, "cancel", doc=document_id
	):
		return {"success": False, "error": "No permission to cancel"}

	doc = frappe.get_doc(reference_doctype, document_id)
	doc.cancel()
	return {"success": True, "message": "Cancelled"}


def handle_get_value(doctype: str = None, filters: dict = None, fieldname=None, **kwargs):
	"""
	Get a field value (or multiple values) from a DocType.
	Matches the auto-generated JSON schema: doctype + filters + fieldname.
	"""
	if not doctype or not filters or not fieldname:
		return {
			"success": False,
			"error": "Missing required parameters: doctype, filters, fieldname",
		}

	try:
		value = frappe.db.get_value(doctype, filters, fieldname)
		return {
			"success": True,
			"doctype": doctype,
			"filters": filters,
			"fieldname": fieldname,
			"value": value,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}


def handle_set_value(
	doctype: str = None, filters: dict = None, fieldname: str = None, value=None, **kwargs
):
	"""Set a field value on a document that matches filters."""
	if not doctype or not filters or not fieldname:
		return {"success": False, "error": "Missing required parameters"}

	try:
		doc_name = frappe.db.get_value(doctype, filters, "name")
		if not doc_name:
			return {
				"success": False,
				"error": f"No {doctype} found matching filters {filters}",
			}

		updated = frappe.db.set_value(doctype, doc_name, fieldname, value)
		frappe.db.commit()

		return {
			"success": True,
			"doctype": doctype,
			"name": doc_name,
			"fieldname": fieldname,
			"new_value": updated[fieldname] if isinstance(updated, dict) else value,
		}

	except Exception as e:
		frappe.log_error(title="handle_set_value failed", message=frappe.get_traceback())
		return {"success": False, "error": str(e)}


def handle_get_report_result(
	report_name: str, filters: dict | None = None, limit: int | None = None, **kwargs
):
	"""Get report results."""
	return get_report_result(report_name, filters=filters, limit=limit, user=frappe.session.user)


def handle_attach_file_to_document(reference_doctype, document_id, **kwargs):
	"""SDK handler that wraps attach_file_to_document."""
	if not reference_doctype or not document_id:
		return {
			"success": False,
			"error": "reference_doctype and document_id are required",
		}

	normalized_kwargs = {}
	for k, v in (kwargs or {}).items():
		if k in ["file_path", "file_url"]:
			normalized_kwargs[k] = v
			continue

		if isinstance(v, str):
			normalized_kwargs[k] = v

	try:
		result = attach_file_to_document(
			reference_doctype,
			document_id,
			**normalized_kwargs,
		)
		return {"success": True, "result": result}
	except Exception as e:
		frappe.log_error(title="handle_attach_file_to_document: failed", message=frappe.get_traceback())
		return {"success": False, "error": str(e)}
