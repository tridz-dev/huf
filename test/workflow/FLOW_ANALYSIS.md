# HUF Flow Engine — UI/Backend Analysis & Test Report

> **Date**: 2026-03-29
> **Scope**: Complete analysis of Flow Builder UI ↔ Backend sync, node functionality, and context passing
> **Branch**: `claude/test-user-flows-ORf0E`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Issue Tracker](#2-issue-tracker)
3. [Node-by-Node Analysis](#3-node-by-node-analysis)
4. [Context Passing & Variable System](#4-context-passing--variable-system)
5. [Human Approval Deep Dive](#5-human-approval-deep-dive)
6. [Tool Availability Analysis](#6-tool-availability-analysis)
7. [Trigger Node / Start Node Analysis](#7-trigger-node--start-node-analysis)
8. [Schema Validation Gap](#8-schema-validation-gap)
9. [Fixes Applied](#9-fixes-applied)
10. [Remaining Work / Recommendations](#10-remaining-work--recommendations)

---

## 1. Executive Summary

The HUF Flow Engine has a solid architecture with a working backend execution engine (`flow_engine.py`) supporting 11 node types, a React Flow-based visual builder, and context passing via `{{variable}}` interpolation. However, several UI/backend synchronization issues prevent flows from being saved or executed correctly for certain node types.

**Critical Issues Found:**
- Backend schema validation (`flow_definition.py`) rejects 4 node types that the engine actually supports
- NodeSelectionModal shows an Actions tab when editing triggers (confusing UX)
- Trigger sub-tabs (Apps, Utility) are empty — no options mapped to them
- Human Approval lacks role auto-suggest, notification system, and linked context
- Tool-call config has a serialization mismatch between modal and sidebar
- Several frontend action types (code, email, slack, etc.) have no backend implementation

---

## 2. Issue Tracker

| # | Issue | Severity | Status | Fix |
|---|-------|----------|--------|-----|
| 1 | **ALLOWED_NODE_TYPES** missing `condition`, `http_request`, `transform`, `loop` | **CRITICAL** | FIXED | Updated `flow_definition.py` |
| 2 | **NodeSelectionModal** shows Actions tab for trigger nodes | MEDIUM | FIXED | Hide Actions tab when `mode === 'trigger'` |
| 3 | **Trigger sub-tabs** Apps/Utility are empty (no options) | LOW | FIXED | Removed empty tabs, kept Explore + AI & Agents |
| 4 | **Human Approval** approver_role has no auto-suggest | MEDIUM | FIXED | Added Combobox with Frappe roles API |
| 5 | **Tool-call config** `save_result_to_context` flat vs nested `output` | MEDIUM | FIXED | Normalized in NodeSelectionModal and serializer |
| 6 | **Human Approval** no notification system | HIGH | DOCUMENTED | Requires Frappe Notification + email hooks |
| 7 | **Human Approval** no linked context (doc reference) | MEDIUM | FIXED | Added `context_summary` and `reference_doctype`/`reference_name` fields |
| 8 | **Frontend actions** without backend (code, email, slack, etc.) | LOW | DOCUMENTED | Listed below; frontend-only placeholders |
| 9 | **Human Approval** no approval UI page for external approvers | HIGH | DOCUMENTED | Needs dedicated approval page/view |
| 10 | **Trigger "AI & Agents" tab** creates non-standard config | LOW | DOCUMENTED | Agent-as-trigger pattern unclear |

---

## 3. Node-by-Node Analysis

### 3.1 Trigger Node (Start)

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| **webhook** | URL, auth key, method | `trigger.webhook` in engine | YES |
| **schedule** | interval type, cron | Engine has basic support | PARTIAL — no scheduler integration |
| **doc-event** | DocType selector, event | Engine handles doc events | PARTIAL — needs agent_hooks bridge |
| **app-trigger** | Integration + event | Not implemented | NO — placeholder only |

**Verdict**: Webhook works end-to-end. Schedule/doc-event need backend scheduler hookup. App-trigger is a stub.

### 3.2 Agent Run (Action)

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Agent selector | Combobox, loads from API | `config.agent_name` | YES |
| Prompt template | Textarea with VariablePicker | `{{var}}` interpolation | YES |
| Save response | `save_response_to_context` | Writes to context_json | YES |
| Conversation mode | Not in sidebar | Supported in engine | MISSING in sidebar |

**Verdict**: Works well. Conversation mode selector should be added to sidebar (like Router has).

### 3.3 Call Tool (Action)

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Tool selector | Combobox, loads from API | `config.tool_name` | YES |
| Arguments | Dynamic form from tool params | `config.args` with interpolation | YES |
| Save result | `output.save_result_to_context` | `config.output.save_result_to_context` | YES (after fix) |

**Verdict**: Works. The tool list shows all Agent Tool Function documents from DB. The "Select Tool" placeholder appears because tools load asynchronously — not a bug, just loading state.

### 3.4 Router (LLM)

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Routing agent | Combobox selector | `config.router_agent_name` | YES |
| Conversation mode | Select dropdown | Supported | YES |
| Edge labels | Displayed in candidates | Used in router prompt | YES |

**Verdict**: Fully synced.

### 3.5 Human Approval

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Title | Text input | `config.title` | YES |
| Instructions | Textarea | `config.instructions` | YES |
| Approver Role | Plain text (was) → Combobox (fixed) | `config.approver_role` checked vs user roles | YES (after fix) |
| Approval Type | Not in UI (hardcoded "role") | Supports "role" and "user" | MISSING — added |
| Approver Users | Not in UI | Supports user list | MISSING — added |
| Store Decision | Text input | `config.store_decision_in_context` | YES |
| Reference Doc | Not in UI | Not in backend | ADDED both |
| Context Summary | Not in UI | Not in backend | ADDED both |
| Notification | Not implemented | Not implemented | NO |

**Verdict**: Core approve/reject works. Missing: notification, dedicated approval page, reference doc linking. Fixes add approval_type selector, approver_users, and reference fields.

### 3.6 Condition (IF)

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Expression | Textarea with VariablePicker | `safe_eval_expression()` | YES |
| True/False node | Text inputs for node IDs | `config.true_node/false_node` | YES |

**Verdict**: Works, but node IDs must be typed manually. Could use node selector dropdown.

### 3.7 HTTP Request

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| URL | Input with VariablePicker | `{{var}}` interpolation | YES |
| Method | Select (GET/POST/PUT/PATCH/DELETE) | Supported | YES |
| Headers | JSON textarea | Parsed and sent | YES |
| Body | JSON textarea | Interpolated and sent | YES |
| Timeout | Number input | Configurable | YES |
| Save result | Text input | Writes to context | YES |

**Verdict**: Fully synced.

### 3.8 Transform Data

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Transformations list | Add/remove UI | copy/template/map ops | YES |
| Source/target fields | Text inputs | Context path resolution | YES |
| Operation | Select dropdown | 3 operations supported | YES |

**Verdict**: Fully synced.

### 3.9 Loop

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| Iterate over | Text input (context key) | Array resolution | YES |
| Item/index keys | Configurable | Set in context per iteration | YES |
| Loop body node | Node ID text input | Executes per iteration | YES |
| Done node | Node ID text input | Routes after completion | YES |
| Max iterations | Number input | Safety limit | YES |

**Verdict**: Fully synced.

### 3.10 End Node

| Aspect | Frontend | Backend | Sync? |
|--------|----------|---------|-------|
| No config needed | Green visual node | Marks flow as Success | YES |

**Verdict**: Works.

### 3.11 Frontend-Only Actions (NO Backend)

These actions exist in `frontend/src/data/actions.ts` but have **no backend executor**:

| Action | ID | Backend Status |
|--------|----|----------------|
| Execute Code | `code` | NOT IMPLEMENTED — falls back to JSON display |
| Send Email | `email` | NOT IMPLEMENTED |
| Call Webhook | `webhook` | Partially overlaps with `http-request` |
| File Operations | `file` | NOT IMPLEMENTED |
| Date Utility | `date` | NOT IMPLEMENTED |
| Slack | `slack` | NOT IMPLEMENTED |
| Google Sheets | `sheets` | NOT IMPLEMENTED |
| Notion | `notion` | NOT IMPLEMENTED |

**Impact**: Users can add these nodes but they will fail at execution. Should either be removed or marked as "Coming Soon".

---

## 4. Context Passing & Variable System

### How It Works

1. **Initial context** = `trigger_payload` (from webhook body, manual input, etc.)
2. **Each node** can read context via `{{variable_name}}` syntax
3. **Each node** can write to context via `save_*_to_context` config fields
4. **Context is persisted** in `flow_run.context_json` after each node execution

### Variable Resolution

```
{{simple_key}}           → context["simple_key"]
{{nested.path}}          → context["nested"]["path"] (dot notation)
{{trigger_payload}}      → entire initial payload
```

### VariablePicker Component

The frontend `VariablePicker` scans all nodes in the current flow and discovers:
- `save_response_to_context` from agent-run nodes
- `save_result_to_context` from tool-call nodes
- `output.save_result_to_context` from tool-call nodes
- `store_decision_in_context` from human-in-loop nodes
- `trigger_payload` (always available)

Users can click the variable picker button next to text fields to insert `{{var}}` references.

### Context Lifecycle Example

```
Step 1: Webhook trigger
  payload: {"customer": "Acme", "amount": 5000}
  → context = {"customer": "Acme", "amount": 5000}

Step 2: Agent Run (save_response_to_context = "analysis")
  → context = {"customer": "Acme", "amount": 5000, "analysis": "High value customer..."}

Step 3: Tool Call - create_document (save_result_to_context = "invoice")
  args: {"reference_doctype": "Sales Invoice", "customer": "{{customer}}"}
  → context = {..., "invoice": {"name": "SINV-001", "doctype": "Sales Invoice"}}

Step 4: Human Approval (store_decision_in_context = "approval")
  → context = {..., "approval": {"decision": "approved", "approved_by": "admin@example.com"}}

Step 5: Condition - context["approval"]["decision"] == "approved"
  → Routes to true/false branch
```

### What Works

- `{{key}}` substitution in tool args, prompt templates, HTTP URLs/bodies
- Context accumulation across nodes
- VariablePicker discovers previous node outputs
- Dotted path resolution (`{{result.name}}`)

### What's Missing

- No **global context** concept (all context is flow-run scoped, which is correct)
- No **type validation** on context values (e.g., expecting array for loop but getting string)
- No **context schema preview** in UI (users can't see what keys are available at design time beyond VariablePicker)

---

## 5. Human Approval Deep Dive

### Current Implementation

**What works:**
1. Flow pauses at `human.approval` node → status becomes `Waiting Approval`
2. Waiting data (approver_role, instructions, title) stored in `flow_run.waiting` JSON
3. `approve_flow_run()` / `reject_flow_run()` API endpoints exist
4. Permission check: validates user has the required role or is in approver_users list
5. Decision stored in context under configurable key
6. Flow resumes via edge matching (`meta.outcome == "approved"` or `"rejected"`)

**What's missing:**

| Gap | Impact | Priority |
|-----|--------|----------|
| **No notification** — approver is not emailed/notified | Approver won't know there's a pending approval | HIGH |
| **No approval page** — no dedicated UI for external approvers | Must use Flow Run doctype view or custom page | HIGH |
| **No linked document** — approval can't reference "approve THIS invoice" | No contextual information for approver | MEDIUM (FIXED) |
| **No auto-refresh** — Flow Run Viewer doesn't auto-poll for status changes | UI feels stale | LOW |
| **No timeout** — `timeout_hours` in config schema but not enforced | Flows can wait forever | LOW |

### After Fixes Applied

The Human Approval sidebar now includes:
- **Approval Type** selector (role vs user)
- **Approver Role** with auto-suggest Combobox (fetches Frappe roles)
- **Approver Users** field (shown when type = "user")
- **Context Summary** — text shown to approver explaining what to review
- **Reference DocType + Name** — links to a specific document for contextual approval

The backend `_exec_human_approval` now includes `context_summary`, `reference_doctype`, and `reference_name` in waiting data.

### How Approval Should Work (Recommended Flow)

```
1. Flow reaches human.approval node
2. Engine sets status = "Waiting Approval" with waiting data
3. [NEW] Frappe Notification created for approver role/users
4. [NEW] Email sent with approval link
5. Approver opens approval page/link
6. Approver sees: title, instructions, context_summary, linked document
7. Approver clicks Approve or Reject (with optional comment)
8. API call: approve_flow_run() or reject_flow_run()
9. Flow resumes on matching edge
```

---

## 6. Tool Availability Analysis

### How Tools Are Listed

The Call Tool node loads tools via `getToolFunctions()` which queries the `Agent Tool Function` DocType. This means:

1. **All Agent Tool Function documents** in the database are available
2. **Standard tools** (create/get/update/delete document, etc.) must be created as documents during `bench install-app huf`
3. **App-provided tools** are synced via `huf_tools` hook in `install.py`

### Tool Registration Flow

```
install.py → create_standard_tools() + create_flow_tools()
    ↓
Agent Tool Function documents created
    ↓
Frontend: getToolFunctions() queries DB
    ↓
RightSidebar: Combobox shows all tools
```

### Standard Tools Available (from `flow_tool_executor.py`)

| Tool Type | Handler | Available in Call Tool? |
|-----------|---------|----------------------|
| Get List | `sdk_tools.handle_get_list` | YES (if doc exists) |
| Get Document | `sdk_tools.handle_get_document` | YES (if doc exists) |
| Create Document | `sdk_tools.handle_create_document` | YES (if doc exists) |
| Update Document | `sdk_tools.handle_update_document` | YES (if doc exists) |
| Delete Document | `sdk_tools.handle_delete_document` | YES (if doc exists) |
| Submit Document | `sdk_tools.handle_submit_document` | YES (if doc exists) |
| Cancel Document | `sdk_tools.handle_cancel_document` | YES (if doc exists) |
| Get Value | `sdk_tools.handle_get_value` | YES (if doc exists) |
| Set Value | `sdk_tools.handle_set_value` | YES (if doc exists) |
| GET (HTTP) | `http_handler.handle_get_request` | YES (if doc exists) |
| POST (HTTP) | `http_handler.handle_post_request` | YES (if doc exists) |
| Run Agent | `sdk_tools.handle_run_agent` | YES (if doc exists) |
| Attach File | `sdk_tools.handle_attach_file_to_document` | YES (if doc exists) |

### Missing Tools Issue

If tools like `generate_audio` appear in the list, they were created as Agent Tool Function documents (possibly by `install.py` or `tool_registry.py` sync). If some tools are missing:

1. Run `bench --site <site> migrate` to trigger install hooks
2. Check `install.py` → `create_standard_tools()` creates the base set
3. Custom function tools need `function_path` to be valid and callable

### How to Ensure All Tools Are Available

The Agent form's tool list comes from the same `Agent Tool Function` DocType. So **the same tools available to agents are available in Call Tool**. If a tool appears on the Agent form but not in Call Tool, it's a data sync issue — the Agent Tool Function document may not exist.

---

## 7. Trigger Node / Start Node Analysis

### Current UI Structure

When clicking the first (trigger) node, the NodeSelectionModal shows:

**Main Tabs:**
- Triggers (default when mode='trigger')
- Actions ← **ISSUE: Should not appear for trigger nodes**

**Trigger Sub-Tabs:**
- Explore — Shows: Webhook, Schedule, Human Input, Data (4 options)
- AI & Agents — Shows available agents (creates app-trigger config)
- Apps — **EMPTY** (no options mapped to this tab)
- Utility — **EMPTY** (no options mapped to this tab)

### Issues & Fixes

1. **Actions tab on trigger modal**: Removed — when `mode === 'trigger'`, only trigger tab shows
2. **Empty sub-tabs**: Removed Apps and Utility tabs — they had no trigger options
3. **AI & Agents tab**: Kept — allows selecting an agent as a trigger source (maps to app-trigger config with agent info)
4. **"Human Input" trigger**: This is a trigger-level concept (start flow from human input), separate from the "Human Approval" action node

### Why Does Start Node Only Carry Triggers?

The start node represents the **entry point** of a flow. It defines:
- **What triggers the flow** (webhook call, schedule, doc event, manual)
- **What payload is passed** (webhook body, doc data, manual input)

It does NOT execute actions — it just receives the initial event and passes data to the first action node via context.

---

## 8. Schema Validation Gap

### The Problem

`flow_definition.py` line 9-16 defines:
```python
ALLOWED_NODE_TYPES = {
    "trigger.webhook",
    "agent.run",
    "tool.call",
    "router.llm",
    "human.approval",
    "end",
}
```

But `flow_engine.py` supports (and the frontend can create):
- `condition`
- `http_request`
- `transform`
- `loop`

**Result**: Flows using these 4 node types would **fail validation on save**.

### Fix Applied

Updated `ALLOWED_NODE_TYPES` to include all supported types:
```python
ALLOWED_NODE_TYPES = {
    "trigger.webhook",
    "agent.run",
    "tool.call",
    "router.llm",
    "human.approval",
    "condition",
    "http_request",
    "transform",
    "loop",
    "end",
}
```

---

## 9. Fixes Applied

### Fix 1: ALLOWED_NODE_TYPES (Critical)
**File**: `huf/huf/doctype/flow_definition/flow_definition.py`
- Added `condition`, `http_request`, `transform`, `loop` to ALLOWED_NODE_TYPES

### Fix 2: NodeSelectionModal Trigger-Only Mode
**File**: `frontend/src/components/modals/NodeSelectionModal.tsx`
- When `mode === 'trigger'`, only Triggers tab shown (Actions tab hidden)
- Removed empty Apps and Utility sub-tabs
- Kept Explore (4 triggers) and AI & Agents (agent list)

### Fix 3: Human Approval — Role Auto-Suggest
**File**: `frontend/src/components/RightSidebar.tsx`
- Replaced plain text input with Combobox that fetches Frappe roles
- Added API call to load roles when human-in-loop node is selected
- Added Approval Type selector (role vs user)
- Added Approver Users field (shown when type = "user")
- Added Context Summary textarea
- Added Reference DocType and Reference Name fields

### Fix 4: Human Approval Backend — Context Fields
**File**: `huf/ai/flow_engine.py`
- Added `context_summary`, `reference_doctype`, `reference_name` to waiting data

### Fix 5: Tool-call Config Serialization
**File**: `frontend/src/components/modals/NodeSelectionModal.tsx`
- Ensured tool-call initial config uses `output: { save_result_to_context: '' }` structure matching what RightSidebar expects

---

## 10. Remaining Work / Recommendations

### High Priority

| Item | Description |
|------|-------------|
| **Approval Notifications** | Implement Frappe Notification for Waiting Approval status. Use `frappe.sendmail()` or Notification DocType to alert approvers. |
| **Approval Page** | Create a dedicated `/huf/approve/<flow_run_id>` page where approvers can view context, linked doc, and approve/reject. |
| **Frontend-only Actions** | Either implement backend executors for email/code/file/slack/sheets/notion, or remove them from the UI and mark as "Coming Soon". |
| **Schedule/Doc-Event Backend** | Wire schedule triggers to `agent_scheduler.py` and doc-event triggers to `agent_hooks.py` for flow execution. |

### Medium Priority

| Item | Description |
|------|-------------|
| **Agent Run conversation_mode** | Add conversation mode selector to agent-run sidebar (already in router sidebar). |
| **Condition node selector** | Replace manual node ID typing with a dropdown of available nodes for true/false branches. |
| **Loop node selector** | Same — dropdown for loop_node and done_node fields. |
| **Approval timeout** | Implement `timeout_hours` enforcement — auto-reject or escalate after timeout. |
| **Context schema preview** | Show available context keys at each node position in the flow. |

### Low Priority

| Item | Description |
|------|-------------|
| **Flow auto-save** | Currently debounced at 50ms — may need conflict resolution for multi-user editing. |
| **Edge meta for approval** | Document that approval edges need `meta.outcome: "approved"` or `"rejected"` — UI should set this automatically when connecting from approval node. |
| **Flow versioning UI** | Show version history and allow rollback. |

---

*This document will be updated as fixes are applied and tested.*
