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


def create_agent_tools(agent) -> list[FunctionTool]:
    """
    Create function tools for Huf Agent
    
    This combines:
    1. MCP tools from linked MCP servers
    2. Native tools from Agent Tool Function documents
    """
    tools = []
    
    # Load MCP tools from linked MCP servers
    if hasattr(agent, "agent_mcp_server") and agent.agent_mcp_server:
        try:
            from huf.ai.mcp_client import create_mcp_tools
            mcp_tools = create_mcp_tools(agent)
            tools.extend(mcp_tools)
        except Exception as e:
            frappe.log_error(
                f"Error loading MCP tools for agent: {str(e)}",
                "MCP Tool Loading Error"
            )
    
    # Load native tools from Agent Tool Function documents

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
                elif function_doc.types == "Client Side Tool":
                    function_path = "huf.ai.cilent_side_tool.client_side_function"
                    if not function_doc.function_name:
                        continue
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
                    elif function_doc.types == "Get Conversation Data":
                        function_path = "huf.ai.sdk_tools.handle_get_conversation_data"
                    elif function_doc.types == "Set Conversation Data":
                        function_path = "huf.ai.sdk_tools.handle_set_conversation_data"
                    elif function_doc.types == "Load Conversation Data":
                        function_path = "huf.ai.sdk_tools.handle_load_conversation_data"

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
                    if function_doc.types == "Attach File to Document":
                        if function_doc.reference_doctype:
                            extra_args["reference_doctype"] = function_doc.reference_doctype

                    elif (
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
                    
                    elif function_doc.types == "Client Side Tool":
                        if function_doc.function_name:
                            extra_args["function_name"] = function_doc.function_name

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

    
    if hasattr(agent, "enable_conversation_data") and agent.enable_conversation_data:
        existing_types = [t.name for t in tools]
        
        # Get Conversation Data
        if "get_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="get_conversation_data",
                description="Retrieve a specific value from the conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_get_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the item to retrieve"},
                        "default": {"type": "string", "description": "Default value if not found"}
                    },
                    "required": ["name"]
                }
            )
            if tool: tools.append(tool)

        # Set Conversation Data
        if "set_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="set_conversation_data",
                description="Store a value in the conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_set_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the item to set"},
                        "value": {"type": "string", "description": "Value to store (scalar, object, or array)"},
                        "value_type": {"type": "string", "description": "Type of value (scalar, object, array). Optional."},
                        "source": {"type": "string", "description": "Source of data (agent/user). Default: agent"}
                    },
                    "required": ["name", "value"]
                }
            )
            if tool: tools.append(tool)

        # Load Conversation Data
        if "load_conversation_data" not in existing_types:
            tool = create_function_tool(
                name="load_conversation_data",
                description="Load the entire conversation data context.",
                tool_name="huf.ai.sdk_tools.handle_load_conversation_data",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            )
            if tool: tools.append(tool)

    return tools

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

                if isinstance(ctx, dict):
                    if "conversation_id" in ctx:
                        args_dict["conversation_id"] = ctx["conversation_id"]
                    if "agent_run_id" in ctx:
                        args_dict["agent_run_id"] = ctx["agent_run_id"]
                    if "agent_name" in ctx:
                        args_dict["agent_name"] = ctx["agent_name"]

                for key, value in _extra_args.items():
                    if key not in args_dict:
                        args_dict[key] = value

                if _function.__name__ in ["handle_get_request", "handle_post_request"]:
                    args_dict["tool_name"] = name
                import inspect

                sig = inspect.signature(_function)
                accepts_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD 
                    for p in sig.parameters.values()
                )
                if accepts_kwargs:
                    result = _function(**args_dict)
                else:
                    valid_params = set(sig.parameters.keys())
                    
                    filtered_args = {
                        k: v for k, v in args_dict.items() 
                        if k in valid_params
                    }
                    result = _function(**filtered_args)
                
                # Handle async functions
                if asyncio.iscoroutine(result):
                    result = await result

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


def handle_delete_document(document_id=None, reference_doctype=None,**kwargs):
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

def handle_run_agent(agent_name: str, prompt: str, **kwargs):
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
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "handle_attach_file_to_document: failed")
        return {"success": False, "error": str(e)}


# Conversation Data Helpers
def _now_iso_utc() -> str:
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()

def _load_state(state_json: str | None | dict) -> dict:
    if not state_json:
        return {"version": 1, "scope": {}, "items": []}
    if isinstance(state_json, dict):
        data = state_json
    else:
        try:
            data = json.loads(state_json)
            if isinstance(data, str): # Handle double encoded
                try: data = json.loads(data)
                except: pass
        except (json.JSONDecodeError, TypeError):
             return {"version": 1, "scope": {}, "items": []}
             
    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    if "version" not in data:
        data["version"] = 1
    return data

