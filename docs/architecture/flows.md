# Flows: Visual Builder and Flow Engine

HUF's Flow Engine is a graph-based workflow orchestrator that reuses existing primitives (Agent Run, Conversation, Tools) rather than introducing its own execution log, and the frontend Flow Builder is a React Flow canvas that edits and runs those graphs through the same whitelisted API surface described here. A flow graph is stored as one JSON blob per `Flow Definition` document — there are no separate Node/Edge DocTypes on either side of the system.

## Core concept

1. **Flow Definition** (`huf/huf/doctype/flow_definition/flow_definition.py:1`) stores the whole graph as JSON in `definition_json`. No separate Node/Edge doctypes exist — nodes and edges are arrays inside that JSON.
2. **Flow Run** (`huf/huf/doctype/flow_run/flow_run.py:1`) persists one execution's runtime state: status, current node, hop count, context.
3. **Agent Run as node-run log**: each node execution reuses the existing `Agent Run` DocType, extended with `flow_run`, `flow_node_id`, `flow_id`, and `run_kind` (`agent`/`tool`/`orchestrator`) fields (`huf/huf/doctype/agent_run/agent_run.json`). There is no dedicated "Flow Node Run" DocType.

Full field tables for `Flow Definition`, `Flow Run`, and the Agent Run extension fields are in `docs/reference/doctypes.generated.md` — not reproduced here.

## Backend: Flow Engine

### DocTypes

- **Flow Definition** — `flow_id`, `flow_name`, `status` (`Draft`/`Active`/`Archived`), `version` (auto-increments on every save, `huf/huf/doctype/flow_definition/flow_definition.py:31`), `schema_version`, `definition_json`, `is_system`, `updated_by`, `updated_at`.
- **Flow Run** — `flow_definition`, `flow_id`, `flow_version` (pinned at start), `mode` (`Normal`/`Agentic`), `status` (`Queued`/`Running`/`Waiting Approval`/`Waiting User`/`Success`/`Failed`), `current_node_id`, `hop_count`, `max_hops`, `context_json`, `trigger_type`, `trigger_payload`, `waiting`, `last_error`, `last_agent_run`, `conversation`, plus `started_at`/`completed_at` timing fields.

### Definition JSON validation

`FlowDefinition.validate()` (`huf/huf/doctype/flow_definition/flow_definition.py:23`) enforces, on every save:

- Top-level keys `schema_version`, `id`, `version`, `entry`, `nodes`, `edges`, `settings`, `metadata` must all be present.
- `definition_json.id` must equal `flow_id`.
- Node `id`s must be unique; every node needs a `type` from the allowed set below.
- `entry` must reference an existing node.
- Every edge's `from`/`to` must reference existing node ids; edge `type` must be one of the allowed edge types; `expression` edges must carry a non-empty `condition`.

The allowed node/edge type sets live as `ALLOWED_NODE_TYPES` / `ALLOWED_EDGE_TYPES` constants at the top of that file — they are the actual source of truth, not the tables below (which mirror them as of this writing).

### Node types (v0.2)

| Type | Executor | Description |
|:-----|:---------|:------------|
| `trigger.webhook` | `_exec_trigger_webhook` | Passthrough entry point for webhook-started runs |
| `trigger.schedule` | `_exec_trigger_schedule` | Passthrough entry point for scheduled runs |
| `trigger.doc-event` | `_exec_trigger_doc_event` | Passthrough entry point for Frappe doc-event runs |
| `agent.run` | `_exec_agent_run` | Runs a Huf agent via `run_agent_sync` |
| `tool.call` | `_exec_tool_call` | Deterministic tool execution (no LLM), with variable interpolation |
| `router.llm` | `_exec_router_llm` | LLM-based routing among candidate outgoing edges |
| `human.approval` | `_exec_human_approval` | Pauses the run for a human approve/reject decision |
| `http_request` | `_exec_http_request` | Executes a custom HTTP request |
| `condition` | `_exec_condition` | Evaluates a boolean expression to pick a branch |
| `transform` | `_exec_transform` | Transforms context data via copy/map/template |
| `loop` | `_exec_loop_node` | Iterates over an array in context |
| `end` | `_exec_end` | Marks the run successful |

Dispatch table: `huf/ai/flow_engine.py:407-418`. This list is unchanged from the older AGENTS.md write-up and matches the code exactly — the node type names and executor dispatch are stable.

