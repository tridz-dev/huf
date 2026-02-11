# Sub-Agent Execution: Improving `run_agent` for Agent-to-Agent Communication

## Overview

This document outlines the current state of sub-agent execution in HUF, identifies its limitations, and proposes both a quick solution and a long-term architecture for reliable agent-to-agent communication via the `run_agent` tool.

---

## Current Implementation

### How `run_agent` Works Today

When an agent calls the `run_agent` tool, the handler in `huf/ai/sdk_tools.py` (`handle_run_agent`, ~line 1051) does the following:

1. Enqueues a background job via `frappe.enqueue()` to run the target agent
2. Returns a minimal response:
   ```json
   {
     "success": true,
     "queued": true,
     "job_id": "<redis_queue_job_id>"
   }
   ```

### What Gets Persisted

HUF already has robust persistence for agent execution:

| DocType | Key Fields | Purpose |
|---------|-----------|---------|
| **Agent Run** | `agent`, `status`, `prompt`, `response`, `parent_run`, `is_child`, `conversation` | Execution record with parent-child linking |
| **Agent Conversation** | `agent`, `session_id`, `channel`, `summary`, `conversation_data` | Conversation context and memory |
| **Agent Message** | `conversation`, `agent_run`, `content`, `role`, `kind` | Individual messages |
| **Agent Tool Call** | `agent_run`, `tool`, `tool_args`, `tool_result`, `status` | Tool invocation audit trail |

The `run_agent_sync()` function already accepts a `parent_run_id` parameter and sets `is_child = 1` on child runs. The orchestration system (`agent_integration.py:590-613`) also supports multi-run flows with `Agent Orchestration` documents.

### The Problem

The calling agent receives only a Redis job ID — an opaque, ephemeral identifier that:

- Cannot be queried through Frappe's document API
- Disappears when the job completes or Redis restarts
- Gives the calling agent no way to retrieve the sub-agent's result
- Breaks the execution chain — the caller loses continuity

This means in practice, the `run_agent` tool fires-and-forgets. The calling agent cannot:

- Check if the sub-agent finished
- Read the sub-agent's output
- Make decisions based on the sub-agent's result
- Build multi-agent reasoning chains

---

## Quick Solution: Persist-First, Return Domain References

### Core Principle

**Do not return a queue job ID. Return domain-level identifiers that are already persisted.**

### Modified `handle_run_agent` Flow

```python
def handle_run_agent(agent_name, prompt, **kwargs):
    ctx = kwargs.get("ctx", {})
    parent_run_id = ctx.get("agent_run_id")
    conversation_id = ctx.get("conversation_id")

    # 1. Create Agent Run document BEFORE enqueueing
    agent_run = frappe.get_doc({
        "doctype": "Agent Run",
        "agent": agent_name,
        "prompt": prompt,
        "status": "Queued",
        "parent_run": parent_run_id,
        "is_child": 1 if parent_run_id else 0,
        "conversation": conversation_id,
    }).insert(ignore_permissions=True)

    # 2. Enqueue background execution with the persisted run ID
    frappe.enqueue(
        "huf.ai.agent_integration.run_agent_background",
        agent_run_id=agent_run.name,
        agent_name=agent_name,
        prompt=prompt,
        conversation_id=conversation_id,
        parent_run_id=parent_run_id,
        queue="long",
    )

    # 3. Return stable, queryable references
    return json.dumps({
        "status": "queued",
        "agent_run_id": agent_run.name,
        "conversation_id": conversation_id,
        "agent": agent_name,
    })
```

### Background Worker

```python
def run_agent_background(agent_run_id, agent_name, prompt, conversation_id=None, parent_run_id=None):
    run = frappe.get_doc("Agent Run", agent_run_id)
    try:
        run.status = "Started"
        run.start_time = now()
        run.save(ignore_permissions=True)
        frappe.db.commit()

        result = run_agent_sync(
            agent_name=agent_name,
            prompt=prompt,
            conversation_id=conversation_id,
            parent_run_id=parent_run_id,
        )

        run.reload()
        run.status = "Success"
        run.response = result.get("response", "")
        run.end_time = now()
        run.save(ignore_permissions=True)
        frappe.db.commit()

        # Notify via realtime
        frappe.publish_realtime(
            event=f"agent_run:{agent_run_id}",
            message={"status": "completed", "agent_run_id": agent_run_id},
        )

    except Exception as e:
        run.reload()
        run.status = "Failed"
        run.error_message = str(e)
        run.end_time = now()
        run.save(ignore_permissions=True)
        frappe.db.commit()

        frappe.publish_realtime(
            event=f"agent_run:{agent_run_id}",
            message={"status": "failed", "agent_run_id": agent_run_id, "error": str(e)},
        )
```

