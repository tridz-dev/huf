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
import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from agents import FunctionTool


# MCP Tool prefix to identify MCP-sourced tools during execution
MCP_TOOL_PREFIX = "__mcp__"


def create_mcp_tools(agent_doc) -> list[FunctionTool]:
    """
    Create FunctionTool objects for all MCP tools available to an agent.
    
    This is the main entry point called from sdk_tools.create_agent_tools().
    
    Args:
        agent_doc: The Agent document with agent_mcp_server child table
    
    Returns:
        list[FunctionTool]: List of FunctionTool objects for MCP tools
    """
    tools = []
    
    if not hasattr(agent_doc, "agent_mcp_server") or not agent_doc.agent_mcp_server:
        return tools
    
    for mcp_link in agent_doc.agent_mcp_server:
        if not mcp_link.enabled:
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
                except Exception:
                    parameters = {}
                    
                tool_def = {
                    "name": tool_row.tool_name,
                    "description": tool_row.description,
                    "parameters": parameters
                }
                
                tool = _create_mcp_function_tool(mcp_server, tool_def)
                if tool:
                    tools.append(tool)
                    
        except Exception as e:
            frappe.log_error(
                f"Error loading MCP tools from {mcp_link.mcp_server}: {str(e)}",
                "MCP Client Error"
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


def _create_mcp_function_tool(mcp_server, tool_def: dict) -> FunctionTool:
    """
    Create a FunctionTool wrapper for an MCP tool.
    
    The tool's on_invoke_tool will call the MCP server to execute the tool.
    
    Args:
        mcp_server: MCP Server document
        tool_def: Tool definition from MCP server (OpenAI format)
    
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
                    f"Error executing MCP tool '{display_name}': {str(e)}",
                    "MCP Tool Execution Error"
                )
                return json.dumps({"error": str(e)})
        
        # Sanitize tool name for OpenAI compatibility
        import re
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', display_name)
        if len(safe_name) > 64:
            safe_name = safe_name[:64]
        
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
            f"Error creating MCP tool from {tool_def}: {str(e)}",
            "MCP Client Error"
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
            f"Error executing MCP tool {tool_name} on {server_name}: {str(e)}",
            "MCP Tool Execution Error"
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
        except Exception:
            pass # Ignore if streaming response not read
        return msg
    return str(exc)

async def execute_with_mcp_session(mcp_server, operation: Callable[[Any], Any]):
    """
    Executes an async operation with an initialized MCP ClientSession.
    Automatically handles transport selection (SSE vs HTTP) and OAuth 401 retries.
    """
    headers = _build_mcp_headers(mcp_server)
    
    try:
        return await _do_execute_mcp_session(mcp_server, headers, operation)
    except Exception as e:
        # If it's a 401 and we use OAuth, retry once
        if mcp_server.auth_type == "oauth" and _has_status_code(e, "401"):
            from huf.ai.mcp_oauth import refresh_oauth_token
            try:
                refresh_oauth_token(mcp_server.name)
                # Rebuild headers with fresh token
                headers = _build_mcp_headers(mcp_server)
                return await _do_execute_mcp_session(mcp_server, headers, operation)
            except Exception as refresh_exc:
                frappe.log_error(f"OAuth retry failed: {refresh_exc}", "MCP OAuth Retry")
                raise Exception("OAuth token invalid or expired. Reconnect via the MCP Server form.")
        raise Exception(_format_mcp_error(e))

async def _do_execute_mcp_session(mcp_server, headers, operation):
    import httpx
    from mcp.client.session import ClientSession
    
    url = mcp_server.server_url
    transport_type = getattr(mcp_server, "transport_type", "http").lower()
    timeout_sec = float(mcp_server.timeout_seconds or 30.0)
    
    if transport_type == "sse":
        from mcp.client.sse import sse_client
        async with sse_client(url, headers=headers, timeout=timeout_sec) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await operation(session)
    else:
        from mcp.client.streamable_http import streamable_http_client
        client = httpx.AsyncClient(
            headers=headers, 
            timeout=httpx.Timeout(timeout_sec, read=timeout_sec)
        )
        async with streamable_http_client(url, http_client=client) as streams:
            read_stream, write_stream, get_session_id = streams
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
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
            except ValueError as exc:
                frappe.log_error(str(exc), "MCP OAuth Header Error")
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
        
        mcp_server.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {
            "success": True,
            "tool_count": len(tools),
            "tools": [t.get("function", t).get("name", "unknown") for t in tools]
        }
        
    except Exception as e:
        frappe.log_error(
            f"Error syncing MCP tools from {server_name}: {str(e)}",
            "MCP Sync Error"
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
    try:
        mcp_server = frappe.get_doc("MCP Server", server_name)
        if not mcp_server.server_url:
            return {"success": False, "error": "Server URL is not set"}

        if mcp_server.auth_type and mcp_server.auth_type not in ("none", "oauth"):
            if not mcp_server.auth_header_name or not mcp_server.auth_header_value:
                return {"success": False, "error": "Auth header name and value are required for this auth type"}

        headers = _build_mcp_headers(mcp_server)
        
        import requests
        
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
                    except Exception:
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
            except Exception:
                continue
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error getting agent MCP servers: {str(e)}", "MCP API Error")
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
            except Exception:
                pass
            
            result.append({
                **server,
                "tool_count": tool_count
            })
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error getting available MCP servers: {str(e)}", "MCP API Error")
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
                frappe.log_error(f"Auto-syncing MCP Tools: {server.name}", "MCP Tools Auto Synced")
                sync_mcp_server_tools(server.name)
        except Exception as e:
            frappe.log_error(f"Error auto-syncing {server.name}: {str(e)}", "MCP Tools Auto Sync Error")
