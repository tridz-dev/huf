# Flow Architecture Gaps Analysis & Remediation

## Status: ✅ Remediated

This document tracks the gaps identified in HUF's flow architecture compared to
n8n's Node Configuration System, and the fixes applied.

---

## Gap 1: Ghost Nodes ✅ FIXED

**Problem:** UI exposed node types (code, utility-email, utility-file,
utility-date, utility-webhook) that had **no backend executors** in
`flow_engine.py`. Users could add these nodes but they would silently fail
at runtime.

**Fix:**
- **Removed** all ghost node types from `flow.types.ts`, `actions.ts`,
  `FlowCanvas.tsx`, and `NodeSelectionModal.tsx`
- **Added** 4 new fully-backed node types: `condition`, `http_request`,
  `transform`, `loop`
- Every node type shown in the UI now has a corresponding executor in
  `flow_engine.py`

---

## Gap 2: Missing Explicit IF Node ✅ FIXED

**Problem:** Conditional branching was embedded in edge-level expressions, making
it opaque compared to n8n's explicit IF node with True/False output ports.

**Fix:**
- Added `condition` node type with `_exec_condition()` backend executor
- Evaluates boolean expressions against context using `safe_eval_expression`
- Returns `true_node` or `false_node` for explicit branch routing
- Frontend config form in `RightSidebar.tsx` with expression input + branch selectors

---

## Gap 3: No Native Loop Executor ✅ FIXED

**Problem:** UI advertised a "Loop" node type, but no backend executor existed.

**Fix:**
- Added `_exec_loop_node()` executor in `flow_engine.py`
- Iterates over arrays in context with configurable item/index variables
- Supports `loop_node` (body) and `done_node` (exit) routing
- Safety limit via `max_iterations` (default: 100)
- Full sidebar config UI

---

## Gap 4: No HTTP Request Node ✅ FIXED

**Problem:** No way to call external APIs from within a flow.

**Fix:**
- Added `http_request` node type with `_exec_http_request()` executor
- Supports GET/POST/PUT/PATCH/DELETE methods
- Variable interpolation in URL, headers, and body (`{{ key }}` syntax)
- Configurable timeout and context-saving
- Frontend config with method selector, headers/body editors

---

## Gap 5: No Data Transform Node ✅ FIXED

**Problem:** No way to reshape/map data between context variables without
running a full agent.

**Fix:**
- Added `transform` node type with `_exec_transform()` executor
- Supports copy, map, and template operations
- Multiple transformations per node
- Dynamic list UI in `RightSidebar.tsx`

---

## Gap 6: Synchronous Execution / No Observability ✅ FIXED

**Problem:** The execution loop ran synchronously with no feedback to the UI
about which node was currently executing.

**Fix:**
- Added `_publish_flow_event()` helper using `frappe.publish_realtime()`
- Events emitted: `flow_node_start`, `flow_node_end`, `flow_paused`,
  `flow_completed`, `flow_failed`, `flow_error`
- Each event includes `flow_run_id`, `node_id`, `node_type`, and `status`
- Frontend `FlowNodeData.status` field updated to reflect live state

---

## Gap 7: Hardcoded UI Schemas ✅ PARTIALLY FIXED

**Problem:** Frontend forms were hardcoded per node type rather than driven
by backend schemas, making it impossible to add new node types without
frontend changes.

**Fix:**
- Added `get_node_schemas()` API endpoint in `flow_api.py`
- Returns complete schema definitions for all 10 supported node types
- Each schema includes: label, icon, category, description, has_backend flag,
  and a `config_schema` array with field definitions
- Frontend `flowApi.ts` now has `getNodeSchemas()` wrapper
- Full dynamic form rendering is a future enhancement; the schema API is
  the foundation

---

## Gap 8: Routing Opacity ✅ IMPROVED

**Problem:** `router.llm` relied on brittle string matching for outcomes.

**Fix:**
- Better error handling and event publishing for router failures
- Condition node provides a deterministic alternative to LLM routing
  for simple boolean logic
- `_execute_loop` now explicitly handles `condition` node type routing
  alongside `router.llm`

---

## Files Changed

### Backend
- `huf/ai/flow_engine.py` — 4 new executors, realtime events, context helpers
- `huf/ai/flow_api.py` — `get_node_schemas()` endpoint

### Frontend
- `frontend/src/types/flow.types.ts` — Ghost types removed, new types added
- `frontend/src/data/actions.ts` — Actions list updated
- `frontend/src/services/flowSerializer.ts` — Serialization for new types
- `frontend/src/services/flowApi.ts` — New types + `getNodeSchemas()` wrapper
- `frontend/src/components/FlowCanvas.tsx` — Icon/label maps updated
- `frontend/src/components/RightSidebar.tsx` — Config forms for 4 new types
- `frontend/src/components/modals/NodeSelectionModal.tsx` — Action configs updated
