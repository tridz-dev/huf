import inspect
import json
import re
import asyncio
from typing import Any, Callable

import frappe
from agents import FunctionTool
from frappe import _

from huf.ai.tool_types import MUTATING_TOOL_TYPES, _GUEST_DOCTYPE_PINNED_TYPES
from huf.ai.tool_registry import PermissionAwareToolRegistry

# Re-export handler functions so existing function_path strings and imports keep working.
from huf.ai.handlers.crud import *
from huf.ai.conversation_data_tools import *
from huf.ai.handlers.media import *
from huf.ai.handlers.agent_runner import *
from huf.ai.tools.perplexity import handle_perplexity_search

# Explicit re-exports for underscore-prefixed helpers used by other modules/tests.
from huf.ai.handlers.crud import _sanitize_for_doctype
from huf.ai.conversation_data_tools import _load_state
from huf.ai.handlers.media import _resolve_tts_config

logger = frappe.logger("huf")


def _frappe_run_context_dict(ctx) -> dict:
    """Huf run context may be a dict or an Agents SDK ToolContext wrapping that dict."""
    if ctx is None:
        return {}
    if isinstance(ctx, dict):
        return ctx
    inner = getattr(ctx, "context", None)
    return inner if isinstance(inner, dict) else {}


def _merge_run_context(args_dict: dict, ctx) -> dict:
    """Inject run-context values into tool args without clobbering the LLM's.

    conversation_id / agent_run_id / agent_name from the huf run context are
    only injected when the key is NOT already present in args_dict — the
    LLM's explicit arguments always win (setdefault semantics).

    ``call_id`` is the Agents SDK's own tool_call_id (``ctx.tool_call_id``,
    e.g. ``call_xyz``) rather than anything from the huf run context dict —
    it identifies this specific invocation, which tool functions that create
    their own audit row up front (e.g. client-side tools, code execution)
    need in order to correlate a later result back to this call.
    """
    huf_ctx = _frappe_run_context_dict(ctx)
    for key in ("conversation_id", "agent_run_id", "agent_name"):
        if key not in huf_ctx:
            continue

        # A BLANK value counts as absent, not as the LLM's choice.
        #
        # This used to be a plain setdefault, which only fills a key that is
        # missing entirely. Models routinely emit the key with an empty
        # string for ids they cannot know - observed live: gemini sent
        # {"conversation_id": ""} to list_document_artifacts, setdefault saw
        # the key present and kept "", and the tool failed with
        # "'conversation_id' is required" even though the run context had the
        # real id the whole time. The agent then told the user the action had
        # succeeded. Every context-injected tool was exposed to this, not
        # just the document ones.
        current = args_dict.get(key)
        if current is None or (isinstance(current, str) and not current.strip()):
            args_dict[key] = huf_ctx[key]

    tool_call_id = getattr(ctx, "tool_call_id", None)
    if tool_call_id:
        args_dict.setdefault("call_id", tool_call_id)

    return args_dict


def _check_tool_permission(tool_type: str, context: dict = None, allowed_for_guest: bool = False):
    """Guard function to block dangerous tools for Guest users"""
    user = frappe.session.user

    # Guest cannot use mutating tools unless explicitly allowed
    if user == "Guest":
        if allowed_for_guest:
            return {"allowed": True}

        if tool_type in MUTATING_TOOL_TYPES:
            return {
                "allowed": False,
                "error": f"Guest users cannot use {tool_type} tools. Please log in."
            }

    return {"allowed": True}


