# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
MCP Client Adapter for HUF

This module provides the core MCP client functionality for HUF agents.
It allows agents to connect to external MCP servers and use their tools.

Features:
- Connect to MCP servers (HTTP/SSE)
- Fetch available tools from MCP servers
- Convert MCP tools to HUF FunctionTool format
- Execute MCP tool calls
- Return results in HUF's expected format

Uses LiteLLM's experimental MCP client for underlying MCP protocol handling.
"""

import asyncio
import contextlib
import contextvars
import json
from contextlib import AsyncExitStack
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from agents import FunctionTool

from huf.ai.transaction import commit_if_background


# MCP Tool prefix to identify MCP-sourced tools during execution
MCP_TOOL_PREFIX = "__mcp__"

# Scoped MCP ClientSession pool: set via `mcp_session_pool()` for the duration of a
# single agent run so all MCP tool calls within that run reuse one initialized
# session per server instead of paying a fresh transport + handshake per call.
# Left unset (None) outside a run (e.g. tool sync / connection tests), which falls
# back to the original open-per-call behavior.
_mcp_session_pool: "contextvars.ContextVar[tuple[AsyncExitStack, dict] | None]" = contextvars.ContextVar(
    "mcp_session_pool", default=None
)


@contextlib.asynccontextmanager
async def mcp_session_pool():
    """
    Scope MCP ClientSession reuse to the wrapped coroutine.

    Wrap a single agent run (one Runner.run call) with this so every MCP tool
    invocation made during that run's tool-calling loop shares one initialized
    session per MCP server, instead of opening a new transport + session per call.
    Sessions are torn down automatically when the block exits (success or error),
    so there is no separate warmup/clearing step to manage.
    """
    stack = AsyncExitStack()
    sessions: dict[str, Any] = {}
    token = _mcp_session_pool.set((stack, sessions))
    try:
        async with stack:
            yield
    finally:
        _mcp_session_pool.reset(token)


def create_mcp_tools(agent_doc, mcp_server_names: list[str] = None) -> list[FunctionTool]:
    """
    Create FunctionTool objects for all MCP tools available to an agent.
    
    This is the main entry point called from sdk_tools.create_agent_tools().
    
    Args:
        agent_doc: The Agent document with agent_mcp_server child table
        mcp_server_names: Optional list of MCP Server names to load. If provided,
            these servers are used instead of agent_doc.agent_mcp_server.
    
    Returns:
        list[FunctionTool]: List of FunctionTool objects for MCP tools
    """
    tools = []
    # Scoped to this call: tracks sanitized/truncated tool names already
    # assigned so collisions (e.g. two source names that sanitize/truncate
    # to the same 64-char string) get numeric suffixes instead of silently
    # shadowing one another.
    seen_tool_names: set[str] = set()

    if mcp_server_names is not None:
        # Use the explicitly provided server names.
        server_links = [
            type("_MCPLink", (), {"mcp_server": name, "enabled": True})()
            for name in mcp_server_names
        ]
    elif hasattr(agent_doc, "agent_mcp_server") and agent_doc.agent_mcp_server:
        server_links = agent_doc.agent_mcp_server
    else:
        return tools
    
    for mcp_link in server_links:
        if not getattr(mcp_link, "enabled", True):
            continue
        
        try:
            mcp_server = frappe.get_doc("MCP Server", mcp_link.mcp_server)
            
            if not mcp_server.enabled:
                continue
            
            # Iterate through enabled tools in child table
            for tool_row in mcp_server.tools:
                if not tool_row.enabled:
                    continue
                    
                # Reconstruct tool definition from child table
                try:
                    parameters = json.loads(tool_row.parameters) if tool_row.parameters else {}
                except json.JSONDecodeError:
                    parameters = {}
                    
                tool_def = {
                    "name": tool_row.tool_name,
                    "description": tool_row.description,
                    "parameters": parameters
                }
                
                tool = _create_mcp_function_tool(mcp_server, tool_def, seen_tool_names)
                if tool:
                    tools.append(tool)
                    
        except Exception as e:
            frappe.log_error(
                message=f"Error loading MCP tools from {mcp_link.mcp_server}: {str(e)}\n\n{frappe.get_traceback()}",
                title="MCP Client Error"
            )
    
    return tools


def _get_cached_mcp_tools(mcp_server) -> list[dict]:
    """
    Get cached tools from an MCP server document.
    
    Args:
        mcp_server: MCP Server document
    
    Returns:
        list[dict]: List of tool definitions
    """
    if not mcp_server.available_tools:
        return []
    
    try:
        tools = json.loads(mcp_server.available_tools)
        return tools if isinstance(tools, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _dedupe_tool_name(safe_name: str, seen_names: set[str] | None, max_len: int = 64) -> str:
    """Return a version of `safe_name` that is not already in `seen_names`.

    Appends `_1`, `_2`, ... until unique, truncating the base name as
    needed so the result never exceeds `max_len` characters. Adds the
    final name to `seen_names`. If `seen_names` is None, dedup is a
    no-op (returns `safe_name` unchanged) - callers that don't care about
    collisions across a batch can omit tracking.
    """
    if seen_names is None:
        return safe_name

    if safe_name not in seen_names:
        seen_names.add(safe_name)
        return safe_name

    suffix_index = 1
    while True:
        suffix = f"_{suffix_index}"
        base = safe_name[: max_len - len(suffix)]
        candidate = f"{base}{suffix}"
        if candidate not in seen_names:
            seen_names.add(candidate)
            return candidate
        suffix_index += 1


def _create_mcp_function_tool(mcp_server, tool_def: dict, seen_names: set[str] | None = None) -> FunctionTool:
    """
    Create a FunctionTool wrapper for an MCP tool.

    The tool's on_invoke_tool will call the MCP server to execute the tool.

    Args:
        mcp_server: MCP Server document
        tool_def: Tool definition from MCP server (OpenAI format)
        seen_names: Optional set of already-assigned tool names (scoped to
            the caller's batch) used to de-duplicate `safe_name` collisions.

    Returns:
        FunctionTool: Wrapped tool that calls MCP server on invocation
    """
    try:
        # Extract tool info from OpenAI format
        if "function" in tool_def:
            # OpenAI format: {"type": "function", "function": {...}}
            func_def = tool_def["function"]
        else:
            # Direct format
            func_def = tool_def
        
        tool_name = func_def.get("name", "")
        description = func_def.get("description", "")
        parameters = func_def.get("parameters", {})
        
        if not tool_name:
            return None
        
        # Apply namespace prefix if configured
        display_name = tool_name
        if mcp_server.tool_namespace:
            display_name = f"{mcp_server.tool_namespace}.{tool_name}"
        
        # Store server info for the closure
        server_name = mcp_server.name
        original_tool_name = tool_name
        
        async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
            """Execute the MCP tool via the MCP server"""
            try:
                if args_json is None and isinstance(ctx, str):
                    args_json = ctx
                    ctx = None
                
                args_dict = json.loads(args_json or "{}")
                
                # Execute the tool on the MCP server
                result = await execute_mcp_tool(
                    server_name=server_name,
                    tool_name=original_tool_name,
                    arguments=args_dict
                )
                
                return json.dumps(result, default=str) if isinstance(result, (dict, list)) else str(result)
                
            except Exception as e:
                frappe.log_error(
                    message=f"Error executing MCP tool '{display_name}': {str(e)}\n\n{frappe.get_traceback()}",
                    title="MCP Tool Execution Error"
                )
                return json.dumps({"error": str(e)})
        
        # Sanitize tool name for OpenAI compatibility
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', display_name)
        if len(safe_name) > 64:
            safe_name = safe_name[:64]
        safe_name = _dedupe_tool_name(safe_name, seen_names)

        tool = FunctionTool(
            name=safe_name,
            description=f"[MCP:{mcp_server.server_name}] {description}",
            params_json_schema=parameters,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=False
        )
        
        return tool
        
    except Exception as e:
        frappe.log_error(
            message=f"Error creating MCP tool from {tool_def}: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP Client Error"
        )
        return None


async def execute_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: dict
) -> Any:
    """
    Execute a tool call on an MCP server and return the result.
    
    This function handles the actual MCP protocol communication.
    
    Args:
        server_name: Name of the MCP Server document
        tool_name: Name of the tool to execute
        arguments: Arguments to pass to the tool
    
    Returns:
        The result from the MCP tool execution
    """
    try:
        if not frappe.has_permission("MCP Server", "read", server_name):
            return {"error": f"Permission denied: You do not have access to MCP Server {server_name}", "success": False}

        mcp_server = frappe.get_doc("MCP Server", server_name)
        
        return await _execute_mcp_tool_via_sdk(
            mcp_server, tool_name, arguments
        )
            
    except Exception as e:
        frappe.log_error(
            message=f"Error executing MCP tool {tool_name} on {server_name}: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP Tool Execution Error"
        )
        return {"error": str(e), "success": False}


from typing import Callable, Any

def _has_status_code(exc, code: str) -> bool:
    if code in str(exc):
        return True
    if hasattr(exc, "exceptions"):
        for sub_exc in exc.exceptions:
            if _has_status_code(sub_exc, code):
                return True
    return False

def _format_mcp_error(exc) -> str:
    import httpx
    if hasattr(exc, "exceptions"):
        return " | ".join(_format_mcp_error(e) for e in exc.exceptions)
    if isinstance(exc, httpx.HTTPStatusError):
        msg = str(exc)
        try:
            if hasattr(exc.response, "text") and exc.response.text:
                msg += f" (Response: {exc.response.text})"
        except (AttributeError, ValueError, RuntimeError):
            pass # Ignore if streaming response not read
        return msg
    return str(exc)

# Bounded exponential backoff parameters for 429 / 5xx retries.
_MCP_RETRY_MAX_ATTEMPTS = 5
_MCP_RETRY_BASE_DELAY_SECONDS = 1
_MCP_RETRY_MAX_DELAY_SECONDS = 60


def _is_retryable_status(exc) -> bool:
    """True if `exc` (or any of its sub-exceptions, e.g. an ExceptionGroup)
    carries an HTTP 429 or 5xx status code."""
    if _has_status_code(exc, "429"):
        return True
    return any(_has_status_code(exc, str(code)) for code in range(500, 600))


def _extract_retry_after_seconds(exc) -> float | None:
    """Best-effort extraction of a `Retry-After` header (seconds) from `exc`.

    Looks at `exc.response.headers` (the shape `httpx.HTTPStatusError` and
    similar exceptions carry) and recurses into `exc.exceptions` for
    exception groups. Returns None if no usable header is found.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except (TypeError, ValueError):
                pass

    if hasattr(exc, "exceptions"):
        for sub_exc in exc.exceptions:
            value = _extract_retry_after_seconds(sub_exc)
            if value is not None:
                return value

    return None


async def execute_with_mcp_session(mcp_server, operation: Callable[[Any], Any]):
    """
    Executes an async operation with an initialized MCP ClientSession.
    Automatically handles transport selection (SSE vs HTTP), OAuth 401
    retries, and bounded exponential backoff for 429/5xx errors (honoring
    a `Retry-After` header when present, capped at `_MCP_RETRY_MAX_ATTEMPTS`
    attempts).
    """
    headers = _build_mcp_headers(mcp_server)
    delay_seconds = _MCP_RETRY_BASE_DELAY_SECONDS

    for attempt in range(1, _MCP_RETRY_MAX_ATTEMPTS + 1):
        try:
            return await _do_execute_mcp_session(mcp_server, headers, operation)
        except Exception as e:
            # If it's a 401 and we use OAuth, refresh the token and retry once.
            if mcp_server.auth_type == "oauth" and _has_status_code(e, "401"):
                from huf.ai.mcp_oauth import refresh_oauth_token
                try:
                    refresh_oauth_token(mcp_server.name)
                    # Rebuild headers with fresh token and drop any pooled session
                    # created with the stale token so the retry opens a fresh one.
                    headers = _build_mcp_headers(mcp_server)
                    _evict_pooled_session(mcp_server.name)
                    return await _do_execute_mcp_session(mcp_server, headers, operation)
                except Exception as refresh_exc:
                    frappe.log_error(
                        message=f"OAuth retry failed: {refresh_exc}\n\n{frappe.get_traceback()}",
                        title="MCP OAuth Retry"
                    )
                    raise Exception("OAuth token invalid or expired. Reconnect via the MCP Server form.")

            # Rate-limited (429) or upstream server error (5xx): back off and retry,
            # up to _MCP_RETRY_MAX_ATTEMPTS total attempts.
            if _is_retryable_status(e) and attempt < _MCP_RETRY_MAX_ATTEMPTS:
                wait_seconds = _extract_retry_after_seconds(e)
                if wait_seconds is None:
                    wait_seconds = delay_seconds
                delay_seconds = min(delay_seconds * 2, _MCP_RETRY_MAX_DELAY_SECONDS)
                _evict_pooled_session(mcp_server.name)
                await asyncio.sleep(wait_seconds)
                continue

            frappe.log_error(
                message=f"MCP session error: {str(e)}\n\n{frappe.get_traceback()}",
                title="MCP Session Error"
            )
            raise Exception(_format_mcp_error(e))

def _evict_pooled_session(server_name: str) -> None:
    pool_ctx = _mcp_session_pool.get()
    if pool_ctx is not None:
        _, sessions = pool_ctx
        sessions.pop(server_name, None)


async def _open_mcp_session(mcp_server, headers, stack: AsyncExitStack):
    """Open a transport + ClientSession, registering both with `stack` for cleanup."""
    import httpx
    from mcp.client.session import ClientSession

    url = mcp_server.server_url
    transport_type = getattr(mcp_server, "transport_type", "http").lower()
    timeout_sec = float(mcp_server.timeout_seconds or 30.0)

    if transport_type == "sse":
        from mcp.client.sse import sse_client
        read_stream, write_stream = await stack.enter_async_context(
            sse_client(url, headers=headers, timeout=timeout_sec)
        )
    else:
        from mcp.client.streamable_http import streamable_http_client
        client = httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout_sec, read=timeout_sec)
        )
        await stack.enter_async_context(client)
        read_stream, write_stream, _get_session_id = await stack.enter_async_context(
            streamable_http_client(url, http_client=client)
        )

    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    return session