### New Companion Tools

Two new tools the calling agent can use to check on its sub-agent:

#### `get_agent_run_status`

```python
def handle_get_agent_run_status(agent_run_id, **kwargs):
    """Check the current status of an agent run."""
    run = frappe.get_doc("Agent Run", agent_run_id)
    return json.dumps({
        "agent_run_id": run.name,
        "agent": run.agent,
        "status": run.status,  # Queued | Started | Success | Failed
        "start_time": str(run.start_time) if run.start_time else None,
        "end_time": str(run.end_time) if run.end_time else None,
        "has_response": bool(run.response),
    })
```

#### `get_agent_run_result`

```python
def handle_get_agent_run_result(agent_run_id, **kwargs):
    """Retrieve the result of a completed agent run."""
    run = frappe.get_doc("Agent Run", agent_run_id)
    if run.status in ("Queued", "Started"):
        return json.dumps({
            "agent_run_id": run.name,
            "status": run.status,
            "message": "Run is still in progress. Check back later.",
        })
    return json.dumps({
        "agent_run_id": run.name,
        "agent": run.agent,
        "status": run.status,
        "response": run.response,
        "error_message": run.error_message if run.status == "Failed" else None,
    })
```

### How the Calling Agent Uses This

```
Agent A (Coordinator):
  1. Calls run_agent("planner_agent", "Analyze Q4 metrics")
  2. Receives: { agent_run_id: "RUN-00045", status: "queued" }
  3. Calls get_agent_run_status("RUN-00045")
  4. Receives: { status: "Success", has_response: true }
  5. Calls get_agent_run_result("RUN-00045")
  6. Receives: { response: "Q4 analysis: revenue up 12%..." }
  7. Incorporates result into its own reasoning
```

### What This Fixes

| Before | After |
|--------|-------|
| Returns ephemeral Redis job ID | Returns persistent `agent_run_id` |
| No way to check status | `get_agent_run_status` tool |
| No way to read result | `get_agent_run_result` tool |
| Parent-child link may be missing | Always sets `parent_run` and `is_child` |
| Fire-and-forget only | Caller can poll and retrieve |

---

## Long-Term Architecture: Flexible Execution Modes & Controls

### Execution Mode Parameter

Add a `mode` parameter to `run_agent`:

```python
def handle_run_agent(agent_name, prompt, mode="async", **kwargs):
    if mode == "await":
        # Synchronous inline execution — blocks until complete
        result = run_agent_sync(agent_name=agent_name, prompt=prompt, ...)
        return json.dumps({
            "status": "completed",
            "agent_run_id": result["agent_run_id"],
            "response": result["response"],
        })
    elif mode == "async":
        # Background execution — returns handle immediately
        # (Quick solution flow above)
        ...
```

| Mode | Behavior | Use Case |
|------|----------|----------|
| `async` | Enqueue background job, return handle | Long-running sub-agents, parallel execution |
| `await` | Run inline synchronously, return full result | Short sub-tasks where caller needs immediate result |

### Chat Scenario Considerations

In the chat UI, users interact via SSE streaming (`/huf/stream/<agent_name>`). Sub-agent execution introduces specific challenges:

#### Problem: User Sees Nothing While Sub-Agent Runs

When Agent A calls `run_agent` in async mode during a chat, the SSE stream may complete (Agent A finishes its turn) before the sub-agent returns. The user sees Agent A's response but has no visibility into the sub-agent's work.

#### Solution: Real-Time Sub-Agent Status Events

Emit SSE-compatible events for sub-agent lifecycle:

```python
# In the background worker
frappe.publish_realtime(
    event=f"conversation:{conversation_id}",
    message={
        "type": "sub_agent_started",
        "parent_run_id": parent_run_id,
        "child_run_id": agent_run.name,
        "child_agent": agent_name,
    }
)

# On completion
frappe.publish_realtime(
    event=f"conversation:{conversation_id}",
    message={
        "type": "sub_agent_completed",
        "parent_run_id": parent_run_id,
        "child_run_id": agent_run.name,
        "child_agent": agent_name,
        "response_preview": response[:200],  # preview for UI
    }
)
```

**Frontend handling** (`ChatMessageList.tsx`): The socket listener already handles events on the `conversation:{id}` channel. Add handlers for `sub_agent_started` and `sub_agent_completed` to show inline status indicators in the chat thread.

#### Await Mode in Chat

