---
name: observability
category: patterns
description: Comprehensive observability and monitoring system for HUF AI agents
---

# Observability & Monitoring

HUF provides a comprehensive observability and monitoring system that tracks every aspect of AI agent execution, from individual API calls to complete conversation histories. The system enables debugging, cost optimization, performance analysis, and quality assurance through detailed logging and feedback collection.

## Overview

The observability system in HUF captures:

- **Execution Logging**: Every agent run is logged with status, timing, tokens, and cost
- **Conversation Tracking**: Full conversation history with message types and metadata
- **Tool Call Auditing**: Detailed logs of all tool invocations with arguments and results
- **User Feedback**: Thumbs up/down ratings with comments for quality analysis
- **Real-time Monitoring**: Dashboard views for active agents and recent executions
- **Cost Analysis**: Token usage and cost tracking per run, conversation, and agent

## Key Files

| File | Purpose |
|:-----|:--------|
| `huf/huf/doctype/agent_run/agent_run.json` | DocType schema for execution logging |
| `huf/huf/doctype/agent_run/agent_run.py` | Agent Run document controller |
| `huf/huf/doctype/agent_conversation/agent_conversation.json` | Conversation tracking schema |
| `huf/huf/doctype/agent_message/agent_message.json` | Individual message logging schema |
| `huf/huf/doctype/agent_run_feedback/agent_run_feedback.json` | User feedback collection schema |
| `huf/huf/doctype/agent_tool_call/agent_tool_call.json` | Tool execution audit logging |
| `huf/ai/agent_integration.py` | Main orchestration with logging hooks |
| `huf/ai/conversation_manager.py` | Conversation lifecycle management |
| `huf/ai/run.py` | Provider routing with telemetry |
| `frontend/src/services/dashboardApi.ts` | Dashboard metrics API |
| `frontend/src/services/agentRunApi.ts` | Agent run CRUD operations |
| `frontend/src/pages/Executions.tsx` | Execution list view with filters |
| `frontend/src/pages/AgentRunDetailPage.tsx` | Detailed run inspection |
| `frontend/src/components/dashboard/views/RecentExecutionsTab.tsx` | Dashboard widget for recent runs |
| `frontend/src/components/dashboard/views/ActiveAgentsTab.tsx` | Active agents dashboard widget |
| `frontend/src/components/dashboard/filters/FilterBar.tsx` | Reusable filter component |
| `frontend/src/components/dashboard/layouts/PageLayout.tsx` | Standard page layout |
| `huf/huf/report/agent_run_feedback/agent_run_feedback.json` | Feedback analysis report |
| `huf/huf/report/ai_model_efficiency_analysis/ai_model_efficiency_analysis.json` | Model efficiency report |
| `huf/huf/report/average_time_duration/average_time_duration.json` | Performance timing report |

## How It Works

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Agent Execution Flow                              │
└─────────────────────────────────────────────────────────────────────────┘

1. User Request
   │
   ▼
┌─────────────────┐
│ run_agent_sync()│  ← Creates Agent Run document with status "Queued"
│  (integration)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ConversationManager
│  get_or_create_ │  ← Links run to conversation
│  conversation() │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   AgentManager  │  ← Sets up tools and creates agent
│   create_agent()│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  RunProvider    │  ← Routes to provider (LiteLLM)
│     .run()      │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌──────┐  ┌────────┐
│Tool  │  │Response│
│Calls │  │        │
└──┬───┘  └───┬────┘
   │          │
   ▼          ▼
┌─────────────────┐
│  log_tool_call()│  ← Creates Agent Tool Call documents
│  (integration)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Update Agent   │  ← Sets status, tokens, cost, response
│  Run Document   │
└─────────────────┘
```

### Agent Run Lifecycle

```
Queued → Started → [Tool Calls] → Success/Failed
   │         │
   │         └─ start_time recorded
   │            input_tokens tracked
   │            output_tokens tracked
   │            cost calculated
   │
   └─ Created on request receipt
```

### DocType Relationships

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Agent Run     │────▶│Agent Conversation│◀────│  Agent Message  │
│                 │     │                  │     │                 │
│ • prompt        │     │ • title          │     │ • content       │
│ • response      │     │ • session_id     │     │ • role          │
│ • status        │     │ • is_active      │     │ • kind          │
│ • input_tokens  │     │ • total_messages │     │ • agent_run     │
│ • output_tokens │     │ • total_cost     │     │ • tool_calll    │
│ • cost          │     │                  │     │                 │
│ • flow_run      │     │                  │     │                 │
└────────┬────────┘     └──────────────────┘     └─────────────────┘
         │
         │◄────────────────────────────────────────┐
         │                                         │
         ▼                                         │
┌─────────────────┐     ┌──────────────────┐      │
│ Agent Tool Call │     │Agent Run Feedback│      │
│                 │     │                  │      │
│ • tool          │     │ • feedback       │      │
│ • tool_args     │     │ • comments       │      │
│ • tool_result   │     │ • agent_message  │──────┘
│ • status        │     │ • agent          │
│ • is_mcp_tool   │     │ • provider       │
└─────────────────┘     └──────────────────┘
```

### Token and Cost Tracking

Tokens and costs are tracked at multiple levels:

1. **Per Run** (`Agent Run`):
   - `input_tokens`: Tokens sent to the model
   - `output_tokens`: Tokens received from the model
   - `cached_tokens`: Reused tokens from prompt cache
   - `cost`: Calculated using LiteLLM's `completion_cost()`

2. **Per Conversation** (`Agent Conversation`):
   - `total_input_tokens`: Cumulative input across all runs
   - `total_output_tokens`: Cumulative output across all runs
   - `total_tokens`: Combined total
   - `total_cost`: Cumulative cost