async def _do_execute_mcp_session(mcp_server, headers, operation):
    pool_ctx = _mcp_session_pool.get()
    if pool_ctx is not None:
        stack, sessions = pool_ctx
        session = sessions.get(mcp_server.name)
        if session is None:
            session = await _open_mcp_session(mcp_server, headers, stack)
            sessions[mcp_server.name] = session
        return await operation(session)

    # No active pool (e.g. tool sync / connection test) - open, use, and close inline.
    async with AsyncExitStack() as stack:
        session = await _open_mcp_session(mcp_server, headers, stack)
        return await operation(session)

async def _execute_mcp_tool_via_sdk(mcp_server, tool_name: str, arguments: dict) -> Any:
    """
    Executes an MCP tool call using the official MCP Python SDK.
    """
    async def operation(session):
        return await session.call_tool(tool_name, arguments)
    
    try:
        result = await execute_with_mcp_session(mcp_server, operation)
        # Return standard MCP content payload
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return {"content": [{"type": "text", "text": str(result)}], "isError": getattr(result, "isError", False)}
    except Exception as e:
        frappe.log_error(
            message=f"Error executing MCP tool via SDK: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP Tool Execution Error"
        )
        return {"error": str(e), "success": False}


def _build_mcp_headers(mcp_server) -> dict:
    """
    Build HTTP headers for MCP server requests.
    
    Args:
        mcp_server: MCP Server document
    
    Returns:
        dict: Headers dictionary
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    # Add authentication header
    if mcp_server.auth_type and mcp_server.auth_type != "none":
        if mcp_server.auth_type == "oauth":
            # Delegate to mcp_oauth — handles proactive refresh
            from huf.ai.mcp_oauth import get_valid_access_token
            try:
                token = get_valid_access_token(mcp_server.name)
                headers["Authorization"] = f"Bearer {token}"
            except Exception as exc:
                frappe.log_error(
                    message=f"{str(exc)}\n\n{frappe.get_traceback()}",
                    title="MCP OAuth Header Error"
                )
                # Proceed without auth header; server will return 401
        else:
            auth_value = mcp_server.get_password("auth_header_value")
            
            if auth_value and mcp_server.auth_header_name:
                if mcp_server.auth_type == "bearer_token":
                    headers[mcp_server.auth_header_name] = f"Bearer {auth_value}"
                else:
                    headers[mcp_server.auth_header_name] = auth_value
    
    # Add custom headers
    if mcp_server.custom_headers:
        for header in mcp_server.custom_headers:
            headers[header.header_name] = header.header_value
    
    return headers


@frappe.whitelist()
def sync_mcp_server_tools(server_name: str) -> dict:
    """
    Fetch and cache available tools from an MCP server.
    
    This function connects to the MCP server, retrieves the list of
    available tools, and caches them in the MCP Server document.
    
    Args:
        server_name: Name of the MCP Server document
    
    Returns:
        dict: Result with success status and tool count
    """
    try:
        if not frappe.has_permission("MCP Server", "write", server_name):
             return {"success": False, "error": f"Permission denied: You cannot sync MCP Server {server_name}"}

        mcp_server = frappe.get_doc("MCP Server", server_name)
        tools = _sync_tools_via_mcp_sdk(mcp_server)
        
        # Cache tools in the document
        mcp_server.available_tools = json.dumps(tools, indent=2)
        mcp_server.last_sync = now_datetime()
        
        # Sync tools to child table
        current_tools = {t.tool_name: t for t in mcp_server.tools}
        synced_tool_names = set()
        
        for tool_def in tools:
            # Handle both OpenAI format and direct format
            if isinstance(tool_def, dict) and "function" in tool_def:
                func_def = tool_def["function"]
            else:
                func_def = tool_def
                
            tool_name = func_def.get("name")
            if not tool_name:
                continue
                
            synced_tool_names.add(tool_name)
            description = func_def.get("description", "")
            parameters = json.dumps(func_def.get("parameters", {}), indent=2)
            
            if tool_name in current_tools:
                # Update existing tool
                row = current_tools[tool_name]
                row.description = description
                row.parameters = parameters
            else:
                # Add new tool
                mcp_server.append("tools", {
                    "tool_name": tool_name,
                    "description": description,
                    "parameters": parameters,
                    "enabled": 1
                })

        # Remove tools that no longer exist on the remote MCP server so stale/deleted
        # tools aren't left enabled and exposed to agents after a sync.
        removed_tool_names = set(current_tools.keys()) - synced_tool_names
        if removed_tool_names:
            mcp_server.tools = [
                row for row in mcp_server.tools if row.tool_name not in removed_tool_names
            ]

        # Whitelisted sync endpoint updates server metadata after permission check; bypass is required because non-admin users may trigger sync.
        mcp_server.save(ignore_permissions=True)
        commit_if_background()
        
        return {
            "success": True,
            "tool_count": len(tools),
            "tools": [t.get("function", t).get("name", "unknown") for t in tools]
        }
        
    except Exception as e:
        frappe.log_error(
            message=f"Error syncing MCP tools from {server_name}: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP Sync Error"
        )
        return {
            "success": False,
            "error": str(e)
        }


def _sync_tools_via_mcp_sdk(mcp_server) -> list:
    """
    Sync tools using the official Model Context Protocol Python SDK.
    Properly executes initialization handshakes for both HTTP and SSE.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def operation(session):
            return await session.list_tools()
        
        result = loop.run_until_complete(execute_with_mcp_session(mcp_server, operation))
        
        # Convert ListToolsResult to OpenAI format
        openai_tools = []
        if hasattr(result, "tools"):
            for tool in result.tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema or {}
                    }
                })
        return openai_tools
    finally:
        loop.close()


