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


from .tool_registry import PermissionAwareToolRegistry
MUTATING_TOOL_TYPES = PermissionAwareToolRegistry.MUTATING_TOOL_TYPES


def _frappe_run_context_dict(ctx) -> dict:
    """Huf run context may be a dict or an Agents SDK ToolContext wrapping that dict."""
    if ctx is None:
        return {}
    if isinstance(ctx, dict):
        return ctx
    inner = getattr(ctx, "context", None)
    return inner if isinstance(inner, dict) else {}


def _check_tool_permission(tool_type: str, context: dict = None, allowed_for_guest: bool = False):
    """Guard function to block dangerous tools for Guest users"""
    user = frappe.session.user
    
    #Guest cannot use mutating tools unless explicitly allowed
    if user == "Guest":
        if allowed_for_guest:
            return {"allowed": True}
             
        if tool_type in MUTATING_TOOL_TYPES:
            return {
                "allowed": False,
                "error": f"Guest users cannot use {tool_type} tools. Please log in."
            }
    
    return {"allowed": True}

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
                f"Error loading MCP tools for agent: {e!s}",
                "MCP Tool Loading Error"
            )

    # Load native tools from Agent Tool Function documents

    from huf.ai.tool_registry import PermissionAwareToolRegistry

    allowed_tool_docs = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)

    for function_doc in allowed_tool_docs:
            try:

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
                                f"Error parsing params for {function_doc.name}: {e!s}"
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

                    elif function_doc.types == "Run Agent":
                        if function_doc.agent:
                            extra_args["target_agent_name"] = function_doc.agent

                    tool = create_function_tool(
                        function_doc.tool_name,
                        function_doc.description,
                        function_path,
                        params,
                        extra_args=extra_args,
                        tool_type=function_doc.types,
                        allowed_for_guest=bool(function_doc.allowed_for_guest)
                    )

                    if tool:
                        tools.append(tool)

            except Exception as e:
                frappe.log_error(
                    "SDK Functions Debug",
                    f"Error processing function {function_doc.name}: {e!s}"
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
                        "source": {"type": "string", "description": "Source of data (agent/user). Default: agent"},
                        "auto_inject": {"type": "boolean", "description": "Whether to auto-inject this variable in the system prompt on future turns. Set false for high-volume variables to prevent context bloat. Default: true"},
                        "inject_mode": {"type": "string", "enum": ["visible", "hidden"], "description": "Injection mode. 'visible' to auto-inject in system prompt (if enabled on agent), 'hidden' to keep it in the data layer only. Default: visible"}
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

            if tool: tools.append(tool)

    existing_types = [t.name for t in tools] if tools else []
    if "get_result_context" not in existing_types:
        tool = create_function_tool(
            name="get_result_context",
            description="Get the full result context of an out-of-band message reference by its handle.",
            tool_name="huf.ai.sdk_tools.handle_get_result_context",
            parameters={
                "type": "object",
                "properties": {
                    "reference_doctype": {
                        "type": "string",
                        "description": "The DocType of the referenced record (e.g. 'Agent Tool Call')"
                    },
                    "reference_name": {
                        "type": "string",
                        "description": "The name/ID of the referenced record"
                    }
                },
                "required": ["reference_doctype", "reference_name"]
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
    tool_type: str = None,
    allowed_for_guest: bool = False
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

            #Permission check before execution
            if tool_type:
                perm_check = _check_tool_permission(tool_type, ctx, allowed_for_guest=allowed_for_guest)
                if not perm_check["allowed"]:
                    return json.dumps({"error": perm_check["error"], "denied": True})

            try:
                if args_json is None and isinstance(ctx, str):
                    args_json = ctx
                    ctx = None

                args_dict = json.loads(args_json or "{}")

                huf_ctx = _frappe_run_context_dict(ctx)
                if "conversation_id" in huf_ctx:
                    args_dict["conversation_id"] = huf_ctx["conversation_id"]
                if "agent_run_id" in huf_ctx:
                    args_dict["agent_run_id"] = huf_ctx["agent_run_id"]
                if "agent_name" in huf_ctx:
                    args_dict["agent_name"] = huf_ctx["agent_name"]

                if _extra_args:
                    args_dict.update(_extra_args)

                if "ignore_permissions" in args_dict:
                    del args_dict["ignore_permissions"]

                if allowed_for_guest and frappe.session.user == "Guest":
                    args_dict["ignore_permissions"] = True

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
                frappe.log_error(f"Error in on_invoke_tool for tool '{name}': {e!s}", "SDK Functions Debug")
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
        frappe.log_error(f"Error creating FunctionTool for {name}: {e!s}", "SDK Functions Debug")
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
		except ValueError:
			frappe.log_error(
				"SDK Functions Debug",
				f"Invalid function name format: {tool_name}. Should be 'module.function'",
			)
			return None

		try:
			module = __import__(module_name, fromlist=[func_name])
		except ImportError as ie:
			frappe.log_error("SDK Functions Debug", f"Module import error: {ie!s}")
			return None

		try:
			available_attrs = dir(module)
		except Exception as e:
			frappe.log_error("SDK Functions Debug", f"Error getting module attributes: {e!s}")

		try:
			function = getattr(module, func_name)
		except AttributeError as ae:
			frappe.log_error("SDK Functions Debug", f"Function not found in module: {ae!s}")
			return None

		if not callable(function):
			return None

		return function

	except Exception as e:
		frappe.log_error(
			"SDK Functions Debug", f"Unexpected error getting function {tool_name}: {e!s}"
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

        doc_dict = doc.as_dict()
        import datetime
        for k, v in doc_dict.items():
            if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
                doc_dict[k] = str(v)

        return {"success": True, "result": doc_dict, "message": f"{reference_doctype} created"}
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_create_document: {e!s}")
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

        #Pre-check delete permission
        if not ignore_permissions and not frappe.has_permission(reference_doctype, "delete", doc=document_id):
            return {
                "success": False,
                "error": f"You do not have delete permission on {reference_doctype} {document_id}",
                "permission_denied": True
            }

        frappe.delete_doc(reference_doctype, document_id, ignore_permissions=ignore_permissions)

        return {"success": True, "message": f"{reference_doctype} {document_id} deleted"}
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_delete_document: {e!s}")
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
		frappe.log_error("SDK Functions Debug", f"Error in handle_get_list: {e!s}")
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
        frappe.db.commit()

        return {
            "success": True,
            "result": doc.as_dict(),
            "message": f"{reference_doctype} {document_id} updated successfully.",
        }
    except Exception as e:
        frappe.log_error("SDK Functions Debug", f"Error in handle_update_document: {e!s}")
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
        frappe.log_error(f"Error in handle_get_document: {e!s}", "SDK Functions Debug")
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

def handle_submit_document(reference_doctype: str, document_id: str, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission(reference_doctype, "submit", doc=document_id):
        return {"success": False, "error": "No permission to submit"}

    doc = frappe.get_doc(reference_doctype, document_id)
    doc.submit()
    return {"success": True, "message": "Submitted"}

def handle_cancel_document(reference_doctype: str, document_id: str, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission(reference_doctype, "cancel", doc=document_id):
        return {"success": False, "error": "No permission to cancel"}

    doc = frappe.get_doc(reference_doctype, document_id)
    doc.cancel()
    return {"success": True, "message": "Cancelled"}

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
        frappe.db.commit()

        return {
            "success": True,
            "doctype": doctype,
            "name": doc_name,
            "fieldname": fieldname,
            "new_value": doc.get(fieldname)
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "handle_set_value failed")
        return {"success": False, "error": str(e)}


def handle_get_report_result(report_name: str, filters: dict | None = None, limit: int | None = None, ignore_permissions=False, **kwargs):
    if not ignore_permissions and not frappe.has_permission("Report", "read", doc=report_name):
        return {"success": False, "error": f"You do not have permission to read Report {report_name}"}
    return get_report_result(report_name, filters=filters, limit=limit, user=frappe.session.user)

def handle_run_agent(target_agent_name: str, prompt: str, **kwargs):
    """
    Queue another agent execution instead of blocking.
    """
    try:
        if not frappe.db.exists("Agent", target_agent_name):
            return {"success": False, "error": f"Agent '{target_agent_name}' does not exist"}

        target_agent = frappe.get_doc("Agent", target_agent_name)
        
        from huf.ai.agent_integration import _is_user_allowed
        if not _is_user_allowed(target_agent, frappe.session.user):
            return {
                "success": False, 
                "error": f"Permission Denied: User '{frappe.session.user}' is not authorized to run the sub-agent '{target_agent_name}'."
            }
        
        conversation_id = kwargs.get("conversation_id")
        agent_run_id = kwargs.get("agent_run_id")
        agent_name_self = kwargs.get("agent_name")

        if target_agent_name == agent_name_self:
            return {
                "success": False, 
                "error": f"Circular Dependency Error: An agent cannot invoke itself as a sub-agent."
            }

        job = enqueue(
            "huf.ai.agent_integration.run_agent_sync",
            queue="default",
            timeout=1500,
            is_async=True,
            agent_name=target_agent_name,
            prompt=prompt,
            provider=target_agent.provider,
            model=target_agent.model,
            parent_conversation_id=conversation_id,
            invoked_by_agent=agent_name_self,
        )

        return {
            "status": "Queued",
            "message": "The task is currently being processed in the background. IMPORTANT: DO NOT tell the user that the task is completed or successful yet. Inform the user that you are working on it and will provide an update shortly. Do not mention the terms 'sub-agent' or 'background queue' explicitly, keep it natural (e.g., 'I am processing this for you now...').",
            "job_id": job.id
        }
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
        frappe.log_error(f"Error getting conversation data: {e!s}", "Conversation Data")
        return {"success": False, "error": str(e)}

def handle_set_conversation_data(
    name: str, 
    value: Any, 
    value_type: str = None, 
    source: str = "agent", 
    conversation_id: str = None, 
    auto_inject: bool = None,
    inject_mode: str = None,
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
                resolved_auto_inject = auto_inject if auto_inject is not None else kwargs.get("auto_inject")
                if resolved_auto_inject is None:
                    resolved_auto_inject = item.get("auto_inject", True)
                
                resolved_inject_mode = inject_mode if inject_mode is not None else kwargs.get("inject_mode")
                if resolved_inject_mode is None:
                    resolved_inject_mode = item.get("inject_mode", "visible")
                
                updated_item["auto_inject"] = resolved_auto_inject
                updated_item["inject_mode"] = resolved_inject_mode
                state["items"][i] = updated_item
                found = True
                break

        if not found:
            resolved_auto_inject = auto_inject if auto_inject is not None else kwargs.get("auto_inject")
            if resolved_auto_inject is None:
                resolved_auto_inject = True
            
            resolved_inject_mode = inject_mode if inject_mode is not None else kwargs.get("inject_mode")
            if resolved_inject_mode is None:
                resolved_inject_mode = "visible"
                
            updated_item["auto_inject"] = resolved_auto_inject
            updated_item["inject_mode"] = resolved_inject_mode
            state["items"].append(updated_item)

        new_json = json.dumps(state, ensure_ascii=False, indent=2)

        frappe.db.set_value("Agent Conversation", conversation_id, "conversation_data", new_json)
        frappe.db.commit() # Persist changes immediately

        return {"success": True, "message": f"Set '{name}' match successfully"}

    except Exception as e:
        frappe.log_error(f"Error setting conversation data: {e!s}", "Conversation Data")
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


ALLOWED_RESULT_CONTEXT_DOCTYPES = frozenset({
    "Agent Tool Call",
    "Agent Context Artifact",
})


def handle_get_result_context(reference_doctype: str, reference_name: str, **kwargs):
    """
    Get the full result context of an out-of-band message reference by its handle.

    Only explicitly allow-listed DocTypes are exposed, and the caller must have
    Frappe read permission on the requested document.
    """
    try:
        if not reference_doctype or not reference_name:
            return {"success": False, "error": "Both reference_doctype and reference_name are required."}

        if reference_doctype not in ALLOWED_RESULT_CONTEXT_DOCTYPES:
            frappe.log_error(
                f"get_result_context rejected for {reference_doctype}",
                "Security: get_result_context allow-list"
            )
            return {"success": False, "error": f"DocType '{reference_doctype}' is not accessible via get_result_context."}

        if not frappe.db.exists(reference_doctype, reference_name):
            return {"success": False, "error": f"Document {reference_name} of type {reference_doctype} not found."}

        doc = frappe.get_doc(reference_doctype, reference_name)

        if not frappe.has_permission(reference_doctype, "read", doc=doc):
            return {"success": False, "error": f"You do not have permission to read {reference_doctype} {reference_name}."}

        # If it's Agent Tool Call, retrieve the tool_result
        if reference_doctype == "Agent Tool Call":
            return {
                "success": True,
                "tool": doc.tool,
                "tool_args": doc.tool_args,
                "status": doc.status,
                "tool_result": doc.tool_result,
                "error_message": doc.error_message
            }

        # If it's Agent Context Artifact, retrieve payload
        if reference_doctype == "Agent Context Artifact":
            return {
                "success": True,
                "artifact_type": doc.artifact_type,
                "summary": doc.summary,
                "payload_json": doc.payload_json,
                "reference_doctype": doc.reference_doctype,
                "reference_name": doc.reference_name
            }

        # Unreachable because of the allow-list, but kept as defense-in-depth.
        return {"success": False, "error": "Unexpected DocType."}
    except Exception as e:
        frappe.log_error(f"Error in handle_get_result_context: {str(e)}", "SDK Functions Debug")
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
            provider_name = provider_doc.provider_name.lower()
            image_model = _get_default_image_model(provider_name)

        if not image_model:
            return {
                "success": False,
                "error": f"Image generation not supported for provider '{provider_doc.provider_name}'. Please configure an image_generation_model in agent settings."
            }

        # Normalize to LiteLLM format
        from huf.ai.providers.litellm import _normalize_model_name
        normalized_model = _normalize_model_name(image_model, agent_doc.provider)

        # Call LiteLLM image generation
        import litellm
        litellm.drop_params = True

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

                # Handle Pydantic model / Object access
                if hasattr(image_data, 'url'):
                    image_url = image_data.url
                if hasattr(image_data, 'b64_json'):
                    image_b64 = image_data.b64_json

                # Handle Dictionary access (if not an object)
                if not image_url and not image_b64 and isinstance(image_data, dict):
                    image_url = image_data.get('url')
                    image_b64 = image_data.get('b64_json')

                if not image_url and not image_b64:
                    continue

                # Download and save image
                image_bytes = None
                filename = f"generated_image_{idx + 1}.png"

                if image_url and image_url.startswith('http'):
                    # Download from URL (with SSRF protection)
                    from huf.ai.http_handler import validate_url
                    is_valid, _err = validate_url(image_url)
                    if not is_valid:
                        frappe.log_error(f"Image URL blocked by SSRF filter: {image_url}", "Image Generation")
                        continue
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

                # Create Agent Message first (we'll attach the file to it)
                message_doc = None
                if conversation_id and conversation_index is not None:
                    try:
                        # Get provider and model from agent
                        provider = agent_doc.provider
                        model = agent_doc.model

                        # Create Agent Message with kind "Image" first (without image)
                        message_doc = frappe.get_doc({
                            "doctype": "Agent Message",
                            "conversation": conversation_id,
                            "role": "agent",
                            "content": f"Generated image: {prompt}",
                            "kind": "Image",
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
                            f"Error creating Agent Message for generated image: {e!s}",
                            "Image Generation Message Creation"
                        )
                        # Continue even if message creation fails

                # Save file attached to the Agent Message (or conversation if message creation failed)
                if message_doc:
                    saved_file = save_file(
                        filename,
                        image_bytes,
                        "Agent Message",
                        message_doc.name,
                        is_private=False,
                        df="generated_image"
                    )
                else:
                    # Fallback: attach to conversation if message creation failed
                    saved_file = save_file(
                        filename,
                        image_bytes,
                        "Agent Conversation",
                        conversation_id or "Unknown",
                        is_private=False
                    )

                # save_file returns a File document object
                file_url = getattr(saved_file, 'file_url', None)
                file_id = getattr(saved_file, 'name', None)

                # Ensure we have a file_url
                if not file_url:
                    file_url = f"/files/{getattr(saved_file, 'file_name', filename)}"

                # Update the message with the file URL if message was created
                # This ensures the Attach Image field displays the image correctly
                if message_doc and file_url:
                    message_doc.db_set("generated_image", file_url)
                    frappe.db.commit()

                    # Emit socket event for new agent message (Image)
                    try:
                        frappe.publish_realtime(
                            event=f'conversation:{conversation_id}',
                            message={
                                "type": "new_agent_message",
                                "conversation_id": conversation_id,
                                "message_id": message_doc.name,
                                "kind": "Image",
                                "content": message_doc.content,
                                "generated_image": file_url,
                                "agent_run_id": kwargs.get("agent_run_id"),
                                "conversation_index": message_doc.conversation_index,
                            },
                            user=frappe.session.user,
                            after_commit=False
                        )
                    except Exception as e:
                        frappe.log_error(
                            f"Error emitting new_agent_message socket event: {e!s}",
                            "Image Generation Socket Event"
                        )

                images.append({
                    "url": file_url or f"/files/{filename}",
                    "file_id": file_id
                })

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
                    f"Error updating conversation total_messages: {e!s}",
                    "Image Generation Message Creation"
                )

        if not images:
            return {
                "success": False,
                "error": "Image generation succeeded but no images were returned"
            }

        print("Returned images: ", images)
        return {
            "success": True,
            "images": images,
            "message": f"Generated {len(images)} image(s) successfully"
        }

    except Exception as e:
        frappe.log_error(f"Image generation error: {e!s}", "Image Generation Tool")
        return {"success": False, "error": str(e)}


def _determine_ocr_strategy(file_path: str, file_type: str) -> str:
    """Determine OCR strategy based on file type."""
    # Check file extension if type not clear
    ext = file_path.lower().split('.')[-1] if '.' in file_path else ""

    # PDF and documents - use OCR endpoint
    if file_type in ["pdf", "application/pdf"] or ext == "pdf":
        return "ocr"

    # Images - use vision models
    if file_type.startswith("image/") or ext in ["jpg", "jpeg", "png", "webp", "gif"]:
        return "vision"

    # Default to vision for unknown types
    return "vision"


def _get_default_ocr_model(provider_name: str, strategy: str) -> str:
    """Get default OCR/Vision model for a provider."""
    if strategy == "ocr":
        # OCR endpoint models
        defaults = {
            "mistral": "mistral/mistral-ocr-latest",
            "azure": "azure_ai/ocr",
            "google": "vertex_ai/ocr",
            "vertex_ai": "vertex_ai/ocr",
        }
    else:
        # Vision models
        defaults = {
            "mistral": "mistral/mistral-small-latest",
            "openai": "gpt-4o",
            "google": "gemini/gemini-2.5-flash",
            "gemini": "gemini/gemini-2.5-flash",
            "anthropic": "claude-3-5-sonnet-20241022",
        }

    return defaults.get(provider_name.lower())


async def _process_with_ocr_endpoint(
    file_path: str,
    model: str,
    api_key: str,
    pages: str = None,
    include_images: bool = False
):
    """Process document using LiteLLM OCR endpoint."""
    import base64

    import litellm

    try:
        # Read file and encode to base64
        with open(file_path, "rb") as f:
            file_content = f.read()
            base64_content = base64.b64encode(file_content).decode('utf-8')

        # Determine document type
        ext = file_path.lower().split('.')[-1]
        mime_type = "application/pdf" if ext == "pdf" else f"image/{ext}"

        # Build OCR parameters
        ocr_params = {
            "model": model,
            "document": {
                "type": "document_url",
                "document_url": f"data:{mime_type};base64,{base64_content}"
            },
            "api_key": api_key
        }

        # Add optional parameters
        if pages:
            # Convert comma-separated string to list of integers
            page_list = [int(p.strip()) for p in pages.split(",")]
            ocr_params["pages"] = page_list

        if include_images:
            ocr_params["include_image_base64"] = True

        # Call LiteLLM OCR
        response = await asyncio.to_thread(
            litellm.ocr,
            **ocr_params
        )

        # Extract text from all pages
        all_text = []
        pages_data = []

        for page in response.pages:
            all_text.append(f"## Page {page.index + 1}\n\n{page.markdown}")
            pages_data.append({
                "index": page.index,
                "text": page.markdown,
                "dimensions": page.dimensions if hasattr(page, 'dimensions') else None
            })

        combined_text = "\n\n".join(all_text)

        return {
            "success": True,
            "text": combined_text,
            "pages": pages_data
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def _process_with_vision_model(
    file_path: str,
    model: str,
    api_key: str
):
    """Process image using LiteLLM vision models."""
    import base64

    import litellm

    try:
        # Read file and encode to base64
        with open(file_path, "rb") as f:
            file_content = f.read()
            base64_image = base64.b64encode(file_content).decode('utf-8')

        # Determine image type
        ext = file_path.lower().split('.')[-1]

        if ext == "pdf":
            mime_type = "application/pdf"
        elif ext in ["jpg", "jpeg", "png", "webp", "gif"]:
            mime_type = f"image/{ext}"
        else:
            mime_type = "image/jpeg"

        # Build vision request
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text from this image. Preserve formatting, structure, and layout. Return the text in markdown format."
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:{mime_type};base64,{base64_image}"
                    }
                ]
            }
        ]

        # Call LiteLLM completion with vision
        response = await asyncio.to_thread(
            litellm.completion,
            model=model,
            messages=messages,
            api_key=api_key
        )

        extracted_text = response.choices[0].message.content

        return {
            "success": True,
            "text": extracted_text,
            "pages": [{"index": 0, "text": extracted_text}]
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

@frappe.whitelist()
async def handle_ocr_document(
    file_id: str = None,
    file_url: str = None,
    pages: str = None,
    include_images: bool = False,
    model: str = None,
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Extract text from documents and images using OCR.
    
    Intelligently routes to:
    - LiteLLM OCR endpoint for PDFs (multi-page documents)
    - Vision models for single images (better context understanding)
    
    Args:
        file_id: File document ID (preferred)
        file_url: File URL/path (alternative)
        pages: Comma-separated page numbers (e.g., "0,1,2") - PDFs only
        include_images: Extract images from document (PDFs only)
        model: Optional model override
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context
    
    Returns:
        dict: {
            "success": bool,
            "text": str,              # Extracted text in markdown
            "pages": list,            # Page-by-page breakdown (PDFs)
            "strategy": str,          # "ocr" or "vision"
            "file_id": str,
            "message_id": str,
            "model": str
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

        # Get file
        file_doc = None
        if file_id:
            try:
                file_doc = frappe.get_doc("File", file_id)
            except Exception as e:
                return {"success": False, "error": f"File not found: {e!s}"}
        elif file_url:
            # Try to find file by URL
            file_path = file_url.replace("/files/", "")
            file_doc = frappe.db.get_value("File",
                {"file_url": file_url},
                ["name"], as_dict=True)
            if file_doc:
                file_doc = frappe.get_doc("File", file_doc.name)
            else:
                # Try by file name
                file_doc = frappe.db.get_value("File",
                    {"file_name": file_path},
                    ["name"], as_dict=True)
                if file_doc:
                    file_doc = frappe.get_doc("File", file_doc.name)

        if not file_doc:
            return {"success": False, "error": "Either file_id or file_url is required"}

        # Get file path and type
        file_path = file_doc.get_full_path()
        file_type = file_doc.file_type or ""
        file_name = file_doc.file_name or ""

        # Determine strategy
        strategy = _determine_ocr_strategy(file_path, file_type)

        # Override strategy for Google/Gemini: Use Vision (Multimodal) for PDFs too
        provider_name = provider_doc.provider_name.lower()
        if provider_name in ["google", "gemini"] and (strategy == "ocr" or file_path.lower().endswith(".pdf")):
            strategy = "vision"

        # Determine model
        ocr_model = None
        if model:
            ocr_model = model
        else:
            provider_name = provider_doc.provider_name.lower()
            ocr_model = _get_default_ocr_model(provider_name, strategy)

        if not ocr_model:
            return {
                "success": False,
                "error": f"OCR not supported for provider '{provider_doc.provider_name}' with strategy '{strategy}'. Please provide a model parameter."
            }

        # Normalize model name
        from huf.ai.providers.litellm import _normalize_model_name
        normalized_model = _normalize_model_name(ocr_model, agent_doc.provider)

        # Route to appropriate method
        if strategy == "ocr":
            result = await _process_with_ocr_endpoint(
                file_path, normalized_model, api_key, pages, include_images
            )
        else:
            result = await _process_with_vision_model(
                file_path, normalized_model, api_key
            )

        if not result["success"]:
            return result

        extracted_text = result["text"]
        pages_data = result.get("pages", [])

        # Create Agent Message with extracted text
        message_doc = None
        if conversation_id:
            try:
                # Get conversation_index
                last_index = frappe.db.sql("""
                    SELECT MAX(conversation_index) as last_index
                    FROM `tabAgent Message`
                    WHERE conversation = %s
                """, (conversation_id,), as_dict=1)

                conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1

                # Create Agent Message
                message_doc = frappe.get_doc({
                    "doctype": "Agent Message",
                    "conversation": conversation_id,
                    "role": "agent",
                    "content": f"Extracted text from {file_name}:\n\n{extracted_text[:500]}{'...' if len(extracted_text) > 500 else ''}",
                    "kind": "Message",
                    "agent": agent_name,
                    "provider": agent_doc.provider,
                    "model": agent_doc.model,
                    "agent_run": kwargs.get("agent_run_id"),
                    "conversation_index": conversation_index,
                    "is_agent_message": 1,
                    "user": "Agent"
                })
                message_doc.insert(ignore_permissions=True)

                # Update conversation
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET total_messages = %s, last_activity = NOW()
                    WHERE name = %s
                """, (conversation_index, conversation_id))

                frappe.db.commit()

                # Emit socket event
                try:
                    frappe.publish_realtime(
                        event=f'conversation:{conversation_id}',
                        message={
                            "type": "new_agent_message",
                            "conversation_id": conversation_id,
                            "message_id": message_doc.name,
                            "kind": "Message",
                            "content": message_doc.content,
                            "conversation_index": conversation_index,
                        },
                        user=frappe.session.user,
                        after_commit=False
                    )
                except Exception as e:
                    frappe.log_error(
                        f"Error emitting new_agent_message socket event: {e!s}",
                        "OCR Socket Event"
                    )
            except Exception as e:
                frappe.log_error(
                    f"Error creating Agent Message for OCR: {e!s}",
                    "OCR Message Creation"
                )

        return {
            "success": True,
            "text": extracted_text,
            "pages": pages_data,
            "strategy": strategy,
            "file_id": file_doc.name,
            "file_name": file_name,
            "message_id": message_doc.name if message_doc else None,
            "model": normalized_model,
            "conversation_id": conversation_id
        }

    except Exception as e:
        frappe.log_error(f"OCR error: {e!s}", "OCR Tool")
        return {"success": False, "error": str(e)}

def _get_default_voice(provider_name: str) -> str:
    """Get default voice for a provider."""
    defaults = {
        "openai": "alloy",
        "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
        "google": "Puck",
        "vertex_ai": "Puck",
        "gemini": "Puck",
        "azure": "en-US-JennyNeural",
        "mistral": "mistral-male-1"
    }
    return defaults.get(provider_name.lower(), "alloy")

def _get_default_tts_model(provider_name: str) -> str:
    """
    Get default TTS model for a provider.
    
    Based on LiteLLM documentation: https://docs.litellm.ai/docs/audio_speech
    
    Args:
        provider_name: Lowercase provider name (e.g., "openai", "google", "elevenlabs")
    
    Returns:
        str: Default TTS model name, or None if not supported
    """
    defaults = {
        "openai": "tts-1",
        "azure": "tts-1",
        "google": "gemini/gemini-2.5-flash-preview-tts",
        "gemini": "gemini/gemini-2.5-flash-preview-tts",
        "vertex_ai": "vertex_ai/gemini-2.5-flash-preview-tts",
        "elevenlabs": "elevenlabs/eleven_multilingual_v2",
        "aws": "aws/polly",
        "minimax": "minimax/speech-01",
    }

    return defaults.get(provider_name.lower())

_TTS_ENV_VAR_PROVIDERS: dict[str, str] = {
    "google":     "GEMINI_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "vertex_ai":  "GEMINI_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "minimax":    "MINIMAX_API_KEY",
}


def _resolve_tts_config(
    agent_doc,
    tool_model: str | None = None,
    tool_voice: str | None = None,
) -> dict:
    """
    Resolve the TTS model, voice, API key, and provider for audio generation.

    Priority (highest → lowest):

    1. **Tool-call parameter** - ``model`` / ``voice`` values passed by the
       agent at runtime (highest precedence; lets individual calls override).
    2. **Agent-level TTS configuration** - ``agent.tts_model`` / ``agent.tts_voice``
       fields set on the Agent DocType.  The API key is fetched from the *TTS
       model's own provider* (``AI Model → AI Provider``), which may be a
       completely different provider from the agent's main conversational model.
    3. **Provider default** - ``_get_default_tts_model`` / ``_get_default_voice``
       derived from the agent's main provider (fallback when nothing else is set).

    Args:
        agent_doc:   Loaded ``Agent`` Frappe document.
        tool_model:  Optional model name supplied by the tool call at runtime.
        tool_voice:  Optional voice name supplied by the tool call at runtime.

    Returns:
        dict:
            - ``tts_model``     - Normalised LiteLLM model string.
            - ``voice``         - Voice identifier for the TTS provider.
            - ``api_key``       - Decrypted API key for the TTS provider.
            - ``provider_name`` - Lowercase provider name (used for env-var routing).
            - ``provider_doc``  - Loaded ``AI Provider`` document for the TTS provider.
            - ``source``        - How the model was resolved: ``"tool_param"``,
                                  ``"agent_config"``, or ``"provider_default"``.

    Raises:
        ValueError: If no TTS model can be determined and the provider does not
                    natively support TTS.
    """
    from huf.ai.providers.litellm import _normalize_model_name

    if tool_model:
        provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
        api_key = provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(
                f"API key is not configured for provider "
                f"'{provider_doc.provider_name}'. Please add it to the AI Provider document."
            )
        provider_name = provider_doc.provider_name.lower()
        voice = tool_voice or _get_default_voice(provider_name)
        normalized = _normalize_model_name(tool_model, agent_doc.provider)
        return {
            "tts_model":     normalized,
            "voice":         voice,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  provider_doc,
            "source":        "tool_param",
        }

    if getattr(agent_doc, "tts_model", None):
        tts_model_doc = frappe.get_doc("AI Model", agent_doc.tts_model)

        if not tts_model_doc.provider:
            raise ValueError(
                f"TTS model '{agent_doc.tts_model}' has no provider linked. "
                f"Please set a provider on the AI Model document."
            )

        tts_provider_doc = frappe.get_doc("AI Provider", tts_model_doc.provider)
        api_key = tts_provider_doc.get_password("api_key")

        if not api_key:
            raise ValueError(
                f"API key is not configured for TTS provider "
                f"'{tts_provider_doc.provider_name}'. "
                f"Please add the API key to that AI Provider document."
            )

        provider_name = tts_provider_doc.provider_name.lower()

        voice = (
            getattr(agent_doc, "tts_voice", None)
            or _get_default_voice(provider_name)
            or tool_voice
        )

        normalized = _normalize_model_name(
            tts_model_doc.model_name, tts_model_doc.provider
        )
        return {
            "tts_model":     normalized,
            "voice":         voice,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  tts_provider_doc,
            "source":        "agent_config",
        }

    provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
    api_key = provider_doc.get_password("api_key")

    if not api_key:
        raise ValueError(
            f"API key is not configured for provider "
            f"'{provider_doc.provider_name}'. Please add it to the AI Provider document."
        )

    provider_name = provider_doc.provider_name.lower()
    tts_model = _get_default_tts_model(provider_name)

    if not tts_model:
        raise ValueError(
            f"Text-to-speech is not natively supported by provider "
            f"'{provider_doc.provider_name}'. Please either:\n"
            f"  \u2022 Set a dedicated 'TTS Model' on the Agent "
            f"(Advanced Settings \u2192 Audio Generation), or\n"
            f"  \u2022 Pass a 'model' parameter directly to the generate_audio tool."
        )

    voice = tool_voice or _get_default_voice(provider_name)
    normalized = _normalize_model_name(tts_model, agent_doc.provider)
    return {
        "tts_model":     normalized,
        "voice":         voice,
        "api_key":       api_key,
        "provider_name": provider_name,
        "provider_doc":  provider_doc,
        "source":        "provider_default",
    }

def _get_default_stt_model(provider_name: str) -> str:
    """
    Get default STT model for a provider.
    """
    defaults = {
        "openai": "whisper-1",
        "azure": "whisper-1",
        "groq": "groq/whisper-large-v3",
        "deepgram": "deepgram/nova-2",
    }
    return defaults.get(provider_name.lower())

def _resolve_stt_config(
    agent_doc,
    tool_model: str | None = None,
) -> dict:
    """
    Resolve the STT model, API key, and provider for audio transcription.
    Priority (highest → lowest):
    1. Tool-call parameter
    2. Agent-level STT configuration
    3. Provider default
    """
    from huf.ai.providers.litellm import _normalize_model_name

    if tool_model:
        stt_provider_name = None
        search_model = tool_model
        if "/" in search_model:
            search_model = search_model.split("/")[-1]

        model_doc = frappe.get_all("AI Model", filters={"name": search_model}, fields=["provider"])
        if model_doc:
            stt_provider_name = model_doc[0].provider
        elif "/" in tool_model:
            provider_slug = tool_model.split("/")[0]
            provs = frappe.get_all("AI Provider", filters={"slug": provider_slug}, fields=["name"])
            if provs:
                stt_provider_name = provs[0].name

        if not stt_provider_name:
            stt_provider_name = agent_doc.provider

        provider_doc = frappe.get_doc("AI Provider", stt_provider_name)
        api_key = provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

        provider_name = provider_doc.provider_name.lower()
        normalized = _normalize_model_name(tool_model, stt_provider_name)
        return {
            "stt_model":     normalized,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  provider_doc,
            "source":        "tool_param",
        }

    if getattr(agent_doc, "stt_model", None):
        stt_model_doc = frappe.get_doc("AI Model", agent_doc.stt_model)
        if not stt_model_doc.provider:
            raise ValueError(f"STT model '{agent_doc.stt_model}' has no provider linked.")

        stt_provider_doc = frappe.get_doc("AI Provider", stt_model_doc.provider)
        api_key = stt_provider_doc.get_password("api_key")
        if not api_key:
            raise ValueError(f"API key is not configured for STT provider '{stt_provider_doc.provider_name}'.")

        provider_name = stt_provider_doc.provider_name.lower()
        normalized = _normalize_model_name(stt_model_doc.model_name, stt_model_doc.provider)
        return {
            "stt_model":     normalized,
            "api_key":       api_key,
            "provider_name": provider_name,
            "provider_doc":  stt_provider_doc,
            "source":        "agent_config",
        }

    provider_doc = frappe.get_doc("AI Provider", agent_doc.provider)
    api_key = provider_doc.get_password("api_key")
    if not api_key:
        raise ValueError(f"API key is not configured for provider '{provider_doc.provider_name}'.")

    provider_name = provider_doc.provider_name.lower()
    stt_model = _get_default_stt_model(provider_name)

    if not stt_model:
        stt_model = "whisper-1" # Safe ultimate fallback

    normalized = _normalize_model_name(stt_model, agent_doc.provider)
    return {
        "stt_model":     normalized,
        "api_key":       api_key,
        "provider_name": provider_name,
        "provider_doc":  provider_doc,
        "source":        "provider_default",
    }


@frappe.whitelist()
async def handle_generate_audio(
    input: str,
    voice: str = None,
    model: str = None,
    speed: float = 1.0,
    response_format: str = "mp3",
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Generate audio (speech) from text using LiteLLM's speech() function.
    
    Uses LiteLLM's speech() function. The model used is either:
    1. The explicitly provided model parameter, OR
    2. An auto-detected suitable TTS model based on the provider
    
    Args:
        input: Text to convert to speech (required)
        voice: Voice to use (e.g., "alloy", "echo", "fable", "onyx", "nova", "shimmer")
        model: Optional model name (e.g., "tts-1", "tts-1-hd", "gemini-2.5-flash-preview-tts")
        speed: Speech speed from 0.25 to 4.0 (default: 1.0)
        response_format: Audio format (mp3, opus, aac, flac, wav, pcm)
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context
    
    Returns:
        dict: {
            "success": bool,
            "audio": {
                "url": str,
                "file_id": str,
                "message_id": str,
                "input_text": str,
                "voice": str,
                "speed": float,
                "format": str,
                "model": str
                "model_source": str,
                "tts_provider": str,
            },
            "message": str,
            "conversation_id": str
        }
    """
    try:
        # Get agent configuration from context
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)

        try:
            tts_config = _resolve_tts_config(
                agent_doc, tool_model=model, tool_voice=voice
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        normalized_model = tts_config["tts_model"]
        voice            = tts_config["voice"]
        api_key          = tts_config["api_key"]
        provider_name    = tts_config["provider_name"]
        tts_source       = tts_config["source"]
        tts_provider_doc = tts_config["provider_doc"]

        import litellm

        speech_params: dict = {
            "model": normalized_model,
            "input": input,
            "voice": voice,
        }

        if provider_name in _TTS_ENV_VAR_PROVIDERS:
            import os
            os.environ[_TTS_ENV_VAR_PROVIDERS[provider_name]] = api_key
        else:
            speech_params["api_key"] = api_key

        if speed != 1.0:
            speech_params["speed"] = speed
        if response_format != "mp3":
            speech_params["response_format"] = response_format

        # Call LiteLLM speech (returns HttpxBinaryResponseContent)
        response = await asyncio.to_thread(
            litellm.speech,
            **speech_params
        )

        # Get audio content from response
        # LiteLLM speech() returns HttpxBinaryResponseContent
        audio_bytes = response.content

        # Get conversation_index for message ordering
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

        # Generate filename
        filename = f"generated_audio_{conversation_index}.{response_format}"

        # Create Agent Message first (we'll attach the file to it)
        message_doc = None
        if conversation_id and conversation_index is not None:
            try:
                # Get provider and model from agent
                provider = agent_doc.provider
                model_name = agent_doc.model

                # Create Agent Message with kind "Audio"
                message_doc = frappe.get_doc({
                    "doctype": "Agent Message",
                    "conversation": conversation_id,
                    "role": "agent",
                    "content": f"Generated audio: {input[:100]}{'...' if len(input) > 100 else ''}",
                    "kind": "Audio",
                    "agent": agent_name,
                    "provider": provider,
                    "model": model_name,
                    "agent_run": kwargs.get("agent_run_id"),
                    "conversation_index": conversation_index,
                    "is_agent_message": 1,
                    "user": "Agent",
                    "tts_voice": voice
                })
                message_doc.insert(ignore_permissions=True)

                if tts_source == "agent_config" and getattr(agent_doc, "tts_model", None):
                    frappe.db.set_value(
                        "Agent Message", message_doc.name,
                        "tts_model", agent_doc.tts_model,
                        update_modified=False
                    )
                    message_doc.tts_model = agent_doc.tts_model

            except Exception as e:
                frappe.log_error(
                    f"Error creating Agent Message for generated audio: {e!s}",
                    "Audio Generation Message Creation"
                )
                message_doc = None

        # Save file attached to the Agent Message
        if message_doc:
            saved_file = save_file(
                filename,
                audio_bytes,
                "Agent Message",
                message_doc.name,
                is_private=False,
                df="generated_audio"
            )
        else:
            # Fallback: attach to conversation if message creation failed
            saved_file = save_file(
                filename,
                audio_bytes,
                "Agent Conversation",
                conversation_id or "Unknown",
                is_private=False
            )

        # Get file URL
        file_url = getattr(saved_file, 'file_url', None)
        file_id = getattr(saved_file, 'name', None)

        if not file_url:
            file_url = f"/files/{getattr(saved_file, 'file_name', filename)}"

        # Update the message with the file URL
        if message_doc and file_url:
            message_doc.db_set("generated_audio", file_url)
            frappe.db.commit()

            # Emit socket event for new agent message (Audio)
            try:
                frappe.publish_realtime(
                    event=f'conversation:{conversation_id}',
                    message={
                        "type": "new_agent_message",
                        "conversation_id": conversation_id,
                        "message_id": message_doc.name,
                        "kind": "Audio",
                        "content": message_doc.content,
                        "generated_audio": file_url,
                        "agent_run_id": kwargs.get("agent_run_id"),
                        "conversation_index": message_doc.conversation_index,
                    },
                    user=frappe.session.user,
                    after_commit=False
                )
            except Exception as e:
                frappe.log_error(
                    f"Error emitting new_agent_message socket event: {e!s}",
                    "Audio Generation Socket Event"
                )

        # Update conversation total_messages
        if conversation_id and conversation_index is not None:
            try:
                frappe.db.sql("""
                    UPDATE `tabAgent Conversation`
                    SET total_messages = %s, last_activity = NOW()
                    WHERE name = %s
                """, (conversation_index, conversation_id))
            except Exception as e:
                frappe.log_error(
                    f"Error updating conversation total_messages: {e!s}",
                    "Audio Generation Message Creation"
                )

        return {
            "success": True,
            "audio": {
                "url": file_url,
                "file_id": file_id,
                "message_id": message_doc.name if message_doc else None,
                "input_text": input,
                "voice": voice,
                "speed": speed,
                "format": response_format,
                "model": normalized_model,
                "model_source": tts_source,
                "tts_provider": tts_provider_doc.provider_name,
            },
            "message": "Generated audio successfully",
            "conversation_id": conversation_id
        }

    except Exception as e:
        frappe.log_error(title="Audio Generation Tool", message=f"Audio generation error: {e!s}")
        return {"success": False, "error": str(e)}

@frappe.whitelist()
async def handle_transcribe_audio(
    file_id: str = None,
    file_url: str = None,
    language: str = None,
    model: str = None,
    agent_name: str = None,
    conversation_id: str = None,
    **kwargs
):
    """
    Transcribe audio using LiteLLM's transcription function.
    
    Uses LiteLLM's transcription() function. The model used is either:
    1. The explicitly provided model parameter, OR
    2. An auto-detected suitable transcription model based on the provider
    
    Args:
        file_id: File document ID (preferred) - File must exist in Frappe
        file_url: File URL/path (alternative) - e.g., "/files/audio.mp3"
        language: Optional language code (e.g., "en", "es", "fr") - ISO 639-1 format
        model: Optional model name (e.g., "whisper-1", "whisper-large-v3")
               If not provided, defaults based on provider
        agent_name: Automatically passed from context
        conversation_id: Automatically passed from context
    
    Returns:
        dict: {
            "success": bool,
            "text": str,
            "file_id": str,
            "message_id": str,
            "language": str
        }
    """
    try:
        # Get message_id for upsert logic
        message_id = kwargs.get("message_id")

        # Get agent configuration from context
        if not agent_name:
            return {"success": False, "error": "Agent name not found in context"}

        agent_doc = frappe.get_doc("Agent", agent_name)

        # Get audio file
        file_doc = None
        if file_id:
            try:
                file_doc = frappe.get_doc("File", file_id)
            except Exception as e:
                return {"success": False, "error": f"File not found: {e!s}"}
        elif file_url:
            # Try to find file by URL
            try:
                file_doc = frappe.get_doc("File", {"file_url": file_url})
            except Exception:
                # Try alternative lookup
                file_name = file_url.replace("/files/", "")
                file_doc = frappe.get_doc("File", {"file_name": file_name})

            if not file_doc:
                return {"success": False, "error": f"File not found at URL: {file_url}"}
        else:
            return {"success": False, "error": "Either file_id or file_url is required"}

        # Get file path for LiteLLM
        # LiteLLM transcription accepts file path or file-like object
        try:
            file_path = file_doc.get_full_path()
        except Exception as e:
            return {"success": False, "error": f"Error getting file path: {e!s}"}

        # Determine transcription model
        try:
            stt_config = _resolve_stt_config(agent_doc, tool_model=model)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}

        normalized_model = stt_config["stt_model"]
        api_key          = stt_config["api_key"]
        provider_name    = stt_config["provider_name"]
        stt_source       = stt_config["source"]
        stt_provider_doc = stt_config["provider_doc"]

        # Call LiteLLM transcription
        import litellm

        if provider_name in ["google", "gemini", "vertex_ai"]:
            import base64
            import mimetypes

            with open(file_path, "rb") as audio_file:
                audio_data = audio_file.read()

            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "audio/mp3"

            if file_path.lower().endswith(".webm") or mime_type == "video/webm":
                mime_type = "audio/webm"

            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            audio_url = f"data:{mime_type};base64,{base64_audio}"

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please transcribe this audio exactly as it is spoken. Do not add any extra commentary or formatting. If there are multiple languages, transcribe them as spoken. If it is silent, just write [Silence]."},
                        {"type": "image_url", "image_url": {"url": audio_url}}
                    ]
                }
            ]

            import os
            env_var = _TTS_ENV_VAR_PROVIDERS.get(provider_name, "GEMINI_API_KEY")
            os.environ[env_var] = api_key

            try:
                response = await asyncio.to_thread(
                    litellm.completion,
                    model=normalized_model,
                    messages=messages,
                    api_key=api_key
                )
                transcribed_text = response.choices[0].message.content
            except Exception as e:
                return {"success": False, "error": f"Transcription failed: {e!s}"}

        else:
            # Standard transcription handling (OpenAI, Deepgram, Groq, etc.)
            transcription_params = {
                "model": normalized_model,
                "file": file_path,
                "api_key": api_key
            }

            # Add optional parameters
            if language:
                transcription_params["language"] = language

            # Call LiteLLM transcription
            def _sync_transcribe(params):
                with open(file_path, "rb") as audio_file:
                    params["file"] = audio_file
                    return litellm.transcription(**params)

            try:
                response = await asyncio.to_thread(_sync_transcribe, transcription_params)
            except Exception as e:
                return {"success": False, "error": f"Transcription failed: {e!s}"}

            # Extract text from response
            # LiteLLM transcription returns a dict with 'text' key or object
            if hasattr(response, "text"):
                transcribed_text = response.text
            elif isinstance(response, dict):
                transcribed_text = response.get("text", "")
            else:
                 transcribed_text = str(response)

        if not transcribed_text:
            return {"success": False, "error": "Transcription returned empty result"}

        # Create Agent Message with transcription result
        message_doc = None
        if conversation_id:
            try:
                # Get conversation_index
                last_index = frappe.db.sql("""
                    SELECT MAX(conversation_index) as last_index
                    FROM `tabAgent Message`
                    WHERE conversation = %s
                """, (conversation_id,), as_dict=1)

                conversation_index = (last_index[0].last_index if last_index and last_index[0].last_index is not None else 0) + 1

                # Create or Update Agent Message
                if message_id and frappe.db.exists("Agent Message", message_id):
                    message_doc = frappe.get_doc("Agent Message", message_id)
                    message_doc.content = transcribed_text
                    if not message_doc.kind: message_doc.kind = "Audio"
                    if stt_source == "agent_config" and getattr(agent_doc, "stt_model", None):
                        message_doc.stt_model = agent_doc.stt_model
                    message_doc.save(ignore_permissions=True)

                else:
                    message_doc = frappe.get_doc({
                        "doctype": "Agent Message",
                        "conversation": conversation_id,
                        "role": "user",
                        "content": transcribed_text,
                        "kind": "Audio",
                        "agent": agent_name,
                        "provider": agent_doc.provider,
                        "model": agent_doc.model,
                        "agent_run": kwargs.get("agent_run_id"),
                        "conversation_index": conversation_index,
                        "is_agent_message": 0,
                        "user": frappe.session.user
                    })
                    if stt_source == "agent_config" and getattr(agent_doc, "stt_model", None):
                        message_doc.stt_model = agent_doc.stt_model
                    message_doc.insert(ignore_permissions=True)

                # Check if file is already attached to this message
                if file_doc and message_doc:
                    if not file_doc.attached_to_name:
                        file_doc.db_set("attached_to_name", message_doc.name)
                        file_doc.db_set("attached_to_doctype", "Agent Message")
                        file_doc.db_set("is_private", 0)

                # Update conversation total_messages
                if not message_id:
                    frappe.db.sql("""
                        UPDATE `tabAgent Conversation`
                        SET total_messages = %s, last_activity = NOW()
                        WHERE name = %s
                    """, (conversation_index, conversation_id))
                else:
                    frappe.db.set_value("Agent Conversation", conversation_id, "last_activity", frappe.utils.now())

                frappe.db.commit()

                # Emit socket event for new message
                try:
                    frappe.publish_realtime(
                        event=f'conversation:{conversation_id}',
                        message={
                            "type": "update_message" if message_id else "new_user_message",
                            "conversation_id": conversation_id,
                            "message_id": message_doc.name,
                            "content": transcribed_text,
                            "kind": "Audio",
                            "file": {
                                "file_name": file_doc.file_name,
                                "file_url": file_doc.file_url
                            } if file_doc else None,
                            "conversation_index": conversation_index,
                        },
                        user=frappe.session.user,
                        after_commit=False
                    )
                except Exception as e:
                    frappe.log_error(
                        f"Error emitting new_user_message socket event: {e!s}",
                        "Audio Transcription Socket Event"
                    )

            except Exception as e:
                frappe.log_error(
                    f"Error creating Agent Message for transcription: {e!s}",
                    "Audio Transcription Message Creation"
                )

        return {
            "success": True,
            "text": transcribed_text,
            "file_id": file_doc.name,
            "message_id": message_doc.name if message_doc else None,
            "language": language or "auto-detected",
            "model": normalized_model
        }

    except Exception as e:
        frappe.log_error(f"Audio transcription error: {e!s}", "Audio Transcription Tool")
        return {"success": False, "error": str(e)}
