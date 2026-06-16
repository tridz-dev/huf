---
name: tool-system
category: features
---

# Tool System & MCP Client

Comprehensive tool system for HUF AI agents, enabling Frappe CRUD operations, custom functions, HTTP requests, and external tool integration via Model Context Protocol (MCP).

## Overview

The HUF Tool System provides a flexible, extensible framework for equipping AI agents with capabilities to interact with Frappe data, external APIs, and third-party services. It supports multiple tool types, automatic tool discovery from apps, and secure HTTP communication with SSRF protection.

### Key Capabilities

- **Native Frappe Tools**: CRUD operations on DocTypes, file attachments, report execution
- **Custom Function Tools**: Python functions exposed as agent tools
- **HTTP Tools**: GET/POST requests with SSRF protection and custom headers
- **MCP Client**: Integration with external MCP servers (Gmail, GitHub, etc.)
- **Standard AI Tools**: OCR, image generation, audio generation/transcription
- **Tool Registry**: Automatic discovery and sync from app hooks

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/doctype/agent_tool_function/agent_tool_function.py` | DocType for defining tool configurations and parameter schemas |
| `huf/huf/doctype/mcp_server/mcp_server.py` | MCP Server configuration and tool sync |
| `huf/ai/sdk_tools.py` | Bridge between HUF tools and `agents` SDK `FunctionTool` |
| `huf/ai/tool_functions.py` | Low-level Frappe database operations |
| `huf/ai/tool_registry.py` | Automatic tool discovery from `huf_tools` hooks |
| `huf/ai/tool_serializer.py` | Provider-agnostic tool format serialization |
| `huf/ai/http_handler.py` | SSRF-protected HTTP request handling |
| `huf/ai/mcp_client.py` | MCP client adapter for external tool servers |

## How It Works

### Tool Loading Flow

When an agent runs, tools are loaded in this order:

```
Agent Run
  └── create_agent_tools(agent)
        ├── 1. MCP Tools (from linked MCP servers)
        │     └── create_mcp_tools(agent)
        │           └── _create_mcp_function_tool()
        │                 └── execute_mcp_tool() on invocation
        │
        └── 2. Native Tools (from Agent Tool Function docs)
              └── PermissionAwareToolRegistry.get_allowed_tools()
                    └── create_function_tool() for each tool
```

### Tool Types

| Type | Handler | Description |
|------|---------|-------------|
| `Get Document` | `handle_get_document` | Fetch single document by ID or filters |
| `Get Multiple Documents` | `handle_get_documents` | Batch document retrieval |
| `Get List` | `handle_get_list` | Query documents with filters, fields, limit |
| `Create Document` | `handle_create_document` | Insert new document |
| `Create Multiple Documents` | `handle_create_documents` | Batch document creation |
| `Update Document` | `handle_update_document` | Modify existing document |
| `Update Multiple Documents` | `handle_update_documents` | Batch document updates |
| `Delete Document` | `handle_delete_document` | Remove single document |
| `Delete Multiple Documents` | `handle_delete_documents` | Batch document deletion |
| `Submit Document` | `handle_submit_document` | Submit submittable document |
| `Cancel Document` | `handle_cancel_document` | Cancel submitted document |
| `Get Value` | `handle_get_value` | Get field value(s) from document |
| `Set Value` | `handle_set_value` | Set field value on document |
| `Get Report Result` | `handle_get_report_result` | Execute report and return data |
| `Attach File to Document` | `handle_attach_file_to_document` | Attach files to documents |
| `GET` | `handle_get_request` | HTTP GET with SSRF protection |
| `POST` | `handle_post_request` | HTTP POST with SSRF protection |
| `Run Agent` | `handle_run_agent` | Trigger another agent execution |
| `Custom Function` | User-defined | Call whitelisted Python function |
| `App Provided` | Hook-defined | Auto-discovered from apps |
| `Speech to Text` | `handle_transcribe_audio` | Audio transcription |

### Permission-Aware Tool Loading

The `PermissionAwareToolRegistry` filters tools based on user permissions:

```python
class PermissionAwareToolRegistry:
    TOOL_PERMISSIONS = {
        "Get Document": {"permission": "read"},
        "Create Document": {"permission": "create"},
        "Update Document": {"permission": "write"},
        "Delete Document": {"permission": "delete"},
        # ... etc
    }
    
    MUTATING_TOOL_TYPES = {
        "Create Document", "Update Document", 
        "Delete Document", "Submit Document", ...
    }
