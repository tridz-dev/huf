"""
Deterministic tool executor for Flow Engine tool.call nodes.

Executes Agent Tool Function tools without LLM involvement, reusing
the same internal handler logic used by sdk_tools so results match
agent tool calls.
"""

import json

import frappe
from frappe import _


def execute(tool_name: str, args: dict, user: str = None) -> dict:
	"""
	Execute an Agent Tool Function deterministically.

	Finds the tool by tool_name, resolves its handler function,
	and executes it with the provided arguments. Uses the same
	handler resolution as sdk_tools.create_agent_tools().

	Args:
	    tool_name: Must match an Agent Tool Function.tool_name
	    args: Arguments to pass to the tool handler
	    user: User to execute as (defaults to current session user)

	Returns:
	    dict with keys:
	        success (bool): Whether execution succeeded
	        result (any): Tool result if successful
	        error (str): Error message if failed
	"""
	if user:
		original_user = frappe.session.user
		frappe.set_user(user)

	try:
		return _execute_tool(tool_name, args)
	finally:
		if user:
			frappe.set_user(original_user)


def _execute_tool(tool_name: str, args: dict) -> dict:
	"""Internal tool execution logic."""
	# Find the Agent Tool Function doc
	tool_doc = frappe.db.get_value(
		"Agent Tool Function",
		{"tool_name": tool_name},
		["name", "types", "function_path", "reference_doctype", "agent", "base_url"],
		as_dict=True,
	)

	if not tool_doc:
		return {"success": False, "error": f"Tool '{tool_name}' not found in Agent Tool Function"}

	# Resolve the function path based on tool type
	function_path = _resolve_function_path(tool_doc)
	if not function_path:
		return {"success": False, "error": f"Cannot resolve handler for tool type '{tool_doc.types}'"}

	# Import the handler function
	from huf.ai.sdk_tools import get_function_from_name

	handler = get_function_from_name(function_path)
	if not handler:
		return {"success": False, "error": f"Handler function not found: {function_path}"}

	# Build the arguments, injecting extra_args as needed
	call_args = dict(args) if args else {}
	_inject_extra_args(call_args, tool_doc)

	# Execute the function
	try:
		import inspect

		sig = inspect.signature(handler)
		accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

		if accepts_kwargs:
			result = handler(**call_args)
		else:
			valid_params = set(sig.parameters.keys())
			filtered_args = {k: v for k, v in call_args.items() if k in valid_params}
			result = handler(**filtered_args)

		# Handle async results
		import asyncio

		if asyncio.iscoroutine(result):
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			try:
				result = loop.run_until_complete(result)
			finally:
				loop.close()

		# Normalize result
		if hasattr(result, "as_dict"):
			result = result.as_dict()

		if isinstance(result, (dict, list)):
			return {"success": True, "result": result}

		return {"success": True, "result": str(result) if result is not None else None}

	except Exception as e:
		frappe.log_error(f"Flow tool execution error for '{tool_name}': {str(e)}", "Flow Tool Executor")
		return {"success": False, "error": str(e)}


def _resolve_function_path(tool_doc: dict) -> str | None:
	"""Resolve the function path for a given tool type, matching sdk_tools logic."""
	tool_type = tool_doc.get("types")

	if tool_type in ("Custom Function", "App Provided"):
		return tool_doc.get("function_path")

	# Map standard types to their handlers (same as sdk_tools.create_agent_tools)
	type_to_handler = {
		"Get List": "huf.ai.sdk_tools.handle_get_list",
		"Get Document": "huf.ai.sdk_tools.handle_get_document",
		"Update Document": "huf.ai.sdk_tools.handle_update_document",
		"Create Document": "huf.ai.sdk_tools.handle_create_document",
		"Delete Document": "huf.ai.sdk_tools.handle_delete_document",
		"Get Multiple Documents": "huf.ai.sdk_tools.handle_get_documents",
		"Create Multiple Documents": "huf.ai.sdk_tools.handle_create_documents",
		"Update Multiple Documents": "huf.ai.sdk_tools.handle_update_documents",
		"Delete Multiple Documents": "huf.ai.sdk_tools.handle_delete_documents",
		"Submit Document": "huf.ai.sdk_tools.handle_submit_document",
		"Cancel Document": "huf.ai.sdk_tools.handle_cancel_document",
		"Get Value": "huf.ai.sdk_tools.handle_get_value",
		"Set Value": "huf.ai.sdk_tools.handle_set_value",
		"Get Report Result": "huf.ai.sdk_tools.handle_get_report_result",
		"GET": "huf.ai.http_handler.handle_get_request",
		"POST": "huf.ai.http_handler.handle_post_request",
		"Run Agent": "huf.ai.sdk_tools.handle_run_agent",
		"Attach File to Document": "huf.ai.sdk_tools.handle_attach_file_to_document",
		"Get Conversation Data": "huf.ai.sdk_tools.handle_get_conversation_data",
		"Set Conversation Data": "huf.ai.sdk_tools.handle_set_conversation_data",
		"Load Conversation Data": "huf.ai.sdk_tools.handle_load_conversation_data",
	}

	return type_to_handler.get(tool_type)


def _inject_extra_args(args: dict, tool_doc: dict):
	"""Inject extra arguments based on tool type, matching sdk_tools logic."""
	tool_type = tool_doc.get("types")

	if tool_type == "Attach File to Document" and tool_doc.get("reference_doctype"):
		args.setdefault("reference_doctype", tool_doc["reference_doctype"])

	elif tool_type in (
		"Get Document",
		"Get Multiple Documents",
		"Get List",
		"Create Document",
		"Create Multiple Documents",
		"Update Document",
		"Update Multiple Documents",
		"Delete Document",
		"Delete Multiple Documents",
	):
		if tool_doc.get("reference_doctype"):
			args.setdefault("reference_doctype", tool_doc["reference_doctype"])

	elif tool_type == "Run Agent" and tool_doc.get("agent"):
		args.setdefault("agent_name", tool_doc["agent"])

	elif tool_type in ("GET", "POST"):
		args.setdefault("tool_name", tool_doc.get("name"))
