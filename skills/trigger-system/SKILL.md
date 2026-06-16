---
name: trigger-system
category: features
---

# Trigger System

The HUF Trigger System provides comprehensive event-driven automation, allowing AI agents to respond to various triggers including document events, schedules, webhooks, and application events. It replaces the legacy `condition` field in the Agent DocType with a robust, extensible trigger management framework.

## Overview

The trigger system enables agents to execute automatically based on:

- **Schedule**: Time-based execution (hourly, daily, weekly, monthly, yearly)
- **Doc Event**: Frappe document lifecycle events (after_insert, on_submit, etc.)
- **Webhook**: HTTP endpoint triggers with authentication
- **App Event**: Application-level events from integrated systems
- **Manual**: Programmatic execution from workflows or flows

Key capabilities include:
- Cache-based duplicate prevention with Redis locks
- Safe expression evaluation for conditional triggers
- Per-user vs shared conversation history
- Background job execution with unique job IDs
- Real-time SSE streaming support

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/doctype/agent_trigger/agent_trigger.json` | DocType schema for trigger configurations |
| `huf/huf/doctype/agent_trigger/agent_trigger.py` | Server-side validation and condition checking |
| `huf/ai/agent_hooks.py` | Document event handling and caching |
| `huf/ai/agent_scheduler.py` | Scheduled trigger execution |
| `huf/ai/agent_stream_renderer.py` | SSE streaming endpoints |
| `huf/hooks.py` | Document event hook registrations |
| `frontend/src/components/agent/TriggersTab.tsx` | React component for trigger management UI |
| `frontend/src/components/agent/TriggerModal.tsx` | Modal for creating/editing triggers |
| `frontend/src/components/agent/TriggerFieldsRenderer.tsx` | Dynamic field rendering based on trigger type |
| `frontend/src/components/agent/TriggerFieldsConfig.tsx` | Field configuration for each trigger type |
| `frontend/src/data/triggers.ts` | Trigger type definitions for UI |

## How It Works

### 1. Doc Event Triggers

Document event triggers execute agents when Frappe documents change.

**Registration Flow:**
```python
# huf/hooks.py - Universal hook registration
doc_events = {
    "*": {
        "validate": "huf.ai.agent_hooks.run_hooked_agents",
        "after_insert": "huf.ai.agent_hooks.run_hooked_agents",
        "on_submit": "huf.ai.agent_hooks.run_hooked_agents",
        # ... all document events
    }
}
```

**Execution Flow:**
1. Frappe fires document event (e.g., `after_insert` on Sales Order)
2. `run_hooked_agents()` receives the document and event name
3. Query cached triggers matching the DocType and event
4. Check Redis lock to prevent duplicate execution (30-second expiry)
5. Evaluate Python condition using `safe_eval()` (if configured)
6. Enqueue background job with unique job ID
7. `run_agent_for_doc()` constructs prompt with document context
8. Execute agent via `run_agent_sync()`

**Duplicate Prevention:**
```python
cache = frappe.cache()
lock_key = f"huf:lock:{agent['agent']}:{doc.doctype}:{doc.name}:{method}"
if cache.get_value(lock_key):
    continue  # Skip if already running
cache.set_value(lock_key, now_datetime().isoformat(), expires_in_sec=30)
```

**Conditional Execution:**
```python
condition = agent.get("condition")
if condition:
    if not safe_eval(condition, get_safe_globals(), {"doc": doc}):
        continue  # Skip if condition fails
```

**Per-User Conversation:**
```python
if getattr(agent_doc, "persist_user_history", False):
    external_id = initiating_user or doc.get("owner") or "unknown_user"
else:
    external_id = f"shared:{agent_name}"
