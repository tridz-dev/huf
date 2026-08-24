import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

// ─── Types ───────────────────────────────────────────────────────────

/** Flow Definition as returned by the backend list */
export interface FlowDefinitionListItem {
    name: string;
    flow_id: string;
    flow_name: string;
    status: 'Draft' | 'Active' | 'Archived';
    version: number;
    schema_version: number;
    modified: string;
}

/** Full flow definition including the graph JSON */
export interface FlowDefinitionDoc {
    flow_id: string;
    flow_name: string;
    status: 'Draft' | 'Active' | 'Archived';
    version: number;
    /** Graph-IR schema_version, e.g. "1.0.0" -- a string, not an int (huf/ai/graph/graph_ir.schema.json). */
    schema_version: string;
    definition_json: BackendFlowGraph;
}

/**
 * The graph JSON stored in definition_json -- the Flow profile of the shared graph-IR
 * (huf/ai/graph/graph_ir.schema.json `$defs/FlowGraph`, see Tracks/safwan-erooth.DeterministicAgent/spec/graph-ir.md).
 *
 * There is no top-level `edges` array any more: each node carries its own successor
 * pointer (`next`) and error route (`on_error`); self-routing node types (condition,
 * router.llm, human.approval) carry their branch targets in their own `config`. There
 * is also no `id`/`version`/`settings`/`metadata` -- the schema is `additionalProperties:
 * false`, so none of those keys may appear. `flow_id`/`flow_name`/`version` live on the
 * Flow Definition doctype record itself, not inside the graph.
 */
export interface BackendFlowGraph {
    schema_version: '1.0.0';
    profile: 'flow';
    /** sha256 hex digest of the graph's canonical form (graph-ir.md section 7). */
    fingerprint: string;
    /** One node id, or (when the graph starts from one or more triggers) an array of trigger node ids. */
    entry: string | string[];
    nodes: BackendNode[];
    contract: BackendContract;
}

export type BackendNodeType =
    | 'trigger.webhook' | 'trigger.schedule' | 'trigger.doc-event'
    | 'agent.run' | 'tool.call' | 'router.llm' | 'human.approval'
    | 'condition' | 'http_request' | 'transform' | 'loop' | 'output';

export interface BackendNode {
    id: string;
    type: BackendNodeType;
    config: Record<string, unknown>;
    /** Default successor node id. Absent/null means terminal for its chain. */
    next?: string | null;
    /** Node to route to if this node raises. Absent/null means an error here fails the run. */
    on_error?: string | null;
    /** Frontend-only: stored for visual layout, ignored by engine */
    _position?: { x: number; y: number };
    /** Frontend-only: visual label */
    _label?: string;
    /** Frontend-only: icon name */
    _icon?: string;
}

export interface BackendDocPermission {
    doctype: string;
    fields?: string[];
}

export interface BackendPermissionEnvelope {
    read: BackendDocPermission[];
    write: BackendDocPermission[];
    http: 'none' | string[];
    code: 'none' | string[];
}

export interface BackendResourceLimits {
    max_nodes: number;
    max_rows: number;
    max_output_bytes: number;
    max_parallel_calls: number;
    max_foreach_iterations: number;
    max_external_calls: number;
    max_writes: number;
    max_wall_time_ms: number;
    fail_closed: true;
}

/** graph-ir.md's Contract: everything a graph declares about its own inputs/outputs
 * and blast radius, required on every graph (Flow and Procedure alike). */
export interface BackendContract {
    input_schema: Record<string, unknown>;
    output_schema: Record<string, unknown>;
    applies_when: string[];
    permission_envelope: BackendPermissionEnvelope;
    limits: BackendResourceLimits;
}

/** @deprecated Pre-migration edge shape. No longer part of BackendFlowGraph -- kept only
 * so the frontend's own React Flow edge model (FlowEdgeData) can still describe an
 * edge's routing intent (always/on_success/on_failure/expression) before it gets
 * folded into a node's `next`/`on_error`/self-routing config at serialize time. */
export interface BackendEdge {
    id: string;
    from: string;
    to: string;
    type: 'always' | 'on_success' | 'on_failure' | 'expression';
    priority?: number;
    condition?: string;
    meta?: Record<string, unknown>;
}

/** @deprecated Flow-level run settings no longer fit in the graph-IR document
 * (additionalProperties: false leaves no room for a `settings` key). Kept as the type
 * of `Flow.settings`, a frontend/local-only field the engine now defaults instead
 * (huf.ai.flow_engine.DEFAULT_MAX_HOPS, etc.) -- see flowSerializer.ts. */
export interface BackendSettings {
    mode?: 'normal' | 'agentic';
    max_hops?: number;
    orchestrator_agent?: string;
    orchestrator_call_policy?: string;
    conversation_mode?: 'flow_shared' | 'per_node';
}

