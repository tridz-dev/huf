import inspect
import json
from typing import Any, Callable
from frappe.utils.background_jobs import enqueue
import base64
from frappe.utils.file_manager import save_file
import asyncio
import frappe
import io
import requests
import base64
from frappe.utils.file_manager import save_file
from frappe import _
from agents import FunctionTool
from frappe import client

from .tool_functions import (
    create_documents,update_documents,
    delete_documents,submit_document, cancel_document,
    get_value, set_value, get_report_result,attach_file_to_document
)
import re
import hashlib
from datetime import datetime, timedelta

from huf.ai.provider_tool_handler import execute_provider_tool

def create_agent_tools(agent) -> list[FunctionTool]:
    """
    Create function tools for Huf Agent
    """
    tools = []

    if hasattr(agent, "agent_tool") and agent.agent_tool:
        for func in agent.agent_tool:
            try:
                # Fetch linked tool function doc
                function_doc = frappe.get_doc("Agent Tool Function", func.tool)

                function_path = None
                if function_doc.types in ["Custom Function", "App Provided"]:
                    if not function_doc.function_path:
                        continue
                    function_path = function_doc.function_path
                else:
                    if function_doc.types == "Get List":
                        function_path = "huf.ai.sdk_tools.handle_get_list"
                    elif function_doc.types == "Get Document":
                        function_path = "huf.ai.sdk_tools.handle_get_document"
                    elif function_doc.types == "Update Document":
                        function_path = "huf.ai.sdk_tools.handle_update_document"
                    elif function_doc.types == "Create Document":
                        function_path = "huf.ai.sdk_tools.handle_create_document"
                    elif function_doc.types == "Delete Document":
                        function_path = "huf.ai.sdk_tools.handle_delete_document"
                    elif function_doc.types == "Get Multiple Documents":
                        function_path = "huf.ai.sdk_tools.handle_get_documents"
                    elif function_doc.types == "Create Multiple Documents":
                        function_path = "huf.ai.sdk_tools.handle_create_documents"
                    elif function_doc.types == "Update Multiple Documents":
                        function_path = "huf.ai.sdk_tools.handle_update_documents"
                    elif function_doc.types == "Delete Multiple Documents":
                        function_path = "huf.ai.sdk_tools.handle_delete_documents"
                    elif function_doc.types == "Submit Document":
                        function_path = "huf.ai.sdk_tools.handle_submit_document"
                    elif function_doc.types == "Cancel Document":
                        function_path = "huf.ai.sdk_tools.handle_cancel_document"
                    elif function_doc.types == "Get Value":
                        function_path = "huf.ai.sdk_tools.handle_get_value"
                    elif function_doc.types == "Set Value":
                        function_path = "huf.ai.sdk_tools.handle_set_value"
                    elif function_doc.types == "Get Report Result":
                        function_path = "huf.ai.sdk_tools.handle_get_report_result"
                    elif function_doc.types == "GET":
                        function_path = "huf.ai.http_handler.handle_get_request"
                    elif function_doc.types == "POST":
                        function_path = "huf.ai.http_handler.handle_post_request"
                    elif function_doc.types == "Run Agent":
                        function_path = "huf.ai.sdk_tools.handle_run_agent"
                    elif function_doc.types == "Attach File to Document":
                        function_path = "huf.ai.sdk_tools.handle_attach_file_to_document"

                    else:
                        continue

                if function_doc:
                    params = {}
                    if function_doc.params:
                        try:
                            params = json.loads(function_doc.params)
                        except Exception as e:
                            frappe.log_error(
                                "SDK Functions Debug",
                                f"Error parsing params for {function_doc.name}: {str(e)}"
                            )

                    if "additionalProperties" in params:
                        del params["additionalProperties"]

                    extra_args = {}
                    if (
                        function_doc.types
                        in [
                            "Get Document", "Get Multiple Documents", "Get List",
                            "Create Document", "Create Multiple Documents",
                            "Update Document", "Update Multiple Documents",
                            "Delete Document", "Delete Multiple Documents"
                        ]
                        and function_doc.reference_doctype
                    ):
                        extra_args["reference_doctype"] = function_doc.reference_doctype

                    tool = create_function_tool(
                        function_doc.tool_name,
                        function_doc.description,
                        function_path,
                        params,
                        extra_args=extra_args,
                    )

                    if tool:
                        tools.append(tool)

            except Exception as e:
                frappe.log_error(
                    "SDK Functions Debug",
                    f"Error processing function {func.tool}: {str(e)}"
                )
    if agent.provider:
        # Fetch tools for this provider, excluding STT (since STT is UI driven)
        provider_tools = frappe.get_all("AI Provider Tool", 
            filters={
                "provider": agent.provider, 
                "enabled": 1,
                "provider_tool_type": ["!=", "Speech to Text"]
            },
            fields=["name", "provider_tool_name", "provider_tool_type", "static_params"]
        )

        for pt in provider_tools:
            tools.append(_create_dynamic_tool(pt))

    return tools