def handle_get_conversation_data(name: str, default: Any = None, conversation_id: str = None, **kwargs):
    """Get a value from conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    
    try:
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)
        
        value = default
        for item in state["items"]:
            if item.get("name") == name:
                value = item.get("value", default)
                break
                
        return {"success": True, "value": value}
    except Exception as e:
        frappe.log_error(f"Error getting conversation data: {str(e)}", "Conversation Data")
        return {"success": False, "error": str(e)}

def handle_set_conversation_data(
    name: str, 
    value: Any, 
    value_type: str = None, 
    source: str = "agent", 
    conversation_id: str = None, 
    **kwargs
):
    """Set a value in conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    
    try:
        # Debug Log
        frappe.logger().info(f"[Conversation Data] Setting {name} for {conversation_id}")

        # Load fresh state
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)

        # infer a simple type label if not provided
        if value_type is None:
            if isinstance(value, dict):
                value_type = "object"
            elif isinstance(value, list):
                value_type = "array"
            else:
                value_type = "scalar"

        updated_item = {
            "name": name,
            "value": value,
            "meta": {
                "type": value_type,
                "updated_at": _now_iso_utc(),
                "source": source
            }
        }

        # Update or Append
        found = False
        for i, item in enumerate(state["items"]):
            if item.get("name") == name:
                state["items"][i] = updated_item
                found = True
                break
        
        if not found:
            state["items"].append(updated_item)

        new_json = json.dumps(state, ensure_ascii=False, indent=2)
        
        frappe.db.set_value("Agent Conversation", conversation_id, "conversation_data", new_json)
        frappe.db.commit() # Persist changes immediately
        
        return {"success": True, "message": f"Set '{name}' match successfully"}
    
    except Exception as e:
        frappe.log_error(f"Error setting conversation data: {str(e)}", "Conversation Data")
        return {"success": False, "error": str(e)}

def handle_load_conversation_data(conversation_id: str = None, **kwargs):
    """Load the full conversation data."""
    if not conversation_id:
        return {"success": False, "error": "No conversation context provided"}
    try:
        data_json = frappe.db.get_value("Agent Conversation", conversation_id, "conversation_data")
        state = _load_state(data_json)
        return {"success": True, "data": state}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _get_default_image_model(provider_name: str) -> str:
    """
    Get default image generation model for a provider.
    
    Based on LiteLLM documentation: https://docs.litellm.ai/docs/image_generation
    
    Args:
        provider_name: Lowercase provider name (e.g., "openai", "azure", "google")
    
    Returns:
        str: Default image model name, or None if not supported
    """
    defaults = {
        "openai": "dall-e-3",
        "azure": "dall-e-3",  # Azure uses same models with azure/ prefix
        "openrouter": "dall-e-3",  # OpenRouter can route to OpenAI models
        "google": "google/gemini-2.5-flash-image",
        "vertex_ai": "vertex_ai/imagegeneration@006",
        "bedrock": "bedrock/stability.stable-diffusion-xl-v0",
        "recraft": "recraft/recraftv3",
    }
    
    return defaults.get(provider_name.lower())