/** Flow Run summary (from list endpoint) */
export interface FlowRunSummary {
    name: string;
    flow_id: string;
    flow_version: number;
    mode: string;
    status: 'Queued' | 'Running' | 'Waiting Approval' | 'Waiting User' | 'Success' | 'Failed';
    current_node_id: string;
    hop_count: number;
    trigger_type: string;
    started_at: string | null;
    completed_at: string | null;
}

/** Flow Run detail (from get endpoint) */
export interface FlowRunDetail {
    flow_run_id: string;
    flow_id: string;
    flow_version: number;
    mode: string;
    status: string;
    current_node_id: string;
    hop_count: number;
    context_json: Record<string, unknown>;
    waiting: Record<string, unknown>;
    last_error: string | null;
    last_agent_run: string | null;
    started_at: string | null;
    completed_at: string | null;
}

/** Pending human approval (from get_pending_approvals endpoint) */
export interface PendingApproval {
    flow_run_id: string;
    flow_id: string;
    current_node_id: string;
    title: string;
    instructions: string;
    approval_type: string;
    started_at: string | null;
    waiting_since: string | null;
    view_link: string;
}

// ─── Flow Definition APIs ────────────────────────────────────────────

const FLOW_LIST_FIELDS = [
    'name', 'flow_id', 'flow_name', 'status',
    'version', 'schema_version', 'modified',
];

/** List all flow definitions */
export async function getFlowDefinitions(): Promise<FlowDefinitionListItem[]> {
    try {
        const flows = await db.getDocList(doctype['Flow Definition'], {
            fields: FLOW_LIST_FIELDS,
            orderBy: { field: 'modified', order: 'desc' },
            limit: 100,
        });
        return flows as FlowDefinitionListItem[];
    } catch (error) {
        handleFrappeError(error, 'Error fetching flow definitions');
    }
}

/** Get a single flow definition with parsed graph JSON */
export async function getFlowDefinition(flowId: string): Promise<FlowDefinitionDoc> {
    try {
        const result = await call.get('huf.ai.flow_api.get_flow_definition', {
            flow_id: flowId,
        });
        return result.message as FlowDefinitionDoc;
    } catch (error) {
        handleFrappeError(error, `Error fetching flow ${flowId}`);
    }
}

/** Save (create or update) a flow definition */
export async function saveFlowDefinition(
    flowId: string,
    definitionJson: BackendFlowGraph
): Promise<{ flow_id: string; version: number }> {
    try {
        const result = await call.post('huf.ai.flow_api.save_flow_definition', {
            flow_id: flowId,
            definition_json: JSON.stringify(definitionJson),
        });
        return result.message as { flow_id: string; version: number };
    } catch (error) {
        handleFrappeError(error, `Error saving flow ${flowId}`);
    }
}

/** Delete a flow definition */
export async function deleteFlowDefinition(flowId: string): Promise<void> {
    try {
        await db.deleteDoc(doctype['Flow Definition'], flowId);
    } catch (error) {
        handleFrappeError(error, `Error deleting flow ${flowId}`);
    }
}

/** Update flow name or status (DocType field update) */
export async function updateFlowDefinitionFields(
    flowId: string,
    fields: { flow_name?: string; status?: string }
): Promise<void> {
    try {
        await db.updateDoc(doctype['Flow Definition'], flowId, fields);
    } catch (error) {
        handleFrappeError(error, `Error updating flow ${flowId}`);
    }
}

/** Outcome of the "create a procedure from this flow on save" checkbox, as recorded on
 * the Flow Definition doc. `get_flow_definition`/`save_flow_definition` don't expose
 * these fields, so they're read straight off the doctype via the SDK. */
export interface FlowConversionStatus {
    auto_convert_to_procedure: boolean;
    /** Human-readable outcome of the last conversion attempt (success or refusal reason). */
    conversion_note: string | null;
    /** Name of the Draft Agent Procedure created/refreshed from this flow, if any. */
    converted_procedure: string | null;
}

/** Fetch the current auto-convert checkbox value and the outcome of the last conversion
 * attempt (set asynchronously by the backend after save -- see flow_definition.py's
 * _maybe_convert_to_procedure). */
export async function getFlowConversionStatus(flowId: string): Promise<FlowConversionStatus> {
    try {
        const doc = await db.getDoc(doctype['Flow Definition'], flowId);
        return {
            auto_convert_to_procedure: Boolean(doc.auto_convert_to_procedure),
            conversion_note: (doc.conversion_note as string) || null,
            converted_procedure: (doc.converted_procedure as string) || null,
        };
    } catch (error) {
        handleFrappeError(error, `Error fetching conversion status for flow ${flowId}`);
    }
}

/** Toggle the "create a procedure from this flow on save" checkbox */
export async function updateFlowAutoConvert(flowId: string, autoConvert: boolean): Promise<void> {
    try {
        await db.updateDoc(doctype['Flow Definition'], flowId, {
            auto_convert_to_procedure: autoConvert ? 1 : 0,
        });
    } catch (error) {
        handleFrappeError(error, `Error updating flow ${flowId}`);
    }
}

