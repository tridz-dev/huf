# HUF Flow Engine Skill

Complete guide to understanding, creating, and executing workflows in the HUF Flow Engine.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Concepts](#core-concepts)
3. [DocTypes](#doctypes)
4. [Creating Flows](#creating-flows)
5. [Running Flows](#running-flows)
6. [Node Types](#node-types)
7. [Storage & Execution](#storage--execution)
8. [Debugging & Monitoring](#debugging--monitoring)
9. [Common Patterns](#common-patterns)

---

## Architecture Overview

The Flow Engine provides graph-based workflow orchestration that reuses existing HUF primitives (Agent Run, Conversation, Messages, Tools) and adds only what's necessary to coordinate multi-step flows.

```
┌─────────────────────────────────────────────────────────────┐
│                    FLOW DEFINITION                          │
│  (Stores the entire graph as JSON - React Flow compatible)  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      FLOW RUN                               │
│  (Runtime state: status, context, current node, hop count)  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    AGENT RUN                                │
│  (Each node execution logged as Agent Run with flow linkage)│
└─────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Single JSON Storage**: Flow definition stored as one JSON blob (React Flow compatible)
2. **No Separate Node/Edge Doctypes**: Everything in `definition_json` field
3. **Agent Run as Node Run**: Each execution logged as existing Agent Run extended with flow linkage
4. **Context Passing**: Shared state passed between nodes via context JSON

---

## Core Concepts

### Flow Definition
Stores the complete workflow graph definition including nodes, edges, and metadata.

### Flow Run
Single execution instance of a flow with:
- **Status**: `Queued` → `Running` → (`Success`|`Failed`|`Waiting Approval`|`Waiting User`)
- **Context**: Shared state between nodes (JSON)
- **Hop Count**: Steps executed (safety limit: default 100)
- **Current Node**: Position in graph

### Execution Modes

| Mode | Description |
|------|-------------|
| **Normal** | Engine follows edges deterministically |
| **Agentic** | Orchestrator agent decides next step after each node |

### Context & Variable Substitution

Nodes can reference context variables using `{{variable}}` syntax:

```json
{
  "parameters": {
    "description": "Task: {{title}}",
    "priority": "{{priority}}"
  }
}
```

Context is built from:
1. `trigger_payload` (initial input)
2. Node `output` configurations (save results to context)

---

## DocTypes

### Flow Definition

Stores the complete workflow graph as JSON.

**Key Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `flow_id` | Data | Stable unique ID used by APIs |
| `flow_name` | Data | Human-readable name |
| `status` | Select | `Draft`, `Active`, `Archived` |
| `version` | Int | Auto-increments on save |
| `definition_json` | JSON | Full graph (nodes + edges) |
| `is_system` | Check | System-shipped vs user-created |

**Python Class**: `FlowDefinition(Document)`  
**File**: `huf/huf/doctype/flow_definition/flow_definition.py`

**Validation:**
- `definition_json.id` must equal `flow_id`
- Node IDs must be unique
- Edges must reference valid node IDs
- Entry node must exist

### Flow Run

Single execution instance.

**Key Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `flow_definition` | Link | Link to Flow Definition |
| `flow_id` | Data | Denormalized flow ID |
| `mode` | Select | `Normal`, `Agentic` |
| `status` | Select | `Queued`, `Running`, `Waiting Approval`, `Waiting User`, `Success`, `Failed` |
| `current_node_id` | Data | Current position in graph |
| `hop_count` | Int | Steps executed |
| `context_json` | JSON | Shared flow state |
| `trigger_payload` | JSON | Initial input |
| `waiting` | JSON | Details when paused |

**Python Class**: `FlowRun(Document)`  
**File**: `huf/huf/doctype/flow_run/flow_run.py`

### Agent Run (Extended)

Existing Agent Run with additional flow linkage fields.

**New Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `flow_run` | Link | Optional link to flow |
| `flow_node_id` | Data | Node ID from JSON |
| `flow_id` | Data | Convenience field |
| `run_kind` | Select | `agent`, `tool`, `orchestrator` |

---

## Creating Flows

### Flow Definition JSON Structure

```json
{
  "schema_version": 1,
  "id": "my-flow-v1",
  "version": 1,
  "entry": "trigger-1",
  "nodes": [...],
  "edges": [...],
  "settings": {...},
  "metadata": {...}
}
```

### Node Structure

```json
{
  "id": "node-1",
  "type": "tool.call",
  "config": {
    "tool_name": "create_document",
    "parameters": {
      "reference_doctype": "ToDo",
      "description": "Task: {{title}}"
    },
    "output": {
      "save_result_to_context": "todo_result"
    }
  },
  "_position": {"x": 100, "y": 200},
  "_label": "Create ToDo",
  "_icon": "check-square"
}
```

### Edge Structure

```json
{
  "id": "edge-1",
  "from": "trigger-1",
  "to": "action-1",
  "type": "always",
  "priority": 1,
  "condition": "status == 'success'"
}
```

### Creating via Python

```python
import frappe
import json

# Create flow definition
flow = frappe.new_doc("Flow Definition")
flow.flow_id = "my-flow-v1"
flow.flow_name = "My Workflow"
flow.status = "Active"

definition = {
    "schema_version": 1,
    "id": "my-flow-v1",
    "version": 1,
    "entry": "trigger-1",
    "nodes": [
        {
            "id": "trigger-1",
            "type": "trigger.webhook",
            "config": {}
        },
        {
            "id": "action-1",
            "type": "tool.call",
            "config": {
                "tool_name": "create_document",
                "parameters": {
                    "reference_doctype": "ToDo",
                    "description": "{{title}}"
                }
            }
        },
        {
            "id": "end-1",
            "type": "end",
            "config": {}
        }
    ],
    "edges": [
        {"id": "e1", "from": "trigger-1", "to": "action-1", "type": "always"},
        {"id": "e2", "from": "action-1", "to": "end-1", "type": "always"}
    ],
    "settings": {"max_hops": 100},
    "metadata": {"category": "automation"}
}

flow.definition_json = json.dumps(definition)
flow.save()
```

### Creating via API

```python
from huf.ai.flow_api import save_flow_definition

flow_def = save_flow_definition(
    flow_id="my-flow-v1",
    definition_json=definition
)
```

---

## Running Flows

### Via Python API

```python
from huf.ai.flow_api import run_flow, get_flow_run

# Start flow execution
result = run_flow(
    flow_id="my-flow-v1",
    mode="Normal",  # or "Agentic"
    payload={"title": "My Task", "priority": "High"}
)

print(f"Run ID: {result['flow_run_id']}")
print(f"Status: {result['status']}")

# Check status
run = get_flow_run(result['flow_run_id'])
print(f"Current Status: {run['status']}")
print(f"Hop Count: {run['hop_count']}")
```

### Via Webhook Trigger

Configure a `trigger.webhook` node and call:

```bash
curl -X POST "http://localhost:8000/api/method/huf.ai.flow_api.flow_webhook" \
  -H "Content-Type: application/json" \
  -d '{"flow_id": "my-flow-v1", "payload": {"title": "Task"}}'
```

### Execution Flow

1. **Flow Run Created**: Status = `Queued`
2. **Entry Node Found**: From `definition_json.entry`
3. **Loop Begins**:
   - Execute current node
   - Evaluate outgoing edges
   - Move to next node
   - Increment hop count
4. **Completion**: Status = `Success` or `Failed`

---

## Node Types

### v0.1 Supported Types

| Type | Purpose | Config Required |
|------|---------|-----------------|
| `trigger.webhook` | Entry point | None |
| `agent.run` | Run HUF agent | `agent_name` |
| `tool.call` | Deterministic tool | `tool_name`, `parameters` |
| `router.llm` | LLM-based routing | `prompt`, `candidates` |
| `human.approval` | Pause for approval | `approver_role` |
| `end` | Terminate flow | None |

### Tool.Call Node

Executes Agent Tool Function deterministically (no LLM).

```json
{
  "id": "create-todo",
  "type": "tool.call",
  "config": {
    "tool_name": "create_document",
    "parameters": {
      "reference_doctype": "ToDo",
      "description": "{{task_title}}"
    },
    "output": {
      "save_result_to_context": "created_todo"
    }
  }
}
```

**Standard Tools** (built-in, no document needed):
- `create_document` - Create Frappe document
- `get_document` - Get single document
- `update_document` - Update document
- `delete_document` - Delete document
- `get_list` - Get list of documents
- `submit_document` - Submit submittable document
- `cancel_document` - Cancel submitted document

### Agent.Run Node

Runs a HUF agent with context-aware prompt.

```json
{
  "id": "process-data",
  "type": "agent.run",
  "config": {
    "agent_name": "Data Processor",
    "prompt_template": "Process this data: {{input_data}}",
    "output": {
      "save_response_to_context": "processed_result"
    }
  }
}
```

### Human.Approval Node

Pauses flow for human approval/rejection.

```json
{
  "id": "manager-approval",
  "type": "human.approval",
  "config": {
    "approver_role": "Manager",
    "timeout_hours": 24,
    "reminder_interval": 4
  }
}
```

**Resuming:**
```python
from huf.ai.flow_api import approve_flow_run, reject_flow_run

# Approve
approve_flow_run(flow_run_id, approver="user@example.com", comments="LGTM")

# Reject
reject_flow_run(flow_run_id, approver="user@example.com", comments="Needs changes")
```

---

## Storage & Execution

### How Flows Are Stored

1. **Flow Definition**: Single document with JSON blob
2. **No Node/Edge Tables**: Everything in `definition_json`
3. **Versioning**: Auto-increment on save
4. **Validation**: JSON schema validation on save

### How Runs Are Stored

1. **Flow Run Document**: Tracks execution state
2. **Agent Run Documents**: Each node execution logged
3. **Context**: Updated after each node (if output configured)
4. **Audit Trail**: Complete history via linked Agent Runs

### Context Lifecycle

```
Trigger Payload: {"title": "Task", "priority": "High"}
       ↓
Initial Context: {"title": "Task", "priority": "High"}
       ↓
Node 1 (tool.call): Creates ToDo
       ↓
Context Update: {"title": "Task", "priority": "High", "todo_result": {...}}
       ↓
Node 2 (tool.call): Uses {{todo_result.name}}
       ↓
Final Context: {"title": "Task", ..., "todo_result": {...}, "followup_result": {...}}
```

### Execution Safety

- **Hop Limit**: Default 100 (prevents infinite loops)
- **Error Handling**: Failed nodes don't stop flow (configurable)
- **Transaction Safety**: Each node commits independently

---

## Debugging & Monitoring

### Check Flow Run Status

```python
from huf.ai.flow_api import get_flow_run

run = get_flow_run("flow-run-id")
print(f"Status: {run['status']}")
print(f"Current Node: {run['current_node_id']}")
print(f"Hops: {run['hop_count']}")
print(f"Context: {run['context_json']}")
print(f"Error: {run.get('last_error')}")
```

### List Recent Runs

```python
from huf.ai.flow_api import list_flow_runs

runs = list_flow_runs(flow_id="my-flow-v1", limit=10)
for run in runs:
    print(f"{run['name']}: {run['status']} ({run['hop_count']} hops)")
```

### Check Agent Runs

```python
agent_runs = frappe.get_all("Agent Run",
    filters={"flow_run": "flow-run-id"},
    fields=["flow_node_id", "status", "prompt", "response"],
    order_by="creation asc"
)

for ar in agent_runs:
    print(f"Node {ar['flow_node_id']}: {ar['status']}")
    print(f"  Prompt: {ar['prompt'][:100]}...")
    print(f"  Response: {ar['response'][:100]}...")
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Tool not found" | Missing Agent Tool Function | Create document or use standard tool |
| "Node not found" | Invalid edge reference | Check edge `from`/`to` match node IDs |
| Context variables not substituted | Wrong variable path | Use `{{variable}}` not `{{obj.property}}` |
| Flow stops early | No matching edge | Check edge conditions and priorities |

---

## Common Patterns

### Pattern 1: Sequential Processing

```
trigger → tool.call → tool.call → end
```

Chain multiple tool executions.

### Pattern 2: Conditional Branching

```
trigger → router.llm → [branch A → end]
                              → [branch B → end]
```

Use `router.llm` for LLM-based routing.

### Pattern 3: Human Approval

```
trigger → tool.call → human.approval → [approve → tool.call → end]
                                               → [reject → end]
```

Pause for approval before continuing.

### Pattern 4: Agent + Tools

```
trigger → agent.run (decides) → tool.call (executes) → end
```

Agent decides parameters, tool executes deterministically.

---

## Files Reference

| File | Purpose |
|------|---------|
| `huf/ai/flow_engine.py` | Core execution engine |
| `huf/ai/flow_api.py` | Whitelisted API endpoints |
| `huf/ai/flow_tool_executor.py` | Deterministic tool execution |
| `huf/ai/flow_orchestrator.py` | Agentic mode orchestrator |
| `huf/ai/flow_eval.py` | Safe expression evaluator |
| `huf/doctype/flow_definition/flow_definition.py` | Flow Definition Doctype |
| `huf/doctype/flow_run/flow_run.py` | Flow Run Doctype |

---

## Quick Reference

### Creating a Simple Flow

```python
import frappe
import json

flow = frappe.new_doc("Flow Definition")
flow.flow_id = "todo-flow-v1"
flow.flow_name = "Create ToDo Flow"
flow.status = "Active"
flow.definition_json = json.dumps({
    "schema_version": 1,
    "id": "todo-flow-v1",
    "version": 1,
    "entry": "trigger-1",
    "nodes": [
        {"id": "trigger-1", "type": "trigger.webhook", "config": {}},
        {
            "id": "create-todo",
            "type": "tool.call",
            "config": {
                "tool_name": "create_document",
                "parameters": {
                    "reference_doctype": "ToDo",
                    "description": "{{title}}"
                }
            }
        },
        {"id": "end-1", "type": "end", "config": {}}
    ],
    "edges": [
        {"id": "e1", "from": "trigger-1", "to": "create-todo", "type": "always"},
        {"id": "e2", "from": "create-todo", "to": "end-1", "type": "always"}
    ]
})
flow.save()
```

### Running the Flow

```python
from huf.ai.flow_api import run_flow

result = run_flow("todo-flow-v1", payload={"title": "My Task"})
print(f"Started: {result['flow_run_id']}")
```

---

*Last updated: 2026-03-29*