@frappe.whitelist()
async def handle_generate_image(
    prompt: str,
    size: str = "1024x1024",
    quality: str = "standard",
    n: int = 1,
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Generate an image using the agent's configured provider and image generation model.
    
    Uses LiteLLM's image_generation() function. The model used is either:
    1. The agent's explicitly configured image_generation_model field, OR
    2. An auto-detected suitable image model based on the provider
    
    Args:
        prompt: Text description of the image to generate
        size: Image size (1024x1024, 1792x1024, 1024x1792, etc.)
        quality: Image quality (standard, hd, high, medium, low)
        n: Number of images to generate (1-10)
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context
    
    Returns:
        dict: {
            "success": bool,
            "images": [{"url": str, "file_id": str}],
            "message": str
        }
    """
    try:
        # Get agent configuration from context
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}
        
        agent_doc = frappe.get_doc("Agent", agent_name)
        provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
        api_key = provider_doc.get_password("api_key")
        
        if not api_key:
            return {"success": False, "error": "API key not configured for provider"}
        
        # Determine image generation model
        image_model = None
        
        if hasattr(agent_doc, "image_generation_model") and agent_doc.image_generation_model:
            # Use explicitly configured image model
            model_doc = frappe.get_doc("AI Model", agent_doc.image_generation_model)
            image_model = model_doc.model_name
        else:
            # Auto-detect suitable image model based on provider
            provider_name = provider_doc.provide_name.lower()
            image_model = _get_default_image_model(provider_name)
        
        if not image_model:
            return {
                "success": False,
                "error": f"Image generation not supported for provider '{provider_doc.provide_name}'. Please configure an image_generation_model in agent settings."
            }
        
        # Normalize to LiteLLM format
        from huf.ai.providers.litellm import _normalize_model_name
        normalized_model = _normalize_model_name(image_model, agent_doc.provider)
        
        # Call LiteLLM image generation
        import litellm
        
        response = await asyncio.to_thread(
            litellm.image_generation,
            prompt=prompt,
            model=normalized_model,
            n=n,
            size=size,
            quality=quality,
            api_key=api_key
        )
        
        # Get conversation_index once if conversation_id exists
        # Each Agent Message needs a unique, sequential conversation_index to maintain order.
        conversation_index = None
        if conversation_id:
            try:
                last_index = frappe.db.sql("""
                    SELECT MAX(conversation_index) as last_index
                    FROM `tabAgent Message`
                    WHERE conversation = %s
                """, (conversation_id,), as_dict=1)
                
                conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1
            except Exception:
                conversation_index = 1
        
        # Process response and save images
        images = []
        if hasattr(response, 'data') and response.data:
            for idx, image_data in enumerate(response.data):
                # Get image URL or base64
                image_url = None
                image_b64 = None
                
                if hasattr(image_data, 'url'):
                    image_url = image_data.url
                elif hasattr(image_data, 'b64_json'):
                    image_b64 = image_data.b64_json
                elif isinstance(image_data, dict):
                    image_url = image_data.get('url')
                    image_b64 = image_data.get('b64_json')
                
                if not image_url and not image_b64:
                    continue
                
                # Download and save image
                image_bytes = None
                filename = f"generated_image_{idx + 1}.png"
                
                if image_url and image_url.startswith('http'):
                    # Download from URL
                    img_response = requests.get(image_url, timeout=30)
                    img_response.raise_for_status()
                    image_bytes = img_response.content
                elif image_b64:
                    # Base64 encoded
                    image_bytes = base64.b64decode(image_b64)
                elif image_url:
                    # Local file path or other format
                    frappe.log_error(f"Unsupported image URL format: {image_url}", "Image Generation")
                    continue
                
                if not image_bytes:
                    continue
                
                # Save to Frappe (attach to conversation first, then we'll attach to message)
                saved_file = save_file(
                    filename,
                    image_bytes,
                    "Agent Conversation",
                    conversation_id or "Unknown",
                    is_private=False
                )
                
                file_id = saved_file.name if hasattr(saved_file, 'name') else saved_file.get('name')
                file_url = saved_file.file_url if hasattr(saved_file, 'file_url') else saved_file.get('file_url')
                
                images.append({
                    "url": file_url or f"/files/{filename}",
                    "file_id": file_id
                })
                
                # Create Agent Message with kind "Image" for each generated image
                if conversation_id and conversation_index is not None:
                    try:
                        # Get provider and model from agent
                        provider = agent_doc.provider
                        model = agent_doc.model
                        
                        # Create Agent Message with kind "Image"
                        message_doc = frappe.get_doc({
                            "doctype": "Agent Message",
                            "conversation": conversation_id,
                            "role": "agent",
                            "content": f"Generated image: {prompt}",
                            "kind": "Image",
                            "generated_image": file_url or f"/files/{filename}",
                            "agent": agent_name,
                            "provider": provider,
                            "model": model,  # Link to AI Model
                            "agent_run": kwargs.get("agent_run_id"),
                            "conversation_index": conversation_index + idx,  # Increment for each image
                            "is_agent_message": 1,
                            "user": "Agent"
                        })
                        message_doc.insert(ignore_permissions=True)
                        
                    except Exception as e:
                        frappe.log_error(
                            f"Error creating Agent Message for generated image: {str(e)}",
                            "Image Generation Message Creation"
                        )
                        # Continue even if message creation fails
        
        # Update conversation total_messages once after all images are created
        if conversation_id and conversation_index is not None and images:
            try:
                final_index = conversation_index + len(images) - 1
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET total_messages = %s, last_activity = NOW()
                    WHERE name = %s
                """, (final_index, conversation_id))
            except Exception as e:
                frappe.log_error(
                    f"Error updating conversation total_messages: {str(e)}",
                    "Image Generation Message Creation"
                )
        
        if not images:
            return {
                "success": False,
                "error": "Image generation succeeded but no images were returned"
            }
        
        return {
            "success": True,
            "images": images,
            "message": f"Generated {len(images)} image(s) successfully"
        }
        
    except Exception as e:
        frappe.log_error(f"Image generation error: {str(e)}", "Image Generation Tool")
        return {"success": False, "error": str(e)}