For short sub-agent calls during streaming, `await` mode is preferable — the parent agent's SSE stream stays open, the sub-agent runs inline, and the result flows back through the same stream. The user sees a seamless response.

For long sub-agent calls, `async` mode with socket events keeps the UI responsive while showing progress.

### Non-Chat Scenario Considerations

In non-chat contexts (triggers, scheduled runs, API calls via `run_agent_sync`), sub-agent execution has different requirements:

| Context | Recommended Mode | Reason |
|---------|-----------------|--------|
| **Doc Event Triggers** (`agent_hooks.py`) | `await` | Trigger runs are already background jobs; inline sub-agent keeps execution sequential and traceable |
| **Scheduled Runs** (`agent_scheduler.py`) | `await` or `async` | Depends on whether the scheduler needs the result before continuing |
| **API Calls** (`run_agent_sync`) | `await` | Caller is already waiting for a response; inline execution returns complete result |
| **Orchestration Steps** | `async` with polling | Steps may run in parallel; orchestrator polls for completion |

### Handling Page Refresh / Disconnection

When a user refreshes the browser during sub-agent execution:

#### Problem

- SSE connection drops
- Socket.io reconnects but may miss events
- User loses visibility into in-flight sub-agent work

#### Solution: Recovery on Reconnect

1. **Persist all state in documents** (already done with Agent Run, Agent Message)
2. **On page load**, query active runs for the conversation:
   ```python
   @frappe.whitelist()
   def get_active_runs(conversation_id):
       return frappe.get_all("Agent Run",
           filters={
               "conversation": conversation_id,
               "status": ["in", ["Queued", "Started"]],
           },
           fields=["name", "agent", "status", "parent_run", "start_time"],
       )
   ```
3. **Frontend reconnection logic**:
   ```typescript
   // On mount or reconnect
   const activeRuns = await call.get("huf.ai.agent_integration.get_active_runs", {
       conversation_id: currentConversation,
   });
   if (activeRuns.length > 0) {
       // Show "Agent X is still running..." indicator
       // Subscribe to socket events for these runs
       activeRuns.forEach(run => {
           socket.on(`agent_run:${run.name}`, handleRunUpdate);
       });
   }
   ```
4. **Completed runs since last seen**: Query messages created after the user's last known message index to catch any results that arrived during disconnection.

### WebSocket-Based Completion Notification

Instead of polling, use Frappe's built-in `publish_realtime` to push completion events:

```python
# Event hierarchy for sub-agent runs:

# 1. Conversation-level (chat UI listens to this)
frappe.publish_realtime(
    event=f"conversation:{conversation_id}",
    message={"type": "sub_agent_completed", ...}
)

# 2. Run-level (specific run watchers)
frappe.publish_realtime(
    event=f"agent_run:{agent_run_id}",
    message={"type": "completed", "response": response}
)

# 3. Agent-level (dashboard/monitoring)
frappe.publish_realtime(
    event=f"agent:{agent_name}",
    message={"type": "run_completed", "agent_run_id": agent_run_id}
)
```

**Frontend subscription pattern**:

```typescript
// Subscribe to sub-agent updates for current conversation
frappe.realtime.on(`conversation:${conversationId}`, (data) => {
    if (data.type === "sub_agent_started") {
        addStatusMessage(`Running ${data.child_agent}...`);
    }
    if (data.type === "sub_agent_completed") {
        updateStatusMessage(data.child_run_id, "completed");
        // Optionally auto-fetch full result
    }
});
```

### Polling Fallback

For environments where WebSocket is unreliable (proxies, firewalls), provide a polling endpoint:

```python
@frappe.whitelist()
def poll_agent_run(agent_run_id):
    """Lightweight status check for polling scenarios."""
    status, response = frappe.db.get_value(
        "Agent Run", agent_run_id, ["status", "response"]
    )
    return {"status": status, "has_response": bool(response)}
```

Polling strategy:
- Initial interval: 1 second
- Backoff: Double interval each poll, cap at 10 seconds
- Timeout: Configurable per agent (default 5 minutes)

### Agent Waiting / Blocking Semantics

For agents that need to coordinate — e.g., Agent A dispatches three sub-agents and needs all results:

#### Tool: `wait_for_runs`