### Edge types

| Type | Description |
|:-----|:------------|
| `always` | Always follow this edge |
| `on_success` | Follow if the previous node succeeded |
| `on_failure` | Follow if the previous node failed |
| `expression` | Evaluate `condition` against flow context (AST-restricted, see Security) |

Edges are sorted by `priority` (descending); the first match wins (`huf/ai/flow_engine.py:1200-1219`).

**Approval routing**: on `human.approval`, the engine follows the edge whose `meta.outcome` matches the decision (`approved`/`rejected`). An approval falls back to the success path when no matching edge exists; a rejection with no explicit `meta.outcome=rejected` edge fails the run instead of silently taking the success path.

**Loop routing**: `loop` nodes route to their body or done node via `next_node_id` returned by the loop executor (`huf/ai/flow_engine.py:1134` uses `max_iterations`, default 100 as a safety cap); without a done node, the flow completes gracefully once the loop finishes.

### Execution modes

- **Normal**: the engine follows edges deterministically; agents run only when an `agent.run` node is hit.
- **Agentic**: an orchestrator agent (`huf/ai/flow_orchestrator.py:1`) is invoked after each node to decide the next step, given completed results, context, and the candidate outgoing edges, and must return a strict JSON decision.

`router.llm` nodes use a related but separate prompt path: `build_router_prompt()` (`huf/ai/flow_orchestrator.py:13`) forces the router agent to respond with only a JSON object of the shape `{"next_node_id": "...", "context_patch": {}, "message": "...", "reason": "..."}`, optionally injecting the current flow context, the last node's result, and the list of candidate destination node IDs — each toggle controlled by `node_config.inject.include_context` / `include_last_node_result` / `include_candidates`.

### Realtime execution events

The engine publishes best-effort Frappe Realtime events via `_publish_flow_event()` (`huf/ai/flow_engine.py:1467`) so the frontend canvas can show live per-node status without polling: `flow_node_start`, `flow_node_end`, `flow_paused`, `flow_completed`, `flow_failed`, `flow_error`. Each message carries `flow_run_id` and `flow_id`. Publish failures are swallowed (`except Exception: pass`) so a realtime hiccup never breaks execution — this is why `FlowContext.tsx` also falls back to fetching flow/run state directly rather than depending on these events alone.

### Core modules

| Module | Purpose |
|:-------|:--------|
| `huf/ai/flow_engine.py` (1521 lines) | Core engine: load, validate, execute nodes, evaluate edges |
| `huf/ai/flow_api.py` (1188 lines) | Whitelisted API endpoints for the UI, triggers, scheduling, and agent tools |
| `huf/ai/flow_eval.py` (225 lines) | AST-based restricted expression evaluator for `expression` edges and `condition` nodes |
| `huf/ai/flow_tool_executor.py` (219 lines) | Deterministic tool execution reusing `sdk_tools` handlers |
| `huf/ai/flow_orchestrator.py` (287 lines) | Prompt construction and JSON parsing for the Agentic-mode orchestrator |
| `huf/ai/flow_tools.py` (91 lines) | Tool definitions registered via the `huf_tools` hook |

### Whitelisted APIs

`huf/ai/flow_api.py` exposes considerably more surface than a graph CRUD + run API — the old AGENTS.md list only covered nine of these:

| Method | Purpose |
|:-------|:--------|
| `get_flow_definition` | Get a flow definition |
| `save_flow_definition` | Save/update a flow definition |
| `run_flow` | Start a flow run |
| `get_flow_run` | Get flow run status |
| `list_flow_runs` | List flow runs |
| `resume_flow_run` | Resume a waiting flow |
| `approve_flow_run` | Approve a flow |
| `reject_flow_run` | Reject a flow |
| `flow_webhook` (`allow_guest=True`) | Webhook trigger, keyed by `webhook_key` |
| `flow_webhook_clean` (`allow_guest=True`) | Alternate webhook trigger route |
| `schedule_flow` | Register a cron schedule for a flow |
| `unschedule_flow` | Remove a flow's schedule |
| `get_flow_schedule` | Read a flow's current schedule |
| `execute_scheduled_flow` | Scheduler entry point that starts a scheduled run |
| `get_node_schemas` | Returns node config schemas (used by the frontend node selection UI) |
| `handle_run_flow`, `handle_get_flow_run`, `handle_resume_flow_run`, `handle_approve_flow_run` | Thin wrappers around the above, used as the actual `function_path` targets for agent tools (see below) |

