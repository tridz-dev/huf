import inspect
import json
from typing import Callable

import frappe
from frappe import client
from frappe import _

from huf.ai.tool_functions import (
    get_documents,
    create_documents,
    update_documents,
    delete_documents,
    submit_document,
    cancel_document,
    get_value,
    set_value,
    get_report_result,
    attach_file_to_document,
)
from huf.ai.transaction import commit_if_background

logger = frappe.logger("huf")


def wrap_frappe_function(func: Callable) -> Callable:
    """
    Wrap a Frappe function to handle exceptions

    Args:
        func: Function to wrap

    Returns:
        Callable: Wrapped function
    """

    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)

            if hasattr(result, "as_dict") and callable(getattr(result, "as_dict", None)):
                result = result.as_dict()

            elif isinstance(result, list) and result:
                result = [item.as_dict() if callable(getattr(item, "as_dict", None)) else item for item in result]

            return {"success": True, "result": result}
        except Exception as e:
            logger.warning(f"Wrapped function {func.__name__} failed: {e!s}\n{frappe.get_traceback()}")
            return {"success": False, "error": str(e)}

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__signature__ = inspect.signature(func)

    return wrapper


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
                        _sanitize_for_doctype(df.options, row)
                        for row in value
                        if isinstance(row, dict)
                    ]
            else:
                cleaned[key] = value

        return cleaned
    except (frappe.DoesNotExistError, frappe.ValidationError, frappe.PermissionError, ValueError, KeyError, TypeError):
        # Defensive fallback: if meta lookup fails, return original data unchanged.
        return data or {}


# Standard CRUD function generators
def create_get_function(doctype: str) -> Callable:
    """
    Create a get function for a doctype

    Args:
        doctype: DocType name

    Returns:
        Callable: Function to get a document
    """

    def get_doc(name: str, **kwargs):
        """
        Get a document

        Args:
            name: Name of the document

        Returns:
            dict: Document data
        """
        doc = client.get(doctype, name)
        return doc

    get_doc.__name__ = f"get_{doctype.lower().replace(' ', '_')}"
    get_doc.__doc__ = f"Get a {doctype} document"

    return wrap_frappe_function(get_doc)


def create_create_function(doctype: str) -> Callable:
    """
    Create a function to create a document

    Args:
        doctype: DocType name

    Returns:
        Callable: Function to create a document
    """

    def create_doc(**kwargs):
        """
        Create a document

        Args:
            **kwargs: Document fields

        Returns:
            dict: Created document
        """
        doc = frappe.get_doc({"doctype": doctype, **kwargs})
        doc.insert()
        return doc

    create_doc.__name__ = f"create_{doctype.lower().replace(' ', '_')}"
    create_doc.__doc__ = f"Create a {doctype} document"

    return wrap_frappe_function(create_doc)


def create_update_function(doctype: str) -> Callable:
    """
    Create a function to update a document

    Args:
        doctype: DocType name

    Returns:
        Callable: Function to update a document
    """

    def update_doc(name: str, **kwargs):
        """
        Update a document

        Args:
            name: Name of the document
            **kwargs: Fields to update

        Returns:
            dict: Updated document
        """
        doc = frappe.get_doc(doctype, name)

        for key, value in kwargs.items():
            if hasattr(doc, key):
                setattr(doc, key, value)

        doc.save()
        return doc

    update_doc.__name__ = f"update_{doctype.lower().replace(' ', '_')}"
    update_doc.__doc__ = f"Update a {doctype} document"

    return wrap_frappe_function(update_doc)


def create_delete_function(doctype: str) -> Callable:
    """
    Create a function to delete a document

    Args:
        doctype: DocType name

    Returns:
        Callable: Function to delete a document
    """

    def delete_doc(name: str):
        """
        Delete a document

        Args:
            name: Name of the document

        Returns:
            dict: Result of deletion
        """
        frappe.delete_doc(doctype, name)
        return {"message": f"{doctype} {name} deleted successfully"}

    delete_doc.__name__ = f"delete_{doctype.lower().replace(' ', '_')}"
    delete_doc.__doc__ = f"Delete a {doctype} document"

    return wrap_frappe_function(delete_doc)


