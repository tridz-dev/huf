---
name: Core Agent System
description: The central AI agent execution engine for HUF, providing multi-provider LLM support, tool integration, conversation management, and real-time chat capabilities.
category: core
version: 1.0.0
---

# Core Agent System

The Core Agent System is the heart of HUF's AI capabilities. It provides a complete framework for creating, configuring, and executing AI agents with support for multiple LLM providers, tool integration, persistent conversations, and real-time interactions.

## Overview

The Core Agent System enables developers to:

- **Create AI Agents** with customizable instructions, temperature, and model settings
- **Equip Agents with Tools** including Frappe CRUD operations, custom functions, HTTP requests, and MCP server integrations
- **Manage Conversations** with persistent history, summarization, and per-user isolation
- **Track Executions** with detailed logging of token usage, costs, and performance metrics
- **Enable Real-time Chat** with markdown rendering and streaming support
- **Support Multi-Provider AI** via LiteLLM unified interface (OpenAI, Anthropic, Google, OpenRouter, etc.)

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/doctype/agent/agent.py` | Agent DocType controller with validation, permission checks, and plan generation |
| `huf/huf/doctype/agent/agent.json` | Agent DocType schema definition with all fields and tabs |
| `huf/ai/agent_integration.py` | Core execution logic with `AgentManager` class and `run_agent_sync()` function |
| `huf/ai/conversation_manager.py` | `ConversationManager` class for conversation persistence and history management |
| `huf/ai/agent_chat.py` | Chat API endpoints for message handling, audio transcription, and file processing |
| `huf/huf/doctype/agent_console/` | Testing/debugging interface (singleton DocType) |
| `huf/huf/doctype/agent_run/` | Execution logging with token tracking and cost calculation |
| `huf/huf/doctype/agent_conversation/` | Conversation document storage |
| `huf/huf/doctype/agent_message/` | Individual message storage within conversations |
| `frontend/src/pages/AgentFormPage.tsx` | React form for agent configuration with tabs |
| `frontend/src/pages/ChatPageV2.tsx` | Real-time chat interface |
| `frontend/src/components/agent/*.tsx` | Agent form tab components (General, Tools, Knowledge, Triggers, Advanced) |

## How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Core Agent System                               │
├─────────────────────────────────────────────────────────────────────────┤
│  Frontend Layer                                                         │
│  ├── AgentFormPage.tsx         → Agent configuration UI                 │
│  ├── ChatPageV2.tsx            → Real-time chat interface               │
│  └── Agent Console             → Testing/debugging interface            │
├─────────────────────────────────────────────────────────────────────────┤
│  API Layer (Whitelisted Functions)                                      │
│  ├── run_agent_sync()          → Synchronous agent execution            │
│  ├── run_agent_stream()        → Streaming agent execution              │
│  ├── send_message()            → Chat message handler                   │
│  └── upload_audio_and_transcribe() → Voice input processing             │
├─────────────────────────────────────────────────────────────────────────┤
│  Core Engine                                                            │
│  ├── AgentManager              → Agent preparation and tool setup       │
│  ├── ConversationManager       → History persistence and retrieval      │
│  └── RunProvider               → Multi-provider LLM routing             │
├─────────────────────────────────────────────────────────────────────────┤
│  Data Layer (DocTypes)                                                  │
│  ├── Agent                     → Agent configuration                    │
│  ├── Agent Run                 → Execution logs with token/cost tracking│
│  ├── Agent Conversation        → Conversation containers                │
│  └── Agent Message             → Individual messages                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent Execution Flow

1. **Agent Initialization** (`AgentManager`)
   ```python
   manager = AgentManager(agent_name)
   agent = manager.create_agent()
   ```
   - Loads Agent DocType configuration
   - Sets up AI provider client (via LiteLLM)
   - Creates tools from `Agent Tool Function` links
   - Adds knowledge search tools if knowledge sources are configured
   - Resolves prompt (Local or Template mode)

2. **Conversation Management** (`ConversationManager`)
   ```python
   conv_manager = ConversationManager(agent_name, channel, external_id)
   conversation = conv_manager.get_or_create_conversation()
   ```
   - Creates or retrieves active conversation based on session_id
   - Session ID format: `{channel}:{external_id}` or `{channel}:{user}`
   - Supports conversation persistence per user or shared

3. **Execution** (`run_agent_sync`)
   ```python
   result = run_agent_sync(
       agent_name="my-agent",
       prompt="User query here",
       channel_id="chat",
       conversation_id=conversation.name
   )
   ```
   - Creates `Agent Run` document for tracking
   - Adds user message to conversation
   - Builds knowledge context (if knowledge sources configured)
   - Routes to provider (LiteLLM for most providers)
   - Processes tool calls and logs results
   - Updates conversation with agent response
   - Calculates tokens, cost, and metrics

4. **Provider Routing** (`RunProvider` in `huf/ai/run.py`)
   - Routes to `huf/ai/providers/litellm.py` for unified provider support
   - Handles model name normalization (e.g., `gpt-4-turbo` → `openai/gpt-4-turbo`)
   - Manages API key setup for different providers
   - Supports multi-turn tool calling

### Agent DocType Structure

The Agent DocType is organized into tabs:

| Tab | Key Fields | Purpose |
|-----|------------|---------|
| **General** | `agent_name`, `provider`, `model`, `temperature`, `top_p`, `instructions` | Core LLM configuration |
| **Behaviour** | `persist_conversation`, `allow_chat`, `enable_multi_run`, `prompt_mode`, `default_plan` | Conversation and execution behavior |
| **Tools and MCP** | `agent_tool` (child table), `agent_mcp_server` (child table) | Tool and MCP server assignments |
| **Knowledge** | `agent_knowledge` (child table) | Knowledge source bindings |
| **Advanced Settings** | `context_strategy`, `history_limit`, `max_turns`, `enable_prompt_caching`, `tts_model`, `stt_model` | Advanced features |
| **Permissions** | `allow_guest`, `allowed_users`, `allowed_roles` | Access control |
| **Metadata** | `last_run`, `total_run` | Runtime statistics (read-only) |

### Conversation Management Strategies

The system supports multiple context management strategies:

1. **Summarize** (default)
   - Maintains rolling summary of old messages
   - Background job compresses history when limit exceeded
   - Configurable via `history_limit` (default: 20) and `summary_ratio` (default: 0.7)
   - Optional dedicated `summary_model` for cost optimization

2. **FIFO**
   - Drops oldest messages when limit exceeded
   - Simple but may lose important context

3. **None**
   - No automatic management
   - Risk of context window errors

### Tool Execution Flow

```
User Prompt → LLM → Tool Call Decision → Tool Execution → Result → LLM → Final Response
```

1. LLM receives prompt with tool descriptions
2. If tool call needed, LLM returns tool call request
3. System logs tool call as "Queued" in `Agent Tool Call`
4. Tool executes via `tool.on_invoke_tool()`
5. Result logged and message updated with "Tool Result"
6. LLM receives tool result and generates final response

### Streaming Support

The `run_agent_stream()` async generator provides real-time response streaming:

```python
async for chunk in run_agent_stream(agent_name, prompt):
    # chunk types: "delta", "tool_call", "complete", "error"
    print(chunk["content"])  # Partial response
```

Used by:
- SSE endpoint (`/huf/stream/<agent_name>`)
- Chat interface for live typing effect

### Multi-Run Orchestration

When `enable_multi_run` is checked:

1. Agent generates a plan (step-by-step breakdown)
2. Each step becomes a separate `Agent Run` linked via `parent_run`
3. Orchestrator manages execution flow
4. Plan stored in `default_plan` child table

### Permission System

Agent access is controlled via:

1. **Guest Access**: `allow_guest` checkbox
2. **User Binding**: `allowed_users` child table (specific users)
3. **Role Binding**: `allowed_roles` child table (role-based)
4. **Public Access**: If both lists empty, all authenticated users can access
5. **Owner**: Agent creator always has full access
6. **System Manager**: Full access regardless of settings

Permission query conditions in `agent.py` filter list views based on these rules.

## Extension Points

### 1. Custom Tools

Create custom tools via `Agent Tool Function` DocType or `huf_tools` hook:

```python
# In your app's hooks.py
huf_tools = [
    {
        "tool_name": "my_custom_tool",
        "description": "Does something useful",
        "function_path": "my_app.tools.my_function",
        "parameters": [
            {"name": "param1", "type": "string", "required": True}
        ]
    }
]
```

### 2. Custom Providers

Add provider support by creating a new file in `huf/ai/providers/`:

```python
# huf/ai/providers/my_provider.py
async def run(agent, enhanced_prompt, provider, model, context=None):
    # Your provider implementation
    return SimpleResult(final_output="...", usage={...}, cost=0.0)
```

Register in `huf/ai/run.py`:
```python
elif provider_name == "my_provider":
    from .providers import my_provider
    return await my_provider.run(agent, enhanced_prompt, provider, model, context)
```

### 3. Conversation Data Management

Enable `enable_conversation_data` to let agents persist key-value pairs:

```python
# Agent automatically gets set_conversation_data and load_conversation_data tools
# Data is stored in Agent Conversation.conversation_data (JSON)
```

### 4. Agent Hooks

Hook into document events via `Agent Trigger` DocType:

- **Schedule**: Time-based execution
- **Doc Event**: React to Frappe document lifecycle
- **Webhook**: HTTP endpoint triggers
- **App Event**: Custom application events

### 5. Prompt Templates

Use `Agent Prompt` DocType for reusable prompt templates:

1. Create prompt in `Agent Prompt` library
2. Set Agent `prompt_mode` to "Template"
3. Link `agent_prompt` to template
4. Optional: Lock version with `prompt_version_locked`

## Dependencies

### Python Packages

| Package | Purpose |
|---------|---------|
| `litellm` | Unified LLM provider interface |
| `agents` (OpenAI) | Agent SDK for tool management |
| `frappe` | Frappe framework core |

### Frappe DocTypes

| DocType | Relationship |
|---------|--------------|
| `AI Provider` | Linked from Agent (API credentials) |
| `AI Model` | Linked from Agent (model configuration) |
| `Agent Tool Function` | Child table via `Agent Tool` |
| `Knowledge Source` | Child table via `Agent Knowledge` |
| `MCP Server` | Child table via `Agent MCP Server` |
| `Agent Prompt` | Linked for template mode |
| `Agent Trigger` | Separate DocType for event hooks |

### Frontend Dependencies

| Package | Purpose |
|---------|---------|
| `react` | UI framework |
| `react-markdown` | Markdown rendering in chat |
| `frappe-react-sdk` | Frappe API integration |

## Gotchas

### 1. Async Context Safety

The system uses `_run_async_safely()` to handle nested async contexts:

```python
# Always use this wrapper when calling async code from sync contexts
result = _run_async_safely(async_function())
```

Without this, you may get "Event loop already running" errors.

### 2. Database Commit Safety

Use `safe_commit()` instead of `frappe.db.commit()` to avoid `_realtime_log` errors:

```python
from huf.ai.agent_integration import safe_commit
safe_commit()  # Handles AttributeError for _realtime_log
```

### 3. Permission Query Conditions

List view permissions are controlled via SQL conditions in `get_permission_query_conditions()`. These run at the database level, not the document level.

### 4. Tool Call Logging

Tool calls are logged in two phases:
1. **Request phase**: Inserted with status "Queued"
2. **Response phase**: Updated with result and status "Completed"/"Failed"

The `tool_call_id` links these phases together.

### 5. Context Window Handling

When `ContextWindowExceededError` occurs:
- Conversation is automatically marked inactive (`is_active = 0`)
- User-friendly error message is added to conversation
- User must start a new conversation

### 6. Rate Limit Handling

When `RateLimitError` occurs:
- User-friendly message added to conversation
- Run status set to "Failed"
- Original error preserved in logs

### 7. Token Counting Fallback

If provider doesn't return token counts, the system falls back to `litellm.token_counter()` for estimation.

### 8. MCP Tool Namespacing

MCP tools are automatically namespaced: `{server_name}.{tool_name}`

This prevents conflicts between tools from different MCP servers.

### 9. Multi-Run with Streaming

Multi-run orchestration (`enable_multi_run`) is not compatible with streaming mode. It always uses synchronous execution.

### 10. Prompt Caching Limitations

Prompt caching only works with specific providers (OpenAI, Anthropic, Bedrock, Deepseek) and models. The system validates this in `Agent.validate()`.

### 11. Conversation Model Locking

The conversation stores the model used. If the agent's model changes mid-conversation, the system continues with the new model (no longer throws error as of recent versions).

### 12. Tool Result Size Limits

Tool results are truncated to 140,000 characters to prevent database field overflow:

```python
if len(val) > 140000:
    val = val[:140000]
```

### 13. Session ID Generation

Session ID determines conversation isolation:
- Same `channel_id` + `external_id` = Same conversation
- For chat: `channel="chat"`, `external_id=user`
- For API: `channel="api"`, `external_id=custom`

### 14. Agent Color Generation

If not specified, a random color from a predefined palette is assigned on agent creation:

```python
avatar_colors_hex = ["#6366F1", "#2563EB", "#10B981", ...]
```

### 15. SSE Streaming Endpoints

Streaming endpoints are available at:
- `/huf/stream/<agent_name>?prompt=...` - SSE stream
- `/huf/stream` - HTML demo page

Enable `allow_chat` on the agent for streaming to work.