@frappe.whitelist()
def test_mcp_connection(server_name: str) -> dict:
    """
    Test connection to an MCP server.
    
    Args:
        server_name: Name of the MCP Server document
    
    Returns:
        dict: Result with success status
    """
    import requests

    try:
        mcp_server = frappe.get_doc("MCP Server", server_name)
        if not mcp_server.server_url:
            return {"success": False, "error": "Server URL is not set"}

        if mcp_server.auth_type and mcp_server.auth_type not in ("none", "oauth"):
            if not mcp_server.auth_header_name or not mcp_server.auth_header_value:
                return {"success": False, "error": "Auth header name and value are required for this auth type"}

        headers = _build_mcp_headers(mcp_server)

        # Try a simple ping/list request
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1
        }
        response = requests.post(
            mcp_server.server_url,
            json=payload,
            headers=headers,
            timeout=min(mcp_server.timeout_seconds or 30, 10)  # Max 10s for test
        )
        
        if response.status_code == 200:
            return {"success": True, "message": "Connection successful"}
        else:
            return {
                "success": False,
                "error": f"Server returned status {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Connection timed out"}
    except requests.exceptions.ConnectionError as e:
        return {"success": False, "error": f"Connection failed: {str(e)}"}
    except Exception as e:
        frappe.log_error(
            message=f"MCP connection test failed: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP Connection Test Error"
        )
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def get_agent_mcp_servers(agent_name: str) -> list:
    """
    Get MCP servers linked to an agent.
    
    Args:
        agent_name: Name of the Agent document
    
    Returns:
        list: List of MCP server info dicts
    """
    try:
        agent = frappe.get_doc("Agent", agent_name)
        result = []
        
        for mcp_link in (agent.agent_mcp_server or []):
            try:
                mcp_server = frappe.get_doc("MCP Server", mcp_link.mcp_server)
                
                # Count tools
                tool_count = 0
                if mcp_server.available_tools:
                    try:
                        tools = json.loads(mcp_server.available_tools)
                        tool_count = len(tools) if isinstance(tools, list) else 0
                    except json.JSONDecodeError:
                        pass
                
                result.append({
                    "name": mcp_link.name,
                    "mcp_server": mcp_server.name,
                    "server_name": mcp_server.server_name,
                    "description": mcp_server.description,
                    "server_url": mcp_server.server_url,
                    "enabled": mcp_link.enabled,
                    "mcp_enabled": mcp_server.enabled,
                    "tool_count": tool_count,
                    "last_sync": mcp_server.last_sync
                })
            except Exception as e:
                frappe.log_error(
                    message=f"Error loading MCP server {mcp_link.mcp_server}: {str(e)}\n\n{frappe.get_traceback()}",
                    title="MCP Agent Server Load Error"
                )
                continue
        
        return result
        
    except Exception as e:
        frappe.log_error(
            message=f"Error getting agent MCP servers: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP API Error"
        )
        return []