3. **Aggregation** (via SQL):
   ```python
   frappe.db.sql("""
       UPDATE `tabAgent Conversation`
       SET 
           total_input_tokens = total_input_tokens + %s,
           total_output_tokens = total_output_tokens + %s,
           total_tokens = total_tokens + %s,
           total_cost = total_cost + %s
       WHERE name = %s
   """, (input_tokens, output_tokens, total_tokens, cost, conversation.name))
   ```

### Tool Call Logging

Tool calls are logged in two phases:

1. **Request Phase** (`is_output=False`):
   ```python
   process_tool_call(
       agent_run=run_doc.name,
       conversation=conversation.name,
       name=tool_name,
       args=tool_args,
       status="Queued",
       is_output=False
   )
   ```

2. **Response Phase** (`is_output=True`):
   ```python
   process_tool_call(
       agent_run=run_doc.name,
       result=tool_result,
       error=error_message,
       status="Completed" | "Failed",
       is_output=True
   )
   ```

### Knowledge Usage Tracking

When knowledge sources are used:
- `knowledge_sources_used`: JSON array of source names
- `chunks_injected`: Number of chunks added to context

### Flow Integration

Agent Runs can be linked to Flow Engine executions:
- `flow_run`: Link to `Flow Run` document
- `flow_node_id`: Node ID within the flow
- `flow_id`: Flow definition ID
- `run_kind`: Type of run (`agent`, `tool`, `orchestrator`)
- `parent_run`: For hierarchical runs (orchestration)
- `is_child`: Boolean flag for child runs

## Extension Points

### Custom Metrics

Add custom fields to `Agent Run` for domain-specific tracking:

```python
# In custom app, extend Agent Run via Custom Field
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Agent Run",
    "fieldname": "custom_metric",
    "fieldtype": "Data",
    "label": "Custom Metric"
}).insert()
```

### Webhook Notifications

Hook into run completion:

```python
# In hooks.py
doc_events = {
    "Agent Run": {
        "on_update": "my_app.observability.notify_run_complete"
    }
}

# In my_app/observability.py
def notify_run_complete(doc, method):
    if doc.status in ("Success", "Failed"):
        send_webhook({
            "run_id": doc.name,
            "agent": doc.agent,
            "status": doc.status,
            "cost": doc.cost
        })
```

### Custom Dashboard Widgets

Add new dashboard tabs:

```typescript
// frontend/src/components/dashboard/views/CustomMetricsTab.tsx
export function CustomMetricsTab() {
  // Your custom metrics component
}

// Export in index.ts
export { CustomMetricsTab } from './views/CustomMetricsTab';
```

### Additional Reports

Create new SQL reports in `huf/huf/report/`:

```python
# Report query example
query = """
SELECT 
    agent,
    DATE(creation) as date,
    COUNT(*) as run_count,
    AVG(cost) as avg_cost,
    SUM(input_tokens + output_tokens) as total_tokens
FROM `tabAgent Run`
WHERE creation >= %(from_date)s
GROUP BY agent, DATE(creation)
ORDER BY date DESC
"""
```

## Dependencies

### Backend

- **LiteLLM**: For token counting and cost calculation
- **Frappe Framework**: Document storage and permissions
- **agents SDK**: For tool call interception

### Frontend

- **@tanstack/react-table**: Table components for execution lists
- **frappe-sdk**: Frappe API client
- **lucide-react**: Icons for status indicators

### Database

The observability system relies on standard Frappe DocType tables:
- `tabAgent Run`
- `tabAgent Conversation`
- `tabAgent Message`
- `tabAgent Tool Call`
- `tabAgent Run Feedback`

## Gotchas

### Large Tool Results

Tool results are truncated at 140,000 characters to prevent database issues:

```python
if len(val) > 140000:
    val = val[:140000]
```

### Cost Calculation Fallback

If provider doesn't return usage, LiteLLM's `token_counter` is used as fallback:

```python
from litellm import token_counter
input_tokens = token_counter(model=pricing_model, messages=msgs_for_count)
output_tokens = token_counter(model=pricing_model, text=full_response)
```

### Permission Conditions

Observability data has role-based access:

```python
# Users only see their own conversations/runs unless they have
# chat.view_all or agent.view_all capabilities
def get_run_permission_conditions(user):
    if "System Manager" in frappe.get_roles(user):
        return None
    if has_capability(user, "agent.view_all"):
        return None
    return f"`tabAgent Run`.owner = {frappe.db.escape(user)}"
```

### Real-time Updates

Tool call completions emit socket events for real-time UI updates:

```python
frappe.publish_realtime(
    event=f'conversation:{conversation.name}',
    message={
        "type": "tool_call_completed",
        "tool_call_id": updated_tool_call_id,
        "tool_result": tool_result
    }
)
```

### Child Run Filtering

When listing executions, filter out child runs to avoid duplication:

```typescript
filters: [["is_child","=","0"]]
```

### Status Variants

Frontend status badges use these mappings:
- `Success` → `default` (green)
- `Failed` → `destructive` (red)
- `Started`/`Queued` → `secondary` (gray)

### Token Precision

Cost is stored as Float with 6 decimal precision for accurate tracking of low-cost models.

### Conversation Auto-Naming

Conversations are auto-named based on content after the first few messages (background job).

### Streaming vs Sync

Both `run_agent_sync` and `run_agent_stream` follow the same logging patterns but streaming:
- Updates metrics incrementally
- Yields chunks for real-time display
- Has additional error handling for connection drops