```

- **Guest users**: Cannot use mutating tools unless explicitly allowed (`allowed_for_guest`)
- **DocType tools**: Checked against Frappe permissions for the reference DocType
- **Read-only restriction**: Tools marked `is_read_only` block mutating operations

### Tool Execution Context

Tools receive automatic context injection:

```python
# Context automatically added to tool calls
{
    "conversation_id": "CONV-001",
    "agent_run_id": "RUN-001", 
    "agent_name": "My Agent"
}
```

This enables tools to:
- Store/retrieve conversation-scoped data
- Create Agent Messages for their outputs
- Access the calling agent's configuration

## Extension Points

### 1. Adding a Custom Function Tool

Create a whitelisted function in your app:

```python
# my_app/my_module.py
import frappe
from frappe import _

@frappe.whitelist()
def my_custom_tool(param1: str, param2: int = 0) -> dict:
    """
    Description shown to the AI agent.
    
    Args:
        param1: Required parameter description
        param2: Optional parameter with default
    
    Returns:
        dict with success status and result
    """
    try:
        # Your logic here
        result = do_something(param1, param2)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

Then create an Agent Tool Function record:
- **Tool Name**: `my_custom_tool`
- **Type**: `Custom Function`
- **Function Path**: `my_app.my_module.my_custom_tool`
- **Parameters**: Define in the parameters table (or use "Fetch Parameters from Code")

### 2. Registering Tools via App Hooks

Add to your app's `hooks.py`:

```python
# my_app/hooks.py

huf_tools = [
    {
        "tool_name": "search_orders",
        "description": "Search sales orders by customer",
        "function_path": "my_app.tools.search_orders",
        "parameters": [
            {"name": "customer", "type": "string", "required": True},
            {"name": "status", "type": "string", "required": False},
        ]
    },
    {
        "tool_name": "create_invoice",
        "description": "Create invoice from order",
        "function_path": "my_app.tools.create_invoice",
        "parameters": [
            {"name": "order_id", "type": "string", "required": True},
        ]
    }
]
```

Tools are auto-synced:
- On app install/upgrade via `after_install`/`after_migrate` hooks
- Manually via **Agent Settings > Sync Tools from Apps**
- Incremental sync based on `hooks.py` modification time

### 3. Adding an MCP Server

1. Create MCP Server document:
   - **Server Name**: `github`
   - **Transport Type**: `http` or `sse`
   - **Server URL**: `https://mcp.github.example.com/mcp`
   - **Auth Type**: `bearer_token`, `api_key`, or `custom_header`
   - **Auth Header Name**: `Authorization`
   - **Auth Header Value**: (encrypted API key)
   - **Tool Namespace**: `github` (optional prefix)

2. Sync tools from the server (button on MCP Server doc)

3. Link to agents via the "MCP Servers" child table in Agent

### 4. Creating Standard AI Tools

The system includes built-in AI capabilities that agents can use:

**Image Generation**:
```python
# Agent automatically gets generate_image tool
# Uses agent's configured image_generation_model or provider default
```

**OCR/Vision**:
```python
# Agent gets ocr_document tool
# Routes to OCR endpoint for PDFs, vision models for images
# Supports page selection, image extraction from PDFs
```

**Audio Generation (TTS)**:
```python
# Agent gets generate_audio tool
# Three-tier resolution: tool param → agent.tts_model → provider default
# Supports cross-provider TTS (e.g., GPT-4 + ElevenLabs voice)
```

**Audio Transcription (STT)**:
```python
# Agent gets transcribe_audio tool
# Supports Whisper, Deepgram, Groq models
# Creates user message with transcription
```

