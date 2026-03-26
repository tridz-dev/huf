---
name: flow-engine
category: features
---

# Flow Engine

Graph-based workflow orchestration system for HUF that enables complex multi-step AI agent workflows with deterministic execution, LLM-based routing, and human-in-the-loop capabilities.

## Overview

The Flow Engine provides a visual, graph-based approach to building workflows. It reuses existing HUF primitives (Agent Run, Conversation, Messages, Tools) and adds only what's necessary to coordinate multi-step flows.

### Key Concepts

1. **Flow Definition**: Stores the entire graph as a single JSON blob (React Flow compatible). No separate Node/Edge DocTypes.
2. **Flow Run**: Persists runtime state (status, context, current node, hop count).
3. **Agent Run as Node Run**: Each node execution is logged as an existing Agent Run extended with flow linkage fields.

## Key Files

| File | Purpose |
|------|---------|
| `huf/huf/doctype/flow_definition/flow_definition.py` | DocType for storing flow graph definitions |
| `huf/huf/doctype/flow_run/flow_run.py` | DocType for flow execution instances |
| `huf/ai/flow_engine.py` | Core orchestration engine - load, validate, execute |
| `huf/ai/flow_api.py` | Whitelisted API endpoints for UI and triggers |
| `huf/ai/flow_eval.py` | Safe AST-based expression evaluator |
| `huf/ai/flow_tool_executor.py` | Deterministic tool execution for tool.call nodes |
| `huf/ai/flow_orchestrator.py` | Prompt construction and JSON parsing for routing |
| `huf/ai/flow_tools.py` | Tool definitions for huf_tools hook |
| `frontend/src/components/FlowCanvas.tsx` | React Flow visual editor |
| `frontend/src/components/FlowNode.tsx` | Node rendering component |
| `frontend/src/services/flowService.ts` | Frontend flow management service |
| `frontend/src/types/flow.types.ts` | TypeScript type definitions |

## How It Works

### Execution Flow

```
1. Trigger (Manual/Webhook/Schedule/Doc Event)
   ↓
2. create_flow_run() - Creates FlowRun doc with context
   ↓
3. run_flow() - Main execution loop
   ↓
4. _execute_loop() - While not complete:
   ├── Load current node from nodes_map
   ├── Check hop limit (default 100)
   ├── _execute_node() based on type
   │   ├── trigger.webhook → passthrough
   │   ├── agent.run → run_agent_sync()
   │   ├── tool.call → flow_tool_executor.execute()
   │   ├── router.llm → LLM routing decision
   │   ├── human.approval → pause, set Waiting Approval
   │   └── end → mark complete
   ├── If paused (Waiting Approval/User) → exit
   ├── _evaluate_edges() OR _call_orchestrator()
   └── Move to next node
   ↓
5. _complete_flow_run() OR _fail_flow_run()
```

### Node Types (v0.1)

| Type | Description | Configuration |
|------|-------------|---------------|
| `trigger.webhook` | Entry point for webhook-triggered flows | `auth` for webhook validation |
| `agent.run` | Execute a HUF agent | `agent_name`, `prompt_template`, `output.save_response_to_context` |
| `tool.call` | Deterministic tool execution | `tool_name`, `args`, `output.save_result_to_context` |
| `router.llm` | LLM-based routing among candidates | `router_agent_name`, `inject.*` flags |
| `human.approval` | Pause for human decision | `approval_type`, `approver_role`/`approver_users` |
| `end` | Termination node | - |

### Edge Types

| Type | Description |
|------|-------------|
| `always` | Always follow this edge |
| `on_success` | Follow if previous node succeeded |
| `on_failure` | Follow if previous node failed |
| `expression` | Evaluate expression against context (see below) |

Edges are sorted by priority (descending); first match wins.

### Expression Edge Syntax

Expression edges use safe AST evaluation:

```python
# Valid expressions
context["status"] == "approved"
context["amount"] > 1000 and context["priority"] == "high"
context["user_id"] in ["user1", "user2"]
context["tags"] and len(context["tags"]) > 0
```

**Allowed**: dict subscript access, comparisons, boolean operators, arithmetic, literals
**Not Allowed**: function calls, attribute access (dot notation), imports, assignments

See `flow_eval.py` for the complete safe evaluator implementation.

### Execution Modes

#### Normal Mode
Engine follows edges deterministically based on edge types and conditions.

#### Agentic Mode
An orchestrator agent is invoked after each node to decide the next step:

```python
# Agentic mode settings in flow definition
{
  "settings": {
    "mode": "agentic",
    "orchestrator_agent": "my-orchestrator",
    "orchestrator_call_policy": "after_each_node"  # or "start_and_after_each_node"
  }
}
```

The orchestrator receives:
- Completed node result
- Current flow context
- Candidate edges
- Summary of completed nodes

Returns strict JSON: `{"next_node_id": "...", "context_patch": {...}, "message": "..."}`

### Conversation Modes

| Mode | Behavior |
|------|----------|
| `flow_shared` | Single conversation for entire flow (default) |
| `node_isolated` | Each node gets its own conversation |
| `agent_default` | Use agent's default conversation behavior |

### Context & Variable Substitution

Flow context is a JSON dictionary that persists across nodes:

```python
# In agent.run nodes, use template syntax:
{
  "input": {
    "prompt_template": "Process this order: {{order_id}} for customer {{customer_name}}"
  },
  "output": {
    "save_response_to_context": "agent_result"
  }
}

# In tool.call nodes, use {{}} syntax in args:
{
  "args": {
    "order_id": "{{order_id}}",
    "status": "processed"
  }
}
```

## Extension Points

### Adding a New Node Type

1. **Add to ALLOWED_NODE_TYPES** in `flow_definition.py`:
```python
ALLOWED_NODE_TYPES = {
    # ... existing types
    "my.custom_node",
}
```

2. **Add executor in `flow_engine.py`**:
```python
def _execute_node(flow_run, node: dict, settings: dict) -> dict:
    executors = {
        # ... existing executors
        "my.custom_node": _exec_my_custom_node,
    }
    # ...

def _exec_my_custom_node(flow_run, node: dict, config: dict, settings: dict) -> dict:
    """Execute my custom node."""
    # Implementation
    return {"status": "success", "output": result}
```

3. **Add frontend node component** in `FlowCanvas.tsx` or custom node component.

4. **Add TypeScript types** in `flow.types.ts`.

### Adding a New Edge Type

1. **Add to ALLOWED_EDGE_TYPES** in `flow_definition.py`:
```python
ALLOWED_EDGE_TYPES = {"always", "on_success", "on_failure", "expression", "my_custom"}
```

2. **Add evaluation logic in `flow_engine.py`**:
```python
def _evaluate_edges(flow_run, node_id: str, node_result: dict, edges_list: list) -> str | None:
    for edge in outgoing:
        edge_type = edge.get("type", "always")
        
        if edge_type == "my_custom":
            if _evaluate_my_custom_condition(edge, ctx, node_result):
                return edge.get("to")
```

## Whitelisted APIs

### Flow Definition Management

```python
# Get flow definition
huf.ai.flow_api.get_flow_definition(flow_id: str) -> dict

# Save flow definition
huf.ai.flow_api.save_flow_definition(flow_id: str, definition_json: str | dict) -> dict
```

### Flow Run Lifecycle

```python
# Start a flow run
huf.ai.flow_api.run_flow(flow_id: str, payload: dict = None, mode: str = None) -> dict

# Get flow run status
huf.ai.flow_api.get_flow_run(flow_run_id: str) -> dict

# List flow runs
huf.ai.flow_api.list_flow_runs(flow_id: str = None, status: str = None, limit: int = 20) -> list

# Resume waiting flow
huf.ai.flow_api.resume_flow_run(flow_run_id: str, input: dict = None) -> dict

# Approve/reject flow
huf.ai.flow_api.approve_flow_run(flow_run_id: str, comment: str = None) -> dict
huf.ai.flow_api.reject_flow_run(flow_run_id: str, comment: str = None) -> dict

# Webhook trigger (allow_guest)
huf.ai.flow_api.flow_webhook(flow_id: str, webhook_key: str = None) -> dict
```