`get_pending_approvals` exists in the file but is commented out (`huf/ai/flow_api.py:1111-1112`) — not currently live.

### Agent tools

Registered via the `huf_tools` hook in `huf/ai/flow_tools.py:1`, so agents can interact with flows as tool calls:

- `run_flow` → `huf.ai.flow_api.handle_run_flow`
- `get_flow_run` → `huf.ai.flow_api.handle_get_flow_run`
- `resume_flow_run` → `huf.ai.flow_api.handle_resume_flow_run`
- `approve_flow_run` → `huf.ai.flow_api.handle_approve_flow_run` (takes a `decision` of `approved` or `rejected`, so this one tool covers both approve and reject)

Note these tools call the `handle_*` wrapper functions, not the REST-facing `run_flow`/`get_flow_run`/etc. functions directly — the wrappers add tool-call-appropriate argument handling (`**kwargs`, string/dict coercion) on top of the same underlying logic.

### Security

- **Expression edges**: `flow_eval.py` uses an AST-based restricted evaluator — no imports, no function calls, no attribute access beyond simple key lookups, expressions capped at `MAX_EXPRESSION_LENGTH = 500` chars (`huf/ai/flow_eval.py:36`).
- **Human approval**: user/role verification before approve/reject; `approval_type` values `user` and `users` are treated as synonyms (`huf/ai/flow_engine.py:837`, `:1420`).
- **Permissions**: `Huf Manager` has `create` on `Flow Run`; agent-tool handlers (`run_flow`, `get_flow_run`, `resume_flow_run`, `approve_flow_run`) enforce the same permission checks and approver-identity verification as the REST endpoints.
- **Hop limit**: `DEFAULT_MAX_HOPS = 100` (`huf/ai/flow_engine.py:34`) guards against infinite loops; a run that exceeds `max_hops` is failed with a `flow_error` event rather than looping forever.

## Frontend: Flow Builder

The frontend flow builder is a React Flow (`@xyflow/react` / `reactflow`) canvas under `frontend/src/`. **This is the part of the old AGENTS.md write-up that was most stale**: it described `flowService.ts` as an in-memory, Map-based mock service. That is no longer true — `flowService.ts` now talks to the real backend.

### Core components

- **`frontend/src/services/flowApi.ts:1`** — the actual Frappe SDK boundary. Wraps `call`/`db` from `@/lib/frappe-sdk` around the backend whitelisted methods: `getFlowDefinitions`, `getFlowDefinition`, `saveFlowDefinition`, `deleteFlowDefinition`, `updateFlowDefinitionFields`, `getNodeSchemas`, `runFlow`, `getFlowRun`, `listFlowRuns`, `approveFlowRun`, `rejectFlowRun`, `resumeFlowRun`, `getPendingApprovals`.
- **`frontend/src/services/flowSerializer.ts`** — converts between the backend's `BackendFlowGraph` JSON shape (`{schema_version, id, version, entry, nodes, edges, settings, metadata}`, with node types like `agent.run`/`trigger.webhook`) and the frontend's React Flow `Flow`/`FlowNode`/`FlowEdge` shape.
- **`frontend/src/services/flowService.ts:1`** — per its own header comment: *"Previously used an in-memory Map (mock). Now calls the backend via flowApi.ts and uses flowSerializer.ts for JSON conversion."* It keeps a local `flowCache: Map<string, Flow>` purely as a read cache between backend round-trips, not as the source of truth. Public methods (`getAllFlows`, `getFlow`, `createFlow`, `saveFlow`, `updateFlow`, `deleteFlow`, `runFlow`, `listFlowRuns`, `approveFlowRun`, `rejectFlowRun`, `resumeFlowRun`) are now `async` and hit the backend.
- **`frontend/src/contexts/FlowContext.tsx:1`** — React context wrapping `flowService`. Tracks `flows`, `activeFlowId`, `activeFlow`, `selectedNodeId`, `selectedEdgeId`, `loading`/`error`, and a `saveState` (`'saved' | 'saving' | 'unsaved' | 'error'`) not present in the old write-up. Listens for `CustomEvent`s (node-start/node-end) to update live per-node execution status on the canvas.
- **`frontend/src/components/FlowCanvas.tsx:1`** — the React Flow canvas: `Background` (dotted), `Controls`, `MiniMap`, drag-and-drop node placement, `onConnect` for edge creation.