## Tool Configuration

### HTTP Tools (GET/POST)

```python
# Tool configuration
{
    "types": "GET",
    "base_url": "https://api.example.com",
    "http_headers": [
        {"key": "Authorization", "value": "Bearer xxx"},
        {"key": "X-API-Version", "value": "v2"}
    ]
}
```

SSRF Protection automatically:
- Blocks private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
- Blocks localhost/IPv6 localhost
- Validates against tool's base URL if specified

### Run Agent Tool

```python
# Configuration
{
    "types": "Run Agent",
    "agent": "Target Agent Name"  # Link field to Agent
}

# Execution queues target agent as background job
# Returns immediately with job_id
```

### Conversation Data Tools

Enable via Agent checkbox `enable_conversation_data`:

- `get_conversation_data(name, default)` - Retrieve stored value
- `set_conversation_data(name, value, value_type)` - Store value
- `load_conversation_data()` - Get all conversation data

Used for maintaining state across agent turns.

## Dependencies

### Required

- `agents` - OpenAI Agents SDK for `FunctionTool`
- `frappe` - Frappe framework

### Optional (for MCP)

- `litellm` with experimental MCP client support
- `aiohttp` - For async MCP HTTP calls

### Standard AI Tools

- `litellm` - For image_generation, speech, transcription, OCR
- `requests` - For image download from URLs

## Gotchas

### Tool Naming

Tool names are sanitized for OpenAI compatibility:
```python
# Original name might be transformed
safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:64]
```

Reserved names that cannot be used:
- `get_document`, `get_documents`, `get_list`
- `create_document`, `create_documents`
- `update_document`, `update_documents`
- `delete_document`, `delete_documents`

### MCP Tool Namespacing

When `tool_namespace` is set on MCP Server:
- Tool name: `send_email` → `gmail.send_email`
- Description: `[MCP:gmail] Send an email...`

This prevents conflicts when multiple MCP servers have tools with the same name.

### Permission Checks

- Tools fail gracefully with `permission_denied: True` when permissions insufficient
- Guest users cannot use ANY tools unless explicitly `allowed_for_guest`
- Mutating tools blocked for Guest even if they have DocType permission

### Async Handling

Tool handlers in `sdk_tools.py` are async:
```python
async def on_invoke_tool(ctx=None, args_json: str = None) -> str:
    result = _function(**args_dict)
    if asyncio.iscoroutine(result):
        result = await result
    return json.dumps(result, default=str)
```

### HTTP Timeout

All HTTP requests (MCP and HTTP tools) have:
- Default timeout: 30 seconds
- No retries by default
- Guest access blocked unless `allowed_for_guest=True`

### TTS Model Resolution Priority

For `generate_audio` tool:
1. `model` parameter from tool call (highest)
2. Agent's `tts_model` field → fetches key from TTS model's provider
3. Provider default based on main provider (fallback)

This enables cross-provider setups (e.g., GPT-4 + ElevenLabs TTS).

### Tool Sync Cache

Tool registry uses cache to avoid re-scanning unchanged apps:
- Cache stored in `Agent Settings.last_app_scans`
- Invalidated when `hooks.py` modification time changes
- Manual sync forces full re-scan

### Parameter Schema Generation

For Custom Functions, parameters can be:
- **Auto-fetched**: Use "Fetch Parameters from Code" button (inspects function signature)
- **Manually defined**: Add rows to Parameters table
- **JSON mode**: Set `pass_parameters_as_json` to receive params as single JSON object

### Child Table Support

For DocType tools with child tables:
- Parameters can target child table fields via `child_table_name` field
- Schema automatically builds nested structure
- Data sanitized to only include valid fields

### Error Handling

All tools should return standardized response:
```python
# Success
{"success": True, "result": {...}, "message": "..."}

# Error
{"success": False, "error": "...", "permission_denied": True}
```

This enables the AI to understand tool execution outcomes and retry or inform the user appropriately.