```

### 2. Schedule Triggers

Schedule triggers execute agents at configured intervals.

**Configuration Fields:**
- `scheduled_interval`: Hourly, Daily, Weekly, Monthly, Yearly
- `interval_count`: Number of intervals between runs (e.g., every 2 days)
- `next_execution`: Calculated datetime of next run
- `last_execution`: Timestamp of last successful run

**Execution Flow:**
1. Scheduler calls `run_scheduled_agents()` (whitelisted function)
2. Query triggers where `next_execution <= now()` and not disabled
3. For each trigger:
   - Load agent and resolve prompt
   - Execute agent via `run_agent_sync()`
   - Update `last_execution` to now
   - Calculate new `next_execution` using `add_to_date()`
   - Save and commit

**Interval Calculation:**
```python
doc.next_execution = add_to_date(
    now,
    hours=interval if si == "hourly" else 0,
    days=interval if si == "daily" else 0,
    weeks=interval if si == "weekly" else 0,
    months=interval if si == "monthly" else 0,
    years=interval if si == "yearly" else 0,
)
```

### 3. Webhook Triggers

Webhook triggers expose HTTP endpoints for external systems to invoke agents.

**Configuration Fields:**
- `webhook_slug`: URL identifier (e.g., "inbound-leads")
- `webhook_key`: Secret for authentication

**Implementation:**
Webhook triggers are implemented through the `Agent Trigger` DocType with fields for slug and key. External systems POST to the webhook endpoint with the secret key for authentication.

### 4. App Event Triggers

App event triggers respond to events from integrated applications.

**Configuration Fields:**
- `app_name`: Source application (e.g., "Slack", "Gmail")
- `event_name`: Event identifier (e.g., "message.posted")

### 5. Manual Triggers

Manual triggers are executed programmatically from workflows, flows, or custom code. No additional configuration required.

### 6. Streaming (SSE)

Real-time streaming endpoints for agent responses.

**Endpoints:**
- `GET /huf/stream/<agent_name>?prompt=<message>` - SSE stream
- `GET /huf/stream` - HTML demo page
- `GET /huf/stream/ping` - Health check

**Event Types:**
```typescript
{
  type: "delta",
  content: "Partial text",
  full_response: "Accumulated response"
}
{
  type: "tool_call",
  tool_call: { function: { name: "tool_name" } }
}
{
  type: "complete",
  full_response: "Final response"
}
{
  type: "error",
  error: "Error message"
}
```

**Usage Example:**
```javascript
const eventSource = new EventSource('/huf/stream/my-agent?prompt=Hello');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'delta') {
    updateUI(data.full_response);
  }
};
```

## Trigger Configuration

### Agent Trigger DocType Fields

| Field | Type | Description |
|-------|------|-------------|
| `trigger_name` | Data | Unique identifier (autoname) |
| `agent` | Link | Target Agent to execute |
| `trigger_type` | Select | Schedule, Doc Event, Webhook, App Event, Manual |
| `disabled` | Check | Disable this trigger |
| `reference_doctype` | Link | For Doc Events: target DocType |
| `doc_event` | Select | Document event (after_insert, on_submit, etc.) |
| `condition` | Code | Python expression using `doc` variable |
| `prompt_field` | Select | DocType field containing user instructions |
| `scheduled_interval` | Select | Hourly, Daily, Weekly, Monthly, Yearly |
| `interval_count` | Int | Number of intervals between runs |
| `next_execution` | Datetime | Next scheduled run (auto-calculated) |
| `last_execution` | Datetime | Last run timestamp |
| `webhook_slug` | Data | Webhook URL identifier |
| `webhook_key` | Data | Webhook authentication secret |
| `app_name` | Data | Source application name |
| `event_name` | Data | Application event identifier |
| `metadata` | JSON | Additional trigger metadata |

### Condition Expression Examples

```python
# Only trigger for high-value orders
doc.grand_total > 10000

# Only for specific customer groups
doc.customer_group == "Premium"

# Complex conditions
doc.status == "Draft" and doc.items and len(doc.items) > 5

# Check field changes (in after_save)
doc.status == "Completed" and doc.get_db_value("status") != "Completed"
```

### Prompt Field Usage

The `prompt_field` allows agents to receive dynamic instructions from document fields:

```python
# In agent_hooks.py
custom_instruction = doc.get(prompt_field)
if custom_instruction:
    prompt += f"USER REQUEST: {custom_instruction}"
