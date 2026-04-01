"""
SDK tool creation and wiring for Huf Agent.

This module is responsible for:
1. Creating FunctionTool instances from Agent Tool Function documents
2. Resolving tool handler functions by dotted path
3. Permission checks for Guest users

Handler implementations live in huf.ai.handlers.* modules.
Backward-compatible re-exports are at the bottom of this file.
"""

import asyncio
import inspect
import json
import re
from typing import Any, Callable

import frappe
from agents import FunctionTool

from huf.ai.tool_registry import PermissionAwareToolRegistry
from huf.ai.tool_types import DOCTYPE_BOUND_TYPES, TOOL_TYPE_HANDLERS

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
	"""Guard function to block dangerous tools for Guest users."""
	user = frappe.session.user

	# Guest cannot use mutating tools unless explicitly allowed
	if user == "Guest":
		if allowed_for_guest:
			return {"allowed": True}

		if tool_type in MUTATING_TOOL_TYPES:
			return {
				"allowed": False,
				"error": f"Guest users cannot use {tool_type} tools. Please log in.",
			}

	return {"allowed": True}


def _call_with_filtered_args(func: Callable, args: dict):
	"""Call a function with only the parameters it accepts."""
	sig = inspect.signature(func)
	if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
		return func(**args)
	valid = set(sig.parameters.keys())
	return func(**{k: v for k, v in args.items() if k in valid})