/** Get node schemas from backend for dynamic UI construction */
export async function getNodeSchemas(): Promise<Record<string, unknown>> {
    try {
        const result = await call.get('huf.ai.flow_api.get_node_schemas');
        return result.message as Record<string, unknown>;
    } catch (error) {
        handleFrappeError(error, 'Error fetching node schemas');
    }
}

// ─── Flow Run APIs ───────────────────────────────────────────────────

/** Run a flow (start new execution) */
export async function runFlow(
    flowId: string,
    payload?: Record<string, unknown>,
    mode?: string
): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow_api.run_flow', {
            flow_id: flowId,
            payload: payload ? JSON.stringify(payload) : undefined,
            mode,
        });
        return result.message as { flow_run_id: string; status: string; current_node_id: string };
    } catch (error) {
        handleFrappeError(error, `Error running flow ${flowId}`);
    }
}

/** Get flow run detail */
export async function getFlowRun(flowRunId: string): Promise<FlowRunDetail> {
    try {
        const result = await call.get('huf.ai.flow_api.get_flow_run', {
            flow_run_id: flowRunId,
        });
        return result.message as FlowRunDetail;
    } catch (error) {
        handleFrappeError(error, `Error fetching flow run ${flowRunId}`);
    }
}

/** List flow runs with optional filters */
export async function listFlowRuns(
    flowId?: string,
    status?: string,
    limit?: number
): Promise<FlowRunSummary[]> {
    try {
        const result = await call.get('huf.ai.flow_api.list_flow_runs', {
            flow_id: flowId,
            status,
            limit: limit || 20,
        });
        return result.message as FlowRunSummary[];
    } catch (error) {
        handleFrappeError(error, 'Error listing flow runs');
    }
}

/** Approve a flow run waiting for approval */
export async function approveFlowRun(
    flowRunId: string,
    comment?: string
): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow_api.approve_flow_run', {
            flow_run_id: flowRunId,
            comment,
        });
        return result.message as { flow_run_id: string; status: string; current_node_id: string };
    } catch (error) {
        handleFrappeError(error, `Error approving flow run ${flowRunId}`);
    }
}

/** Reject a flow run waiting for approval */
export async function rejectFlowRun(
    flowRunId: string,
    comment?: string
): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow_api.reject_flow_run', {
            flow_run_id: flowRunId,
            comment,
        });
        return result.message as { flow_run_id: string; status: string; current_node_id: string };
    } catch (error) {
        handleFrappeError(error, `Error rejecting flow run ${flowRunId}`);
    }
}

/** Resume a flow run waiting for user input */
export async function resumeFlowRun(
    flowRunId: string,
    input?: Record<string, unknown>
): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow_api.resume_flow_run', {
            flow_run_id: flowRunId,
            input: input ? JSON.stringify(input) : undefined,
        });
        return result.message as { flow_run_id: string; status: string; current_node_id: string };
    } catch (error) {
        handleFrappeError(error, `Error resuming flow run ${flowRunId}`);
    }
}

/** List flow runs waiting for human approval */
export async function getPendingApprovals(): Promise<PendingApproval[]> {
    try {
        const result = await call.get('huf.ai.flow_api.get_pending_approvals');
        return result.message as PendingApproval[];
    } catch (error) {
        handleFrappeError(error, 'Error fetching pending approvals');
    }
}

// ─── Flow -> Procedure conversion ───────────────────────────────────────

/** Preview of converting a flow into a deterministic procedure */
export interface FlowConversionAnalysis {
    convertible: boolean;
    reason?: string;
    reads?: string[];
    writes?: string[];
    atomic_operations?: number;
    estimated_round_trip_reduction_pct?: number;
}

/** Result of actually creating the procedure from a flow */
export interface FlowConversionResult extends FlowConversionAnalysis {
    name: string;
    procedure_id: string;
    version: number;
    status: string;
    tier: string;
}

/** Read-only preview: is this flow convertible, and what would it look like? Creates nothing. */
export async function analyzeFlowConversion(flowId: string): Promise<FlowConversionAnalysis> {
    try {
        const result = await call.get('huf.ai.flow_api.analyze_flow_conversion', {
            flow_id: flowId,
        });
        return result.message as FlowConversionAnalysis;
    } catch (error) {
        handleFrappeError(error, `Error analyzing flow ${flowId} for conversion`);
    }
}

/** Convert a deterministic flow into a Draft procedure. Never activates it. */
export async function convertFlowToProcedure(flowId: string): Promise<FlowConversionResult> {
    try {
        const result = await call.post('huf.ai.flow_api.convert_flow_to_procedure', {
            flow_id: flowId,
        });
        return result.message as FlowConversionResult;
    } catch (error) {
        handleFrappeError(error, `Error converting flow ${flowId} to a procedure`);
    }
}