@frappe.whitelist()
def get_available_mcp_servers() -> list:
    """
    Get all available MCP servers.
    
    Returns:
        list: List of MCP server info dicts
    """
    try:
        servers = frappe.get_all(
            "MCP Server",
            filters={"enabled": 1},
            fields=["name", "server_name", "description", "server_url", "last_sync"]
        )
        
        result = []
        for server in servers:
            tool_count = 0
            try:
                available_tools = frappe.db.get_value(
                    "MCP Server", server.name, "available_tools"
                )
                if available_tools:
                    tools = json.loads(available_tools)
                    tool_count = len(tools) if isinstance(tools, list) else 0
            except json.JSONDecodeError:
                pass
            
            result.append({
                **server,
                "tool_count": tool_count
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(
            message=f"Error getting available MCP servers: {str(e)}\n\n{frappe.get_traceback()}",
            title="MCP API Error"
        )
        return []

@frappe.whitelist()
def auto_sync_mcp_server_tools():
    """
    Scheduled job to auto-sync MCP server Tools.
    Runs hourly and checks if sync is due based on the interval.
    """
    from frappe.utils import time_diff_in_hours

    servers = frappe.get_all(
        "MCP Server",
        filters={"enabled": 1, "enable_auto_sync": 1},
        fields=["name", "auto_sync_interval", "last_sync"]
    )
    
    for server in servers:
        try:
            # Check if sync is due
            if not server.last_sync or time_diff_in_hours(now_datetime(), server.last_sync) >= server.auto_sync_interval:
                frappe.log_error(
                    title="MCP Tools Auto Synced",
                    message=f"Auto-syncing MCP Tools: {server.name}",
                )
                sync_mcp_server_tools(server.name)
        except Exception as e:
            frappe.log_error(
                message=f"Error auto-syncing {server.name}: {str(e)}\n\n{frappe.get_traceback()}",
                title="MCP Tools Auto Sync Error"
            )