```python
def handle_wait_for_runs(agent_run_ids, timeout=300, **kwargs):
    """Block until all specified runs complete or timeout."""
    import time
    start = time.time()
    pending = set(agent_run_ids)

    while pending and (time.time() - start) < timeout:
        for run_id in list(pending):
            status = frappe.db.get_value("Agent Run", run_id, "status")
            if status in ("Success", "Failed"):
                pending.discard(run_id)
        if pending:
            time.sleep(2)
            frappe.db.rollback()  # refresh DB state in long-running job

    results = {}
    for run_id in agent_run_ids:
        run = frappe.get_doc("Agent Run", run_id)
        results[run_id] = {
            "status": run.status,
            "response": run.response if run.status == "Success" else None,
            "error": run.error_message if run.status == "Failed" else None,
        }

    return json.dumps({
        "all_completed": len(pending) == 0,
        "timed_out": list(pending),
        "results": results,
    })
```

> **Caution**: `wait_for_runs` should only be used in `async` background execution contexts. Using it in a synchronous SSE stream would block the response and waste a worker thread. The tool should validate its execution context before blocking.

### Parent-Child Execution Graph

The existing `parent_run` field on Agent Run already supports tree structures. Extend with:

```
Agent Run: RUN-001 (Coordinator)
├── Agent Run: RUN-002 (Planner)      parent_run=RUN-001
├── Agent Run: RUN-003 (Researcher)   parent_run=RUN-001
│   └── Agent Run: RUN-005 (Fetcher)  parent_run=RUN-003
└── Agent Run: RUN-004 (Summarizer)   parent_run=RUN-001
```

#### Query helpers

```python
def get_child_runs(parent_run_id):
    """Get all direct child runs."""
    return frappe.get_all("Agent Run",
        filters={"parent_run": parent_run_id},
        fields=["name", "agent", "status", "response"],
        order_by="creation asc",
    )

def get_execution_tree(root_run_id):
    """Recursively build the full execution tree."""
    run = frappe.get_doc("Agent Run", root_run_id)
    children = get_child_runs(root_run_id)
    return {
        "run_id": run.name,
        "agent": run.agent,
        "status": run.status,
        "children": [get_execution_tree(c.name) for c in children],
    }
```

---

## Summary: Implementation Phases

### Phase 1 — Quick Win (Persist-First Handle)

| Change | File |
|--------|------|
| Modify `handle_run_agent` to create Agent Run before enqueueing | `huf/ai/sdk_tools.py` |
| Create `run_agent_background` worker function | `huf/ai/agent_integration.py` |
| Add `get_agent_run_status` tool handler | `huf/ai/sdk_tools.py` |
| Add `get_agent_run_result` tool handler | `huf/ai/sdk_tools.py` |
| Register new tools in tool type definitions | `huf/ai/sdk_tools.py` |
| Emit `publish_realtime` events on sub-agent completion | `huf/ai/agent_integration.py` |

### Phase 2 — Execution Modes

| Change | File |
|--------|------|
| Add `mode` parameter (`async` / `await`) to `run_agent` tool | `huf/ai/sdk_tools.py` |
| Implement inline synchronous sub-agent execution for `await` mode | `huf/ai/agent_integration.py` |
| Add `wait_for_runs` tool for parallel dispatch patterns | `huf/ai/sdk_tools.py` |
| Context validation (prevent blocking in SSE streams) | `huf/ai/sdk_tools.py` |

### Phase 3 — Chat UI Integration

| Change | File |
|--------|------|
| Handle `sub_agent_started` / `sub_agent_completed` socket events | `frontend/src/components/chat/ChatMessageList.tsx` |
| Show inline sub-agent status indicators in chat | `frontend/src/components/chat/` |
| Reconnection recovery: query active runs on mount | `frontend/src/components/chat/ChatMessageList.tsx` |
| Catch-up logic for missed messages during disconnect | `frontend/src/hooks/useChatSocket.ts` |

### Phase 4 — Execution Graph & Monitoring

| Change | File |
|--------|------|
| Add `get_child_runs` / `get_execution_tree` API methods | `huf/ai/agent_integration.py` |
| Execution tree visualization in Agent Run detail view | `frontend/src/pages/` |
| Add `poll_agent_run` lightweight status endpoint | `huf/ai/agent_integration.py` |
| Dashboard for active multi-agent executions | `frontend/src/pages/` |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Return `agent_run_id` instead of Redis job ID | Persistent, queryable, survives restarts |
| Create Agent Run before enqueueing | Guarantees reference exists even if queue fails |
| Use `publish_realtime` for notifications | Already used throughout HUF; no new infrastructure |
| Polling as fallback, not primary | WebSocket is preferred; polling for degraded environments |
| `await` mode runs inline | Avoids queue overhead for short sub-tasks |
| `wait_for_runs` restricted to background contexts | Prevents blocking SSE streams and wasting worker threads |
| Conversation shared across parent-child runs | Maintains coherent conversation history for chat scenarios |