def create_agent_tools(agent, model_name: str = None) -> list[FunctionTool]:
    """
    Create function tools for Huf Agent

    This combines:
    1. MCP tools from linked MCP servers
    2. Native tools from Agent Tool Function documents

    model_name is the effective AI Model in use for this run (falls back to
    agent.model when omitted) — passed through to the permission-aware
    registry so an AI Model's capability overrides (see huf.ai.capabilities)
    can gate tools like ask_user regardless of the agent's own setting.
    """
    tools = []

    # Load MCP tools from linked MCP servers
    if hasattr(agent, "agent_mcp_server") and agent.agent_mcp_server:
        try:
            from huf.ai.mcp_client import create_mcp_tools
            mcp_tools = create_mcp_tools(agent)
            tools.extend(mcp_tools)
        except (ImportError, frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError) as e:
            frappe.logger("huf").warning(
                f"Error loading MCP tools for agent: {e!s}"
            )

    # Load native tools from Agent Tool Function documents
    allowed_tool_docs = PermissionAwareToolRegistry.get_allowed_tools(
        agent, frappe.session.user, model_name=model_name
    )

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
                elif function_doc.types == "Perplexity Search":
                    function_path = "huf.ai.tools.perplexity.handle_perplexity_search"
                elif function_doc.types == "Save Memory Record":
                    function_path = "huf.ai.memory_tools.handle_save_memory_record"
                elif function_doc.types == "Search Memory Records":
                    function_path = "huf.ai.memory_tools.handle_search_memory_records"
                elif function_doc.types == "Get Memory Record":
                    function_path = "huf.ai.memory_tools.handle_get_memory_record"
                elif function_doc.types == "Archive Memory Record":
                    function_path = "huf.ai.memory_tools.handle_archive_memory_record"
                elif function_doc.types == "Promote Memory to Knowledge":
                    function_path = "huf.ai.memory_tools.handle_promote_memory_to_knowledge"

                else:
                    continue

            if function_doc:
                params = {}
                if function_doc.params:
                    try:
                        params = json.loads(function_doc.params)
                    except json.JSONDecodeError as e:
                        frappe.logger("huf").debug(
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
                        "Delete Document", "Delete Multiple Documents",
                        "Submit Document", "Cancel Document", "Get Amended Document"
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

                # Client Side Tool calls block (waiting on the browser to report a
                # result via submit_client_tool_result); run them off the event loop.
                # ``blocking`` defaults to checked, so a missing/unset field (e.g. on
                # rows created before this field existed) still behaves as blocking.
                is_blocking = (
                    bool(getattr(function_doc, "blocking", 1))
                    if function_doc.types == "Client Side Tool"
                    else False
                )

                tool = create_function_tool(
                    function_doc.tool_name,
                    function_doc.description,
                    function_path,
                    params,
                    extra_args=extra_args,
                    tool_type=function_doc.types,
                    allowed_for_guest=bool(function_doc.allowed_for_guest),
                    blocking=is_blocking,
                )

                if tool:
                    tools.append(tool)

        except (frappe.DoesNotExistError, frappe.ValidationError, ValueError, KeyError, AttributeError) as e:
            frappe.logger("huf").debug(
                f"Error processing function {function_doc.name}: {e!s}"
            )

    # Load tools from attached skills (mandatory and optional)
    try:
        from huf.ai.skills.loader import load_all_skill_tools
        skill_tools = load_all_skill_tools(agent, frappe.session.user)
        if skill_tools:
            tools.extend(skill_tools)
    except Exception as e:
        frappe.log_error(
            f"Error loading skill tools for agent: {e!s}",
            "Skill Tool Loading Error"
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
            if tool:
                tools.append(tool)

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
            if tool:
                tools.append(tool)

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
            if tool:
                tools.append(tool)

    if getattr(agent, "enable_memory", False):
        existing_tool_names = {getattr(t, "name", "") for t in tools}
        memory_tool_specs = []
        if getattr(agent, "enable_memory_search_tool", True):
            memory_tool_specs.append(("search_memory_records", "Search Memory Records"))
        if getattr(agent, "enable_memory_write_tool", True):
            memory_tool_specs.append(("save_memory_record", "Save Memory Record"))

        for tool_name, tool_type in memory_tool_specs:
            if tool_name in existing_tool_names:
                continue
            function_name = frappe.db.get_value("Agent Tool Function", {"tool_name": tool_name}, "name")
            if not function_name:
                continue
            try:
                function_doc = frappe.get_doc("Agent Tool Function", function_name)
                params = {}
                if function_doc.params:
                    params = json.loads(function_doc.params)
                tool = create_function_tool(
                    function_doc.tool_name,
                    function_doc.description,
                    function_doc.function_path,
                    params,
                    tool_type=tool_type,
                )
                if tool:
                    tools.append(tool)
                    existing_tool_names.add(tool_name)
            except Exception as e:
                frappe.logger("huf").debug(f"Error wiring memory tool {tool_name}: {e!s}")

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
    blocking: bool = False,
) -> FunctionTool:
    """
    Create a FunctionTool for Huf Tool functions

    Args:
        name: Tool name
        description: Tool description
        function_name: Function name to call
        parameters: Function parameters schema
        extra_args: Extra arguments to pass to the function
        blocking: When True, the tool function is invoked via
            ``asyncio.to_thread`` instead of being awaited inline. Tool
            functions that perform a bounded blocking wait (e.g. the
            client-side tool round trip) would otherwise stall the event
            loop for the whole run; running them on a worker thread lets
            other concurrent work keep going while this call waits.

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

            # Permission check before execution
            if tool_type:
                perm_check = _check_tool_permission(tool_type, ctx, allowed_for_guest=allowed_for_guest)
                if not perm_check["allowed"]:
                    return json.dumps({"error": perm_check["error"], "denied": True})

            try:
                if args_json is None and isinstance(ctx, str):
                    args_json = ctx
                    ctx = None

                args_dict = json.loads(args_json or "{}")

                _merge_run_context(args_dict, ctx)

                if _extra_args:
                    args_dict.update(_extra_args)

                if "ignore_permissions" in args_dict:
                    del args_dict["ignore_permissions"]

                if allowed_for_guest and frappe.session.user == "Guest":
                    if tool_type in _GUEST_DOCTYPE_PINNED_TYPES and not _extra_args.get("reference_doctype"):
                        return json.dumps({
                            "error": (
                                "This tool is not available for guest access: it has no "
                                "fixed target doctype configured."
                            ),
                            "denied": True,
                        })
                    args_dict["ignore_permissions"] = True

                if _function.__name__ in ["handle_get_request", "handle_post_request"]:
                    args_dict["tool_name"] = name

                sig = inspect.signature(_function)
                accepts_kwargs = any(
                    p.kind == inspect.Parameter.VAR_KEYWORD
                    for p in sig.parameters.values()
                )
                if accepts_kwargs:
                    call_kwargs = args_dict
                else:
                    valid_params = set(sig.parameters.keys())

                    call_kwargs = {
                        k: v for k, v in args_dict.items()
                        if k in valid_params
                    }

                if blocking:
                    # Run off the event loop: a blocking tool function (e.g. one
                    # that polls for a browser-reported result for up to tens of
                    # seconds) would otherwise stall this whole run. Mirrors the
                    # asyncio.to_thread precedent in huf.ai.handlers.media (TTS
                    # via litellm.speech).
                    result = await asyncio.to_thread(_function, **call_kwargs)
                else:
                    result = _function(**call_kwargs)

                # Handle async functions
                if asyncio.iscoroutine(result):
                    result = await result

                if hasattr(result, "as_dict") and callable(getattr(result, "as_dict", None)):
                    result = result.as_dict()

                return json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)

            except Exception as e:
                frappe.logger("huf").debug(
                    f"Error in on_invoke_tool for tool '{name}': {e!s}\n{frappe.get_traceback()}"
                )
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

    except (TypeError, ValueError, AttributeError) as e:
        frappe.logger("huf").debug(
            f"Error creating FunctionTool for {name}: {e!s}\n{frappe.get_traceback()}"
        )
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
            frappe.logger("huf").debug(
                f"Invalid function name format: {tool_name}. Should be 'module.function'"
            )
            return None

        try:
            module = __import__(module_name, fromlist=[func_name])
        except ImportError as ie:
            frappe.logger("huf").debug(f"Module import error: {ie!s}")
            return None

        try:
            available_attrs = dir(module)
        except (TypeError, AttributeError) as e:
            frappe.logger("huf").debug(f"Error getting module attributes: {e!s}")

        try:
            function = getattr(module, func_name)
        except AttributeError as ae:
            frappe.logger("huf").debug(f"Function not found in module: {ae!s}")
            return None

        if not callable(function):
            return None

        return function

    except (ImportError, AttributeError, TypeError, ValueError) as e:
        frappe.logger("huf").debug(
            f"Unexpected error getting function {tool_name}: {e!s}\n{frappe.get_traceback()}"
        )
        return None


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
            # Security event: retain Error Log for unauthorized allow-list attempts.
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
    except (frappe.DoesNotExistError, frappe.PermissionError, frappe.ValidationError, ValueError, KeyError) as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        # Boundary exception handler: tool contract requires returning JSON error to LLM
        logger.warning(f"handle_get_result_context failed: {e!s}\n{frappe.get_traceback()}")
        return {"success": False, "error": str(e)}