```

Use case: An "AI Instructions" field on Sales Order where users can specify custom processing requests.

## Caching System

### Cache Keys

| Key Pattern | Purpose |
|-------------|---------|
| `huf:doc_event_agents` | Hash of triggers by event type |
| `huf:lock:{agent}:{doctype}:{name}:{event}` | Duplicate prevention locks |

### Cache Invalidation

```python
def clear_doc_event_agents_cache(doc=None, method=None):
    """Clear cache when Agent Trigger changes."""
    frappe.cache().delete_key(CACHE_KEY)
```

Triggered on:
- Agent Trigger: after_insert, on_update, on_trash

## Frontend Components

### TriggersTab

Main trigger management interface showing:
- List of configured triggers
- Type/status filters
- Add/Edit/Delete actions

### TriggerModal

Configuration modal with:
- Trigger type selection
- Dynamic field rendering based on type
- Zod schema validation
- Required field checking

### TriggerFieldsRenderer

Renders appropriate fields for each trigger type:
- **Schedule**: Interval select, Count input
- **Doc Event**: DocType combobox, Event select, Condition textarea
- **Webhook**: Slug input, Key input
- **App Event**: App name, Event name inputs
- **Manual**: Info message only

## Extension Points

### Adding New Trigger Types

1. Add to `trigger_type` options in `agent_trigger.json`
2. Add field configuration in `TriggerFieldsConfig.tsx`
3. Implement execution logic in appropriate module
4. Add validation in `AgentTrigger.validate()`

### Custom Condition Evaluators

Override `safe_eval` context in `agent_hooks.py`:

```python
from frappe.utils.safe_exec import get_safe_globals

def get_custom_context(doc):
    return {
        "doc": doc,
        "utils": my_custom_utils,
        "custom_func": lambda x: x * 2
    }
```

### Webhook Handlers

Implement custom webhook processing:

```python
@frappe.whitelist(allow_guest=True)
def custom_webhook_handler():
    data = frappe.request.get_json()
    trigger = frappe.get_doc("Agent Trigger", {"webhook_slug": data.get("slug")})
    # Validate key, execute agent
```

## Dependencies

- **Frappe Framework**: Core DocType system, caching, background jobs
- **Redis**: For distributed locking and caching
- **safe_exec**: Secure Python expression evaluation
- **APScheduler** (via Frappe): Scheduled task execution

## Gotchas

### Duplicate Execution Prevention
- Redis locks expire after 30 seconds
- Long-running agents may allow re-triggering if they exceed 30s
- Locks are per-agent-per-document-per-event (not global)

### Condition Evaluation
- Conditions use `safe_eval()` with restricted globals
- No access to imports, file system, or network
- Use `doc` variable to reference the document
- Validation occurs on save, not at trigger time

### Background Jobs
- All doc event triggers run as background jobs (queue: "long")
- Job IDs include UUID to prevent conflicts
- Failures are logged but don't block document operations

### Scheduled Triggers
- Requires manual scheduler setup or external cron
- `run_scheduled_agents()` must be called periodically
- Frappe's scheduler_events can be configured in hooks.py

### Per-User History
- `persist_user_history` field on Agent controls behavior
- When enabled: Each user has isolated conversation history
- When disabled: Shared history for all doc event triggers
- Only affects Doc Event and Scheduled triggers

### Cache Consistency
- Cache is cleared when Agent Trigger documents change
- Manual database changes may require cache clear
- Cache key: `huf:doc_event_agents`

### Streaming Limitations
- SSE connections may timeout on long-running agents
- No built-in retry mechanism for stream failures
- Tool calls are visible in stream but not interactive

### Security Considerations
- Webhook keys are stored as plain Data fields (not Password)
- Conditions are evaluated with `safe_exec()` but user input should still be validated
- Background jobs run with trigger creator's permissions