def create_list_function(doctype: str) -> Callable:
    """
    Create a function to list documents

    Args:
        doctype: DocType name

    Returns:
        Callable: Function to list documents
    """

    def list_docs(
        filters: dict = None, fields: list = None, limit: int = 100, order_by: str = "modified desc"
    ):
        """
        List documents

        Args:
            filters: Filters to apply
            fields: Fields to return
            limit: Maximum number of documents to return
            order_by: Order by clause

        Returns:
            list: List of documents
        """
        if not fields:
            fields = ["name", "modified"]

        result = frappe.get_list(
            doctype, filters=filters, fields=fields, limit_page_length=limit, order_by=order_by
        )

        return result

    list_docs.__name__ = f"list_{doctype.lower().replace(' ', '_')}"
    list_docs.__doc__ = f"List {doctype} documents"

    return wrap_frappe_function(list_docs)


# Built-in handlers for standard function types

def handle_create_document(reference_doctype=None, ignore_permissions=False, **kwargs):
    """
    Create a new document

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
                "permission_denied": True
            }

        # Support both flat kwargs and a "doc" wrapper {"doc": {"field": "value"}}
        if "doc" in kwargs and isinstance(kwargs["doc"], dict):
            doc_fields = kwargs.pop("doc")
            kwargs.update(doc_fields)

        doc = frappe.get_doc({"doctype": reference_doctype, **kwargs})
        doc.insert(ignore_permissions=ignore_permissions)

        # Return a concise dictionary to prevent polluting the LLM context with a huge document payload
        result_dict = {"name": doc.name, "creation": str(doc.creation)}

        return {"success": True, "result": result_dict, "message": f"{reference_doctype} created"}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_create_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_delete_document(document_id=None, reference_doctype=None, ignore_permissions=False, **kwargs):
    """
    Delete a document

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
            return {"success": False, "error": f"Document {document_id} not found in {reference_doctype}"}

        # Pre-check delete permission
        if not ignore_permissions and not frappe.has_permission(reference_doctype, "delete", doc=document_id):
            return {
                "success": False,
                "error": f"You do not have delete permission on {reference_doctype} {document_id}",
                "permission_denied": True
            }

        frappe.delete_doc(reference_doctype, document_id, ignore_permissions=ignore_permissions)

        return {"success": True, "message": f"{reference_doctype} {document_id} deleted"}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_delete_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_get_list(
    filters=None, fields=None, limit=0, order_by="modified desc", reference_doctype=None, **kwargs
):
    """
    Get a list of documents from a doctype

    Args:
        filters (dict): Filters to apply
        fields (list): Fields to include in the result
        limit (int): Maximum number of documents to return
        order_by (str): Order by clause
        reference_doctype (str): DocType to get list from (provided by function configuration)

    Returns:
        list: List of documents
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
            warning = f"Fields {', '.join(invalid_fields)} do not exist in DocType '{reference_doctype}' and were ignored."

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

                filter_warning = f"Filter fields {', '.join(invalid_filter_fields)} do not exist in DocType '{reference_doctype}' and were ignored."
                warning = f"{warning}\n{filter_warning}" if warning else filter_warning

        page_length = limit if limit and int(limit) > 0 else None
        ignore_permissions = kwargs.get("ignore_permissions", False)

        result = frappe.get_list(
            reference_doctype,
            filters=filters,
            fields=filtered_fields,
            limit_page_length=page_length,
            order_by=order_by,
            ignore_permissions=ignore_permissions,
        )

        import datetime

        for item in result:
            for key, value in item.items():
                if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
                    item[key] = str(value)

        response = {"success": True, "result": result}

        if warning:
            response["warning"] = warning

        response["valid_fields"] = valid_fields[:20]
        if len(valid_fields) > 20:
            response["valid_fields_note"] = f"Showing first 20 of {len(valid_fields)} available fields"

        return response
    except Exception as e:
        logger.warning(f"handle_get_list failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_update_document(document_id=None, data=None, reference_doctype=None, ignore_permissions=False, **kwargs):
    """
    Update a document in the database
    """
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

    if not ignore_permissions and not frappe.has_permission(reference_doctype, "write", doc=document_id):
        return {
            "success": False,
            "error": f"You do not have write permission on {reference_doctype} {document_id}",
            "permission_denied": True
        }

    try:
        doc = frappe.get_doc(reference_doctype, document_id)

        for field, value in data.items():
            doc.set(field, value)

        doc.save(ignore_permissions=ignore_permissions)
        commit_if_background()

        # Build a concise result dict
        result_dict = {"name": doc.name, "modified": str(doc.modified)}
        # Add the fields that were updated so the LLM has explicit confirmation
        for field in data.keys():
            result_dict[field] = getattr(doc, field, data.get(field))

        return {
            "success": True,
            "result": result_dict,
            "message": f"{reference_doctype} {document_id} updated successfully.",
        }
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_update_document failed: {e!s}\n{frappe.get_traceback()}")
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
                return {"success": False, "error": f"Document '{document_id}' not found in '{reference_doctype}'"}
            doc_name = document_id
        else:
            valid_fields = [f.fieldname for f in frappe.get_meta(reference_doctype).fields]
            applied_filters = {k: v for k, v in filters.items() if k in valid_fields and v}

            if not applied_filters:
                return {"success": False, "error": "No valid filter fields provided to find the document."}

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

    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_get_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_get_documents(reference_doctype: str = None, document_ids: list = None, **kwargs):
    """
    Get multiple documents by ID for a DocType.
    """
    try:
        if not reference_doctype:
            reference_doctype = frappe.flags.get("current_function_doctype")

        if not reference_doctype:
            return {"success": False, "error": "No reference doctype provided."}

        ids = document_ids or kwargs.get("ids") or kwargs.get("documents") or []
        if not isinstance(ids, list):
            ids = [ids]

        if not ids:
            return {"success": False, "error": "No document_ids provided."}

        docs = get_documents(reference_doctype, ids)
        res_docs = [doc.as_dict() if callable(getattr(doc, "as_dict", None)) else doc for doc in docs]
        return {
            "success": True,
            "result": res_docs,
            "message": f"{len(res_docs)} {reference_doctype} document(s) fetched successfully",
        }
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_get_documents failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_create_documents(reference_doctype: str, documents: list = None, data: list = None, **kwargs):
    """
    Create multiple documents.
    Accepts either 'documents' or 'data' depending on schema auto-generation.
    """
    docs = documents or data or []
    sanitized = [
        _sanitize_for_doctype(reference_doctype, d)
        for d in docs if isinstance(d, dict)
    ]
    return create_documents(reference_doctype, sanitized)


def handle_update_documents(reference_doctype: str, documents: list = None, data: list = None, **kwargs):
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
    return delete_documents(reference_doctype, document_ids or [])


def handle_submit_document(reference_doctype: str = None, document_id: str = None, ignore_permissions=False, **kwargs):
    try:
        if not reference_doctype:
            reference_doctype = frappe.flags.get("current_function_doctype")

        if not reference_doctype:
            return {"success": False, "error": "No reference doctype provided."}

        if not document_id:
            document_id = kwargs.get("name")

        if not document_id:
            return {"success": False, "error": "No document ID provided."}

        if not ignore_permissions and not frappe.has_permission(reference_doctype, "submit", doc=document_id):
            return {"success": False, "error": f"No permission to submit {reference_doctype} {document_id}"}

        doc = frappe.get_doc(reference_doctype, document_id)
        doc.submit()
        commit_if_background()
        return {"success": True, "message": f"{reference_doctype} {document_id} submitted successfully"}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning(f"handle_submit_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_cancel_document(reference_doctype: str = None, document_id: str = None, ignore_permissions=False, **kwargs):
    try:
        if not reference_doctype:
            reference_doctype = frappe.flags.get("current_function_doctype")

        if not reference_doctype:
            return {"success": False, "error": "No reference doctype provided."}

        if not document_id:
            document_id = kwargs.get("name")

        if not document_id:
            return {"success": False, "error": "No document ID provided."}

        if not ignore_permissions and not frappe.has_permission(reference_doctype, "cancel", doc=document_id):
            return {"success": False, "error": f"No permission to cancel {reference_doctype} {document_id}"}

        doc = frappe.get_doc(reference_doctype, document_id)
        doc.cancel()
        commit_if_background()
        return {"success": True, "message": f"{reference_doctype} {document_id} cancelled successfully"}
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.warning(f"handle_cancel_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_get_value(doctype: str = None, filters: dict = None, fieldname=None, ignore_permissions=False, **kwargs):
    """
    Get a field value (or multiple values) from a DocType.
    Matches the auto-generated JSON schema: doctype + filters + fieldname.
    """
    if not doctype or not filters or not fieldname:
        return {
            "success": False,
            "error": "Missing required parameters: doctype, filters, fieldname"
        }

    try:
        if isinstance(filters, dict):
            doc_name = frappe.db.get_value(doctype, filters, "name")
        else:
            doc_name = filters

        if not doc_name:
            return {
                "success": False,
                "error": f"No {doctype} found matching filters {filters}"
            }

        if not ignore_permissions and not frappe.has_permission(doctype, "read", doc=doc_name):
            return {
                "success": False,
                "error": f"You do not have read permission on {doctype} {doc_name}"
            }

        value = frappe.db.get_value(doctype, doc_name, fieldname)
        return {
            "success": True,
            "doctype": doctype,
            "filters": filters,
            "fieldname": fieldname,
            "value": value,
        }
    except Exception as e:
        logger.warning(f"handle_get_value failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_set_value(doctype: str = None, filters: dict = None, fieldname: str = None, value=None, ignore_permissions=False, **kwargs):
    """
    Set a field value on a document that matches filters.
    """
    if not doctype or not filters or not fieldname:
        return {"success": False, "error": "Missing required parameters"}

    try:
        if isinstance(filters, dict):
            doc_name = frappe.db.get_value(doctype, filters, "name")
        else:
            doc_name = filters

        if not doc_name:
            return {
                "success": False,
                "error": f"No {doctype} found matching filters {filters}"
            }

        if not ignore_permissions and not frappe.has_permission(doctype, "write", doc=doc_name):
            return {
                "success": False,
                "error": f"You do not have write permission on {doctype} {doc_name}"
            }

        doc = frappe.get_doc(doctype, doc_name)
        doc.set(fieldname, value)
        doc.save(ignore_permissions=ignore_permissions)
        commit_if_background()

        return {
            "success": True,
            "doctype": doctype,
            "name": doc_name,
            "fieldname": fieldname,
            "new_value": doc.get(fieldname)
        }

    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_set_value failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}


def handle_get_report_result(report_name: str, filters: dict | None = None, limit: int | None = None, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission("Report", "read", doc=report_name):
        return {"success": False, "error": f"You do not have permission to read Report {report_name}"}
    return get_report_result(report_name, filters=filters, limit=limit, user=frappe.session.user)


def handle_attach_file_to_document(reference_doctype, document_id, **kwargs):
    """
    SDK handler that wraps attach_file_to_document.
    """
    if not reference_doctype or not document_id:
        return {
            "success": False,
            "error": "reference_doctype and document_id are required"
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
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_attach_file_to_document failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}