def create_agent_tools(agent) -> list[FunctionTool]:
	"""
	Create function tools for Huf Agent.

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
				title="MCP Tool Loading Error",
				message=f"Error loading MCP tools for agent: {str(e)}",
			)

	# Load native tools from Agent Tool Function documents
	allowed_tool_docs = PermissionAwareToolRegistry.get_allowed_tools(agent, frappe.session.user)

	for function_doc in allowed_tool_docs:
		try:
			function_path = None
			if function_doc.types in ["Custom Function", "App Provided"]:
				if not function_doc.function_path:
					continue
				function_path = function_doc.function_path
			elif function_doc.types == "Client Side Tool":
				function_path = "huf.ai.client_side_tool.client_side_function"
				if not function_doc.function_name:
					continue
			else:
				# Use the centralized tool-type-to-handler mapping
				function_path = TOOL_TYPE_HANDLERS.get(function_doc.types)
				if not function_path:
					continue

			params = {}
			if function_doc.params:
				try:
					params = json.loads(function_doc.params)
				except Exception as e:
					frappe.log_error(
						title="SDK Functions Debug",
						message=f"Error parsing params for {function_doc.name}: {str(e)}",
					)

			if "additionalProperties" in params:
				del params["additionalProperties"]

			extra_args = {}
			if function_doc.types in DOCTYPE_BOUND_TYPES and function_doc.reference_doctype:
				extra_args["reference_doctype"] = function_doc.reference_doctype
			elif function_doc.types == "Client Side Tool":
				if function_doc.function_name:
					extra_args["function_name"] = function_doc.function_name
			elif function_doc.types == "Run Agent":
				if function_doc.agent:
					extra_args["agent_name"] = function_doc.agent

			tool = create_function_tool(
				function_doc.tool_name,
				function_doc.description,
				function_path,
				params,
				extra_args=extra_args,
				tool_type=function_doc.types,
				allowed_for_guest=bool(function_doc.allowed_for_guest),
			)

			if tool:
				tools.append(tool)

		except Exception as e:
			frappe.log_error(
				title="SDK Functions Debug",
				message=f"Error processing function {function_doc.name}: {str(e)}",
			)

	if hasattr(agent, "enable_conversation_data") and agent.enable_conversation_data:
		existing_types = [t.name for t in tools]

		if "get_conversation_data" not in existing_types:
			tool = create_function_tool(
				name="get_conversation_data",
				description="Retrieve a specific value from the conversation data context.",
				tool_name="huf.ai.handlers.conversation_data.handle_get_conversation_data",
				parameters={
					"type": "object",
					"properties": {
						"name": {"type": "string", "description": "Name of the item to retrieve"},
						"default": {"type": "string", "description": "Default value if not found"},
					},
					"required": ["name"],
				},
			)
			if tool:
				tools.append(tool)

		if "set_conversation_data" not in existing_types:
			tool = create_function_tool(
				name="set_conversation_data",
				description="Store a value in the conversation data context.",
				tool_name="huf.ai.handlers.conversation_data.handle_set_conversation_data",
				parameters={
					"type": "object",
					"properties": {
						"name": {"type": "string", "description": "Name of the item to set"},
						"value": {
							"type": "string",
							"description": "Value to store (scalar, object, or array)",
						},
						"value_type": {
							"type": "string",
							"description": "Type of value (scalar, object, array). Optional.",
						},
						"source": {
							"type": "string",
							"description": "Source of data (agent/user). Default: agent",
						},
					},
					"required": ["name", "value"],
				},
			)
			if tool:
				tools.append(tool)

		if "load_conversation_data" not in existing_types:
			tool = create_function_tool(
				name="load_conversation_data",
				description="Load the entire conversation data context.",
				tool_name="huf.ai.handlers.conversation_data.handle_load_conversation_data",
				parameters={
					"type": "object",
					"properties": {},
					"required": [],
				},
			)
			if tool:
				tools.append(tool)

	return tools


def create_function_tool(
	name: str,
	description: str,
	tool_name: str,
	parameters: dict[str, Any],
	extra_args: dict[str, Any] = None,
	tool_type: str = None,
	allowed_for_guest: bool = False,
) -> FunctionTool:
	"""
	Create a FunctionTool for Huf Tool functions.

	Args:
		name: Tool name
		description: Tool description
		tool_name: Fully qualified handler function path
		parameters: Function parameters schema
		extra_args: Extra arguments to pass to the function
		tool_type: Tool type for permission checking
		allowed_for_guest: Whether Guest users can use this tool

	Returns:
		FunctionTool or None on failure
	"""
	function = get_function_from_name(tool_name)

	if not function:
		return None

	try:
		_extra_args = extra_args or {}
		_function = function

		async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
			# Permission check before execution
			if tool_type:
				perm_check = _check_tool_permission(
					tool_type, ctx, allowed_for_guest=allowed_for_guest
				)
				if not perm_check["allowed"]:
					return json.dumps({"error": perm_check["error"], "denied": True})

			try:
				if args_json is None and isinstance(ctx, str):
					args_json = ctx
					ctx = None

				args_dict = json.loads(args_json or "{}")

				if _extra_args:
					args_dict.update(_extra_args)

				huf_ctx = _frappe_run_context_dict(ctx)
				if "conversation_id" in huf_ctx:
					args_dict.setdefault("conversation_id", huf_ctx["conversation_id"])
				if "agent_run_id" in huf_ctx:
					args_dict.setdefault("agent_run_id", huf_ctx["agent_run_id"])
				if "agent_name" in huf_ctx:
					args_dict.setdefault("agent_name", huf_ctx["agent_name"])

				if allowed_for_guest and frappe.session.user == "Guest":
					args_dict["ignore_permissions"] = True

				if _function.__name__ in ["handle_get_request", "handle_post_request"]:
					args_dict["tool_name"] = name

				result = _call_with_filtered_args(_function, args_dict)

				# Handle async functions
				if asyncio.iscoroutine(result):
					result = await result

				if hasattr(result, "as_dict"):
					result = result.as_dict()

				return (
					json.dumps(result, default=str)
					if isinstance(result, (dict, list))
					else str(result)
				)

			except Exception as e:
				frappe.log_error(
					title="SDK Functions Debug",
					message=f"Error in on_invoke_tool for tool '{name}': {str(e)}",
				)
				return json.dumps({"error": str(e)})

		safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (name or ""))
		if len(safe_name) > 128:
			safe_name = safe_name[:128]

		if safe_name != name:
			frappe.log(
				"SDK Functions Debug",
				f"Tool runtime name '{safe_name}' created for friendly name '{name}'",
			)

		tool = FunctionTool(
			name=safe_name,
			description=description,
			params_json_schema=parameters,
			on_invoke_tool=on_invoke_tool,
			strict_json_schema=False,
		)

		return tool

	except Exception as e:
		frappe.log_error(
			title="SDK Functions Debug",
			message=f"Error creating FunctionTool for {name}: {str(e)}",
		)
		return None


def get_function_from_name(tool_name: str) -> Callable:
	"""
	Get a function from its fully qualified name.

	Args:
		tool_name: Fully qualified function name (module.function)

	Returns:
		Callable or None
	"""
	try:
		try:
			module_name, func_name = tool_name.rsplit(".", 1)
		except ValueError:
			frappe.log_error(
				title="SDK Functions Debug",
				message=f"Invalid function name format: {tool_name}. Should be 'module.function'",
			)
			return None

		try:
			module = __import__(module_name, fromlist=[func_name])
		except ImportError as ie:
			frappe.log_error(title="SDK Functions Debug", message=f"Module import error: {str(ie)}")
			return None

		try:
			function = getattr(module, func_name)
		except AttributeError as ae:
			frappe.log_error(
				title="SDK Functions Debug", message=f"Function not found in module: {str(ae)}"
			)
			return None

		if not callable(function):
			return None

		return function

	except Exception as e:
		frappe.log_error(
			title="SDK Functions Debug",
			message=f"Unexpected error getting function {tool_name}: {str(e)}",
		)
		return None


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
#
# Handler functions have been moved to huf.ai.handlers.* modules.
# These re-exports ensure existing function_path values stored in
# Agent Tool Function documents (e.g. "huf.ai.sdk_tools.handle_get_list")
# continue to resolve at runtime.
# ---------------------------------------------------------------------------

from huf.ai.handlers.agent_runner import handle_run_agent  # noqa: F401
from huf.ai.handlers.conversation_data import (  # noqa: F401
	handle_get_conversation_data,
	handle_load_conversation_data,
	handle_set_conversation_data,
)
from huf.ai.handlers.crud import (  # noqa: F401
	_sanitize_for_doctype,
	handle_attach_file_to_document,
	handle_cancel_document,
	handle_create_document,
	handle_create_documents,
	handle_delete_document,
	handle_delete_documents,
	handle_get_document,
	handle_get_documents,
	handle_get_list,
	handle_get_report_result,
	handle_get_value,
	handle_set_value,
	handle_submit_document,
	handle_update_document,
	handle_update_documents,
)
from huf.ai.handlers.media import (  # noqa: F401
	_TTS_ENV_VAR_PROVIDERS,
	_determine_ocr_strategy,
	_get_default_image_model,
	_get_default_ocr_model,
	_get_default_stt_model,
	_get_default_tts_model,
	_get_default_voice,
	_process_with_ocr_endpoint,
	_process_with_vision_model,
	_resolve_stt_config,
	_resolve_tts_config,
	handle_generate_audio,
	handle_generate_image,
	handle_ocr_document,
	handle_transcribe_audio,
)