def _create_dynamic_tool(tool_doc):
    """Internal helper to wrap a Provider Tool as a FunctionTool"""
    async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
        try:
            args = json.loads(args_json or "{}")
            res = execute_provider_tool(tool_name=tool_doc.name, kwargs=args)
            return json.dumps(res.get("result", res))
        except Exception as e:
            return json.dumps({"error": str(e)})

    # Simple prompt schema
    schema = {
        "type": "object", 
        "properties": {
            "prompt": {"type": "string", "description": "The input/prompt for the tool"}
        }
    }
    
    from agents import FunctionTool 
    safe_name = tool_doc.provider_tool_name.lower().replace(" ", "_")
    return FunctionTool(
        name=safe_name,
        description=f"Tool for {tool_doc.provider_tool_type}",
        params_json_schema=schema,
        on_invoke_tool=on_invoke_tool
    )

def create_function_tool(
    name: str,
    description: str,
    tool_name: str,
    parameters: dict[str, Any],
    extra_args: dict[str, Any] = None,
) -> FunctionTool:
    """
    Create a FunctionTool for Huf Tool functions

	Args:
	    name: Tool name
	    description: Tool description
	    function_name: Function name to call
	    parameters: Function parameters schema
	    extra_args: Extra arguments to pass to the function

	Returns:
	    FunctionTool: Function tool
    """

    function = get_function_from_name(tool_name)

    if not function:
        return None

    try:
        _extra_args = extra_args or {}
        _function = function

        async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
            try:
                if args_json is None and isinstance(ctx, str):
                    args_json = ctx
                    ctx = None

                args_dict = json.loads(args_json or "{}")

                for key, value in _extra_args.items():
                    if key not in args_dict:
                        args_dict[key] = value

                if _function.__name__ in ["handle_get_request", "handle_post_request"]:
                    args_dict["tool_name"] = name

                result = _function(**args_dict)

                if hasattr(result, "as_dict"):
                    result = result.as_dict()

                return json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)

            except Exception as e:
                frappe.log_error(f"Error in on_invoke_tool for tool '{name}': {str(e)}", "SDK Functions Debug")
                return json.dumps({"error": str(e)})

        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', (name or ""))
        if len(safe_name) > 128:
            safe_name = safe_name[:128]

        if safe_name != name:
            frappe.log("SDK Functions Debug", f"Tool runtime name '{safe_name}' created for friendly name '{name}'")

        tool = FunctionTool(
            name=safe_name,
            description=description,
            params_json_schema=parameters,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=False
        )

        return tool

    except Exception as e:
        frappe.log_error(f"Error creating FunctionTool for {name}: {str(e)}", "SDK Functions Debug")
        return None


def get_function_from_name(tool_name: str) -> Callable:
	"""
	Get a function from its name

	Args:
	    function_name: Fully qualified function name (module.function)

	Returns:
	    Callable: Function
	"""

	try:
		try:
			module_name, func_name = tool_name.rsplit(".", 1)
		except ValueError as ve:
			frappe.log_error(
				"SDK Functions Debug",
				f"Invalid function name format: {tool_name}. Should be 'module.function'",
			)
			return None

		try:
			module = __import__(module_name, fromlist=[func_name])
		except ImportError as ie:
			frappe.log_error("SDK Functions Debug", f"Module import error: {str(ie)}")
			return None

		try:
			available_attrs = dir(module)
		except Exception as e:
			frappe.log_error("SDK Functions Debug", f"Error getting module attributes: {str(e)}")

		try:
			function = getattr(module, func_name)
		except AttributeError as ae:
			frappe.log_error("SDK Functions Debug", f"Function not found in module: {str(ae)}")
			return None

		if not callable(function):
			return None

		return function

	except Exception as e:
		frappe.log_error(
			"SDK Functions Debug", f"Unexpected error getting function {tool_name}: {str(e)}"
		)
		return None


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


			if hasattr(result, "as_dict"):
				result = result.as_dict()


			elif isinstance(result, list) and result and hasattr(result[0], "as_dict"):
				result = [item.as_dict() if hasattr(item, "as_dict") else item for item in result]

			return {"success": True, "result": result}
		except Exception as e:
			frappe.log_error(f"Error in function {func.__name__}: {e}")
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
    except Exception:
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

