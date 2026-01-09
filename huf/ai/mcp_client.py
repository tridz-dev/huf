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
        mcp_server = frappe.get_doc("MCP Server", server_name)
        
        # Build headers
        headers = _build_mcp_headers(mcp_server)
        return await _execute_mcp_tool_http(
            mcp_server, tool_name, arguments, headers
        )
        
        # Use LiteLLM's experimental MCP client if available
        # try:
        #     from litellm.experimental_mcp_client import call_openai_tool
            
        #     # Prepare the tool call in OpenAI format
        #     tool_call = {
        #         "type": "function",
        #         "function": {
        #             "name": tool_name,
        #             "arguments": json.dumps(arguments)
        #         }
        #     }
            
        #     # Call the MCP tool
        #     result = await call_openai_tool(
        #         mcp_url=mcp_server.server_url,
        #         tool_call=tool_call,
        #         headers=headers,
        #         timeout=mcp_server.timeout_seconds or 30
        #     )
            
        #     return result
            
        # except ImportError:
        #     # Fallback to direct HTTP call if LiteLLM MCP client not available
        #     return await _execute_mcp_tool_http(
        #         mcp_server, tool_name, arguments, headers
        #     )
            
    except Exception as e:
        frappe.log_error(
            f"Error executing MCP tool {tool_name} on {server_name}: {str(e)}",
            "MCP Tool Execution Error"
        )
        return {"error": str(e), "success": False}


async def _execute_mcp_tool_http(
    mcp_server,
    tool_name: str,
    arguments: dict,
    headers: dict
) -> Any:
    """
    Fallback HTTP-based MCP tool execution.
    
    This is used when LiteLLM's MCP client is not available.
    """
    import aiohttp
    
    url = mcp_server.server_url
    timeout = aiohttp.ClientTimeout(total=mcp_server.timeout_seconds or 30)
    
    # MCP JSON-RPC format for tool calls
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        },
        "id": 1
    }
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {
                        "error": f"MCP server returned status {response.status}: {error_text}",
                        "success": False
                    }
                
                result = await response.json()
                
                # Handle JSON-RPC response
                if "error" in result:
                    return {
                        "error": result["error"].get("message", "Unknown MCP error"),
                        "success": False
                    }
                
                return result.get("result", result)
                
    except asyncio.TimeoutError:
        return {"error": f"MCP server timeout after {mcp_server.timeout_seconds}s", "success": False}
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
        mcp_server = frappe.get_doc("MCP Server", server_name)
        headers = _build_mcp_headers(mcp_server)
        
        # Try to use LiteLLM's MCP client
        # try:
        #     tools = _sync_tools_via_litellm(mcp_server, headers)
        # except ImportError:
            # Fallback to direct HTTP
        tools = _sync_tools_via_http(mcp_server, headers)
        
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


def _sync_tools_via_litellm(mcp_server, headers: dict) -> list:
    """
    Sync tools using LiteLLM's experimental MCP client.
    """
    from litellm.experimental_mcp_client import load_mcp_tools
    
    # Run async function synchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        tools = loop.run_until_complete(
            load_mcp_tools(
                mcp_url=mcp_server.server_url,
                headers=headers,
                format="openai"  # Get tools in OpenAI function format
            )
        )
        return tools if tools else []
    finally:
        loop.close()


def _sync_tools_via_http(mcp_server, headers: dict) -> list:
    """
    Sync tools using direct HTTP calls to MCP server.
    """
    import requests
    
    # MCP JSON-RPC format for listing tools
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
        timeout=mcp_server.timeout_seconds or 30
    )
    
    response.raise_for_status()
    result = response.json()
    
    if "error" in result:
        raise Exception(result["error"].get("message", "Unknown MCP error"))
    
    # Convert MCP tools list to OpenAI format
    mcp_tools = result.get("result", {}).get("tools", [])
    openai_tools = []
    
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {})
            }
        })
    
    return openai_tools


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
        if not mcp_server.auth_header_name or not mcp_server.auth_header_value:
            return {"success": False, "error": "Auth Details are not set"}
        
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