### Node types shown in the UI

The frontend's `NodeType` union (`frontend/src/types/flow.types.ts:6-9`) is just `'trigger' | 'action' | 'end'` — three visual categories, not the twelve-entry backend list. Within the `action` category, `ActionType` (`frontend/src/types/flow.types.ts:43-51`) enumerates the configs that map 1:1 onto backend executors:

| Frontend `ActionType` | Backend node type |
|:-----|:-----|
| `agent-run` | `agent.run` |
| `tool-call` | `tool.call` |
| `router` | `router.llm` |
| `human.approval` | `human.approval` |
| `condition` | `condition` |
| `http-request` | `http_request` |
| `transform` | `transform` |
| `loop` | `loop` |

The type file's own comment is explicit about what changed: *"ActionType — only types with real backend executors. Ghost types (utility-email, utility-file, utility-date, etc.) have been removed."* The old AGENTS.md's "Utility Nodes" section (Email, File, Date, Webhook, HTTP utilities) and "Code Action" (custom JS/Python/TS execution) describe exactly those ghost types — **none of them exist in the current frontend or have a backend executor**. The only HTTP-like utility that survived is `http-request`, which maps to the real `http_request` backend node.

Trigger configs (`frontend/src/types/flow.types.ts:53-89`) cover `webhook`, `schedule`, `doc-event`, and `app-trigger` (Gmail/Calendar/Slack/Notion/HubSpot/Sheets integrations). Of these, only `webhook`, `schedule`, and `doc-event` have backend node types (`trigger.webhook`, `trigger.schedule`, `trigger.doc-event`); `app-trigger` is frontend-only UI scaffolding with no corresponding entry in `ALLOWED_NODE_TYPES` — selecting it in the UI does not produce a node the engine can execute today.

### Node/edge data shape

```typescript
// frontend/src/types/flow.types.ts
interface FlowNodeData {
  label: string;
  nodeType: NodeType;            // 'trigger' | 'action' | 'end'
  description?: string;
  icon?: string;
  configured: boolean;
  triggerConfig?: TriggerConfig;
  actionConfig?: ActionConfig;
  status?: 'idle' | 'running' | 'success' | 'error' | 'waiting'; // live, via realtime events
}

interface FlowEdgeData {
  edgeType?: 'always' | 'on_success' | 'on_failure' | 'expression';
  priority?: number;
  condition?: string;
  meta?: Record<string, unknown>;
}
```

`FlowNode`/`FlowEdge` are React Flow's own `Node<FlowNodeData>`/`Edge` types (`reactflow` package), not a custom graph representation.

### UI components

- **Node renderers**: `frontend/src/components/nodes/TriggerNode.tsx`, `ActionNode.tsx`, `EndNode.tsx`, plus shared `nodeStyles.ts`. (The old doc's file tree also listed these three — that part held up.)
- **Modals**: `frontend/src/components/modals/NodeSelectionModal.tsx` (pick a trigger/action type and fill its config — this is where the `ActionConfig` variants above get built), `ActionSelectionModal.tsx`, `TriggerConfigModal.tsx`, and `FlowSettingsModal.tsx` (not present in the old write-up — configures run mode / max hops at the flow-settings level).
- **Pages**: `frontend/src/pages/FlowCanvasPage.tsx` and `FlowCanvasPageWrapper.tsx` (route `/flows/:flowId`), `FlowListPage` (route `/flows`).

### Flow of a save

1. User edits nodes/edges on `FlowCanvas`, which updates `FlowContext` state.
2. `FlowContext` calls `flowService.updateFlow`/`saveFlow`, which runs `serializeFlow()` to produce a `BackendFlowGraph` and calls `flowApi.saveFlowDefinition`.
3. `flowApi.saveFlowDefinition` posts to `huf.ai.flow_api.save_flow_definition`, which persists `definition_json` on the `Flow Definition` doc and re-runs the validation described above.

## See also

`docs/reference/doctypes.generated.md` for the full `Flow Definition`, `Flow Run`, and `Agent Run` field schemas.