### Agent Tools

These are automatically registered via `huf_tools` hook:

```python
# Run a flow from within an agent
huf.ai.flow_api.handle_run_flow(flow_id: str, payload: dict = None, mode: str = None) -> dict

# Check flow status
huf.ai.flow_api.handle_get_flow_run(flow_run_id: str) -> dict

# Resume a waiting flow
huf.ai.flow_api.handle_resume_flow_run(flow_run_id: str, input: dict = None) -> dict

# Approve/reject
huf.ai.flow_api.handle_approve_flow_run(flow_run_id: str, decision: str, comment: str = None) -> dict
```

## Flow Definition JSON Schema (v0.1)

```json
{
  "schema_version": 1,
  "id": "my-flow",
  "version": 1,
  "entry": "node-1",
  "nodes": [
    {
      "id": "node-1",
      "type": "trigger.webhook",
      "position": {"x": 100, "y": 100},
      "config": {"auth": "secret-key"}
    },
    {
      "id": "node-2",
      "type": "agent.run",
      "position": {"x": 300, "y": 100},
      "config": {
        "agent_name": "classifier",
        "input": {"prompt_template": "Classify: {{input_text}}"},
        "output": {"save_response_to_context": "classification"}
      }
    }
  ],
  "edges": [
    {
      "id": "edge-1",
      "from": "node-1",
      "to": "node-2",
      "type": "always",
      "priority": 10
    }
  ],
  "settings": {
    "mode": "normal",
    "max_hops": 100,
    "conversation_mode": "flow_shared"
  },
  "metadata": {
    "name": "My Flow",
    "description": "Classifies incoming requests"
  }
}
```

## Dependencies

### Backend
- Frappe Framework
- HUF Agent Integration (`huf.ai.agent_integration`)
- HUF SDK Tools (`huf.ai.sdk_tools`)
- HUF HTTP Handler (`huf.ai.http_handler`)

### Frontend
- React Flow (visual canvas)
- React Context API (state management)
- TypeScript

## Gotchas

### Security
- **Expression edges use AST-based safe evaluation** - no function calls, no attribute access, no imports
- **Hop limit (default 100)** prevents infinite loops
- **Human approval requires role/user verification** - `_verify_approval_permission()` checks approver_role or approver_users
- **Webhook auth** - entry node config can specify expected auth key

### Context Persistence
- Context is stored as JSON in `FlowRun.context_json`
- Non-serializable values will be lost or converted to strings
- Large contexts may impact performance

### Tool Execution
- Tool.call nodes use the same handlers as agent tools via `flow_tool_executor.py`
- Async tool results are automatically awaited
- Tool execution failures set node status to "failed" and can trigger `on_failure` edges

### Router Nodes
- Router agents MUST return valid JSON with `next_node_id`
- The `next_node_id` is validated against candidate edges
- Invalid responses fail the flow

### Approval Flows
- When approved/rejected, the decision is stored in context under the key specified by `store_decision_in_context` (default: "approval")
- The engine looks for outgoing edges with matching `outcome` in edge meta
- If no matching edge found, flow fails

### Agentic Mode
- Requires `orchestrator_agent` in settings
- Orchestrator responses are parsed with strict JSON validation
- Context patches from orchestrator are applied before continuing

### Webhook Triggers
- Run in background queue (not synchronous)
- Auth key is checked against entry node config
- Payload is extracted from request body or form data

### Versioning
- Flow Definition version auto-increments on save
- Flow Run pins to the version at creation time
- Changes to a flow don't affect in-progress runs
