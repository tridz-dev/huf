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
    schema_version: number;
    definition_json: BackendFlowGraph;
}

/** The graph JSON stored in definition_json */
export interface BackendFlowGraph {
    schema_version: number;
    id: string;
    version: number;
    entry: string;
    nodes: BackendNode[];
    edges: BackendEdge[];
    settings: BackendSettings;
    metadata: BackendMetadata;
}

export interface BackendNode {
    id: string;
    type: 'trigger.webhook' | 'trigger.schedule' | 'trigger.doc-event' | 'agent.run' | 'tool.call' | 'router.llm' | 'human.approval' | 'condition' | 'http_request' | 'transform' | 'loop' | 'end';
    config: Record<string, unknown>;
    /** Frontend-only: stored for visual layout, ignored by engine */
    _position?: { x: number; y: number };
    /** Frontend-only: visual label */
    _label?: string;
    /** Frontend-only: icon name */
    _icon?: string;
}

export interface BackendEdge {
    id: string;
    from: string;
    to: string;
    type: 'always' | 'on_success' | 'on_failure' | 'expression';
    priority?: number;
    condition?: string;
    meta?: Record<string, unknown>;
}

export interface BackendSettings {
    mode?: 'normal' | 'agentic';
    max_hops?: number;
    orchestrator_agent?: string;
    orchestrator_call_policy?: string;
    conversation_mode?: 'flow_shared' | 'per_node';
}

export interface BackendMetadata {
    name: string;
    description?: string;
    category?: string;
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