def handle_create_document(reference_doctype=None, **kwargs):
    """
    Create a new document

    Args:
        reference_doctype (str): DocType of the document
        **kwargs: Fields of the document

    Returns:
        dict: Created document data
    """
    try:
        if not reference_doctype:
            return {"success": False, "error": "No reference doctype provided."}

        if not frappe.db.exists("DocType", reference_doctype):
            return {"success": False, "error": f"DocType '{reference_doctype}' does not exist."}

        doc = frappe.get_doc({"doctype": reference_doctype, **kwargs})
        doc.insert()

        doc_dict = doc.as_dict()
        import datetime
        for k, v in doc_dict.items():
            if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
                doc_dict[k] = str(v)

        return {"success": True, "result": doc_dict, "message": f"{reference_doctype} created"}
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_create_document: {str(e)}")
        return {"success": False, "error": str(e)}


def handle_delete_document(document_id=None, reference_doctype=None):
    """
    Delete a document

    Args:
        document_id (str): ID of the document
        reference_doctype (str): DocType of the document

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

        frappe.delete_doc(reference_doctype, document_id)

        return {"success": True, "message": f"{reference_doctype} {document_id} deleted"}
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_delete_document: {str(e)}")
        return {"success": False, "error": str(e)}


def handle_get_list(
	filters=None, fields=None, limit=0, order_by="modified desc", reference_doctype=None
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

		result = frappe.get_all(
			reference_doctype,
			filters=filters,
			fields=filtered_fields,
			limit_page_length=page_length,
			order_by=order_by,
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
		frappe.log_error("SDK Functions Debug", f"Error in handle_get_list: {str(e)}")
		return {"success": False, "error": str(e)}


def handle_update_document(document_id=None, data=None, reference_doctype=None, **kwargs):
    """
    Update a document in the database
    """
    if data is None:
        data = {}
        for key, value in kwargs.items():
            if key not in ["document_id", "reference_doctype"]:
                data[key] = value

    if not reference_doctype:
        reference_doctype = frappe.flags.get("current_function_doctype")

    if not reference_doctype:
        return {"success": False, "error": "No reference doctype provided."}

    if not frappe.db.exists(reference_doctype, document_id):
        return {"success": False, "error": f"{reference_doctype} {document_id} not found"}

    try:
        doc = frappe.get_doc(reference_doctype, document_id)

        for field, value in data.items():
            doc.set(field, value)

        doc.save()
        frappe.db.commit() 

        return {
            "success": True,
            "result": doc.as_dict(),
            "message": f"{reference_doctype} {document_id} updated successfully.",
        }
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_update_document: {str(e)}")
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

    except Exception as e:
        frappe.log_error(f"Error in handle_get_document: {str(e)}", "SDK Functions Debug")
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

def handle_submit_document(reference_doctype: str, document_id: str, **kwargs):
    return submit_document(reference_doctype, document_id)

def handle_cancel_document(reference_doctype: str, document_id: str, **kwargs):
    return cancel_document(reference_doctype, document_id)

def handle_get_value(doctype: str = None, filters: dict = None, fieldname=None, **kwargs):
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



def handle_set_value(doctype: str = None, filters: dict = None, fieldname: str = None, value=None, **kwargs):
    """
    Set a field value on a document that matches filters.
    """
    if not doctype or not filters or not fieldname:
        return {"success": False, "error": "Missing required parameters"}

    try:
        doc_name = frappe.db.get_value(doctype, filters, "name")
        if not doc_name:
            return {
                "success": False,
                "error": f"No {doctype} found matching filters {filters}"
            }

        updated = frappe.db.set_value(doctype, doc_name, fieldname, value)
        frappe.db.commit()

        return {
            "success": True,
            "doctype": doctype,
            "name": doc_name,
            "fieldname": fieldname,
            "new_value": updated[fieldname] if isinstance(updated, dict) else value
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "handle_set_value failed")
        return {"success": False, "error": str(e)}


def handle_get_report_result(report_name: str, filters: dict | None = None, limit: int | None = None, **kwargs):
    return get_report_result(report_name, filters=filters, limit=limit, user=frappe.session.user)

def handle_run_agent(agent_name: str, prompt: str):
    """
    Queue another agent execution instead of blocking.
    """
    try:
        if not frappe.db.exists("Agent", agent_name):
            return {"success": False, "error": f"Agent '{agent_name}' does not exist"}

        target_agent = frappe.get_doc("Agent", agent_name)

        job = enqueue(
            "huf.ai.agent_integration.run_agent_sync",
            queue="default",
            timeout=300,
            is_async=True,
            agent_name=agent_name,
            prompt=prompt,
            provider=target_agent.provider,
            model=target_agent.model,
        )

        return {"success": True, "queued": True, "job_id": job.id}
    except Exception as e:
        frappe.log_error("Run Agent Tool Error", str(e))
        return {"success": False, "error": str(e)}

def handle_attach_file_to_document(reference_doctype=None, document_id=None, file_path=None, **kwargs):
    """
    Attach a file to a document.

    Args:
        reference_doctype (str): DocType name
        document_id (str): Target document ID
        file_path (str): File URL or path to attach

    Returns:
        dict: Result message with file_id if success
    """
    if not reference_doctype or not document_id or not file_path:
        return {"success": False, "error": "doctype, document_id, and file_path are required"}
    try:
        result = attach_file_to_document(reference_doctype, document_id, file_path)
        return {"success": True, "result": result}
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_attach_file_to_document: {str(e)}")
        return {"success": False, "error": str(e)}


def _read_file_bytes_from_file_doc(file_doc):

    url = file_doc.file_url

    if url.startswith("/files/") or url.startswith("files/"):

        path = frappe.get_site_path("public", url.lstrip("/"))
        with open(path, "rb") as f:
            return f.read(), file_doc.file_name

    try:
        site_url = frappe.utils.get_url()
        resp = requests.get(site_url.rstrip("/") + url)
        resp.raise_for_status()
        return resp.content, file_doc.file_name
    except Exception:
        return None, None

def handle_speech_to_text(
    file_id: str = None,
    file_url: str = None,
    language: str = None,
    translate: bool = False,
    model: str = "whisper-1",
    provider: str = None,
    api_key: str = None,
    conversation: str = None,
    reference_doctype: str = None,
    document_id: str = None,
    message_id: str = None,
    **kwargs
):
    """
    Transcribe audio via OpenAI Whisper API and store result as Agent Message + File.

    If `message_id` is provided, update that Agent Message's `content`; else create a new
    user message in `conversation`. If `file_id` is missing but `file_url` is provided,
    the audio is fetched directly (and can be saved back to a File doc if you want).
    """
    try:
        if not file_id:
             return {"success": False, "error": "File ID is required."}

        if not provider and conversation:
            conv_doc = frappe.get_doc("Agent Conversation", conversation)
            if conv_doc.agent:
                provider = frappe.db.get_value("Agent", conv_doc.agent, "provider")

        if not provider:
            return {"success": False, "error": "Provider could not be determined."}

        file_doc = frappe.get_doc("File", file_id)

        response = execute_provider_tool(
            provider=provider,
            tool_type="Speech to Text",
            file_doc=file_doc,
            kwargs=kwargs
        )

        if not response:
            return {"success": False, "error": f"No 'Speech to Text' tool configured for provider {provider}."}
        
        if not response.get("success"):
            return response

        text = response.get("result") or "(empty transcript)"
        
        if not isinstance(text, str): 
            text = json.dumps(text)

        if message_id:
            frappe.db.set_value("Agent Message", message_id, "content", text, update_modified=True)
        elif conversation:
            # Create new message if one wasn't passed
            new_msg = frappe.get_doc({
                "doctype": "Agent Message",
                "conversation": conversation,
                "role": "user",
                "content": text,
                "user": frappe.session.user
            })
            new_msg.insert(ignore_permissions=True)
            message_id = new_msg.name

        return {
            "success": True,
            "text": text,
            "file_id": file_id,
            "message_id": message_id
        }

    except Exception as e:
        frappe.log_error(f"STT Error: {frappe.get_traceback()}", "STT Debug")
        return {"success": False, "error": str(e)}