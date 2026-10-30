import { db, call } from '@/lib/frappe-sdk';
import type { RunStepMeta, RunStoryFields } from './flow/flowRunStoryTypes';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

// ─── Types ───────────────────────────────────────────────────────────

/** Flow Definition as returned by the backend list */
export interface FlowDefinitionListItem {
    name: string;
    flow_id: string;
    flow_name: string;
    description?: string;
    category?: string;
    status: 'Draft' | 'Active' | 'Archived';
    version: number;
    schema_version: number;
    modified: string;
}

/** Full flow definition including the graph JSON */
export interface FlowDefinitionDoc {
    flow_id: string;
    flow_name: string;
    description?: string;
    category?: string;
    status: 'Draft' | 'Active' | 'Archived';
    version: number;
    /** Graph-IR schema_version, e.g. "1.0.0" -- a string, not an int (huf/ai/graph/graph_ir.schema.json). */
    schema_version: string;
    definition_json: BackendFlowGraph;
}

/**
 * The graph JSON stored in definition_json -- the Flow profile of the shared graph-IR
 * (huf/ai/graph/graph_ir.schema.json `$defs/FlowGraph`, see the DeterministicAgent workspace track).
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
    | 'trigger.webhook' | 'trigger.schedule' | 'trigger.doc-event' | 'trigger.unset'
    | 'agent.run' | 'tool.call' | 'router.llm' | 'router.decision' | 'human.approval'
    | 'condition' | 'transform' | 'foreach' | 'validate' | 'output'
    | 'state.get' | 'state.set' | 'state.delete' | 'doc.create' | 'code.run';

export interface BackendNode {
    id: string;
    type: BackendNodeType;
    config: Record<string, unknown>;
    /** Default successor node id. Absent/null means terminal for its chain. */
    next?: string | null;
    /** Node to route to if this node raises. Absent/null means an error here fails the run. */
    on_error?: string | null;
    /** Node-level UI extras (NodeCommon permits extra keys; engine ignores them, reads only `_label` for run logs). */
    _position?: { x: number; y: number };
    /** Frontend-only: visual label */
    _label?: string;
    /** Frontend-only: icon name */
    _icon?: string;
    /** Turned off: the engine skips the step and carries on with `next`. */
    _disabled?: boolean;
    /** The author's note about the step. Never read by the engine. */
    _notes?: string;
    /** A saved example of the data this step receives (webhook trigger): <= 8 KB, secrets hidden, only editors get it back. */
    _sample?: Record<string, unknown>;
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

/** Flow Run summary (from list endpoint) */
export interface FlowRunSummary extends RunStoryFields {
        input_hint?: string;
    name: string;
    flow_id: string;
    flow_version: number;
    mode: string;
    run_mode?: 'Real' | 'Test';
    status: 'Queued' | 'Running' | 'Waiting Approval' | 'Waiting User' | 'Waiting Code' | 'Success' | 'Failed';
    current_node_id: string;
    hop_count: number;
    trigger_type: string;
    /** Display name of the flow (flow_id when the definition is gone). */
    flow_name: string;
    /** Queued/Running and unchanged for a long time: the worker is probably gone. */
    stale: boolean;
    can_mark_failed: boolean;
    /** UTC ISO strings. */
    started_at: string | null;
    completed_at: string | null;
}

/** Flow Run detail (from get endpoint) */
export interface FlowRunDetail extends RunStoryFields {
    step_meta?: Record<string, RunStepMeta>;
    /** UTC ISO string: the last time the run changed (how long a stuck run has been stuck). */
    modified_at?: string | null;
    flow_run_id: string;
    flow_id: string;
    flow_name: string;
    flow_version: number;
    mode: string;
    run_mode?: 'Real' | 'Test';
    status: string;
    trigger_type: string;
    current_node_id: string;
    hop_count: number;
    context_json: Record<string, unknown>;
    waiting: Record<string, unknown>;
    /** Step titles by node id, from the flow's saved definition. */
    node_labels: Record<string, string>;
    /** Document event that started a Data trigger run (e.g. on_submit); null for other triggers. */
    trigger_event?: string | null;
    last_error: string | null;
    last_agent_run: string | null;
    /** UTC ISO strings. */
    started_at: string | null;
    completed_at: string | null;
    stale: boolean;
    can_mark_failed: boolean;
    stale_after_minutes: number;
    /** The signed-in person may approve or reject this run (only meaningful while it waits for approval). */
    can_decide?: boolean;
    /** Why not, when they may not. */
    cannot_decide_reason?: string | null;
}

/** Pending human approval (from get_pending_approvals endpoint) */
export interface PendingApproval {
    flow_run_id: string;
    flow_id: string;
    flow_name?: string;
    current_node_id: string;
    title: string;
    message?: string;
    instructions: string;
    approval_type: string;
    started_at: string | null;
    waiting_since: string | null;
    view_link: string;
}

// ─── Flow Definition APIs ────────────────────────────────────────────

const FLOW_LIST_FIELDS = [
    'name', 'flow_id', 'flow_name', 'description', 'category', 'status',
    'version', 'schema_version', 'modified',
];

/** What the Flows list may ask the server to narrow down by, so older flows stay reachable when there are many. */
export interface FlowListQuery {
    search?: string;
    /** Backend status: Draft, Active or Archived. */
    status?: string;
    /** Category name, matched without regard to capitals. */
    category?: string;
}

/** The most flows the list loads at once. */
export const FLOW_LIST_LIMIT = 100;

/** List flow definitions, newest change first, at most FLOW_LIST_LIMIT. */
export async function getFlowDefinitions(query: FlowListQuery = {}): Promise<FlowDefinitionListItem[]> {
    try {
        const filters: Array<[string, '=' | 'like', string]> = [];
        if (query.search?.trim()) filters.push(['flow_name', 'like', `%${query.search.trim()}%`]);
        if (query.status) filters.push(['status', '=', query.status]);
        if (query.category) filters.push(['category', 'like', query.category]);
        const flows = await db.getDocList(doctype['Flow Definition'], {
            fields: FLOW_LIST_FIELDS,
            filters,
            orderBy: { field: 'modified', order: 'desc' },
            limit: FLOW_LIST_LIMIT,
        });
        return flows as FlowDefinitionListItem[];
    } catch (error) {
        handleFrappeError(error, 'Error fetching flow definitions');
    }
}

/** Get a single flow definition with parsed graph JSON */
export async function getFlowDefinition(flowId: string): Promise<FlowDefinitionDoc> {
    try {
        const result = await call.get('huf.ai.flow.api.get_flow_definition', {
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
        const result = await call.post('huf.ai.flow.api.save_flow_definition', {
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
    fields: { flow_name?: string; description?: string; category?: string; status?: string }
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
        const result = await call.get('huf.ai.flow.api.get_node_schemas');
        return result.message as Record<string, unknown>;
    } catch (error) {
        handleFrappeError(error, 'Error fetching node schemas');
    }
}

/** Roles that can be chosen as approvers (Huf roles first; no All/Guest/Administrator or desk-only roles). */
export async function getApproverRoles(): Promise<Array<{ name: string; group: 'Huf' | 'Other' }>> {
    try {
        const result = await call.get('huf.ai.flow.api.get_approver_roles');
        return (result.message as Array<{ name: string; group: 'Huf' | 'Other' }>) ?? [];
    } catch (error) {
        handleFrappeError(error, 'Error fetching approver roles');
    }
}

// ─── Flow Run APIs ───────────────────────────────────────────────────

/** Whether a document type can be submitted (and cancelled): only then do those Data trigger events exist. */
export async function getTriggerDoctypeInfo(doctype: string): Promise<{ doctype: string; is_submittable: boolean }> {
    try {
        const result = await call.post('huf.ai.flow.api.get_trigger_doctype_info', { doctype });
        return result.message as { doctype: string; is_submittable: boolean };
    } catch (error) {
        handleFrappeError(error, `Error loading document type ${doctype}`);
    }
}

/** Publish a flow (status Active): its triggers start firing. */
export async function publishFlow(flowId: string): Promise<{ flow_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.api.publish_flow', { flow_id: flowId });
        return result.message as { flow_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error publishing flow ${flowId}`);
    }
}

/** Take a published flow back to Draft: webhook calls are refused and schedule / document triggers stop firing. */
export async function unpublishFlow(flowId: string): Promise<{ flow_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.api.unpublish_flow', { flow_id: flowId });
        return result.message as { flow_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error unpublishing flow ${flowId}`);
    }
}

/** Run a flow (start new execution) */
export async function runFlow(flowId: string, payload?: Record<string, unknown>, mode: 'test' | 'real' = 'real'): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow.api.run_flow', {
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
        const result = await call.get('huf.ai.flow.api.get_flow_run', {
            flow_run_id: flowRunId,
        });
        return result.message as FlowRunDetail;
    } catch (error) {
        handleFrappeError(error, `Error fetching flow run ${flowRunId}`);
    }
}

/** List flow runs with optional filters */
export async function listFlowRuns(flowId?: string, status?: string, limit?: number, runMode?: 'test' | 'real'): Promise<FlowRunSummary[]> {
    try {
        const result = await call.get('huf.ai.flow.api.list_flow_runs', {
            flow_id: flowId,
            status,
            limit: limit || 20,
            run_mode: runMode,
        });
        return result.message as FlowRunSummary[];
    } catch (error) {
        handleFrappeError(error, 'Error listing flow runs');
    }
}

export interface FlowRunsPage {
    items: FlowRunSummary[];
    total: number;
}

/** Page of Flow Runs across all flows (Executions page). `fromDate` is a UTC ISO string. */
export async function listFlowRunsPage(params: {
    status?: string;
    search?: string;
    fromDate?: string;
    start?: number;
    limit?: number;
}): Promise<FlowRunsPage> {
    try {
        const result = await call.get('huf.ai.flow.api.list_flow_runs_page', {
            status: params.status,
            search: params.search || undefined,
            from_date: params.fromDate,
            start: params.start ?? 0,
            limit: params.limit ?? 20,
        });
        return result.message as FlowRunsPage;
    } catch (error) {
        handleFrappeError(error, 'Error listing flow runs');
    }
}

/** "Flow: <name> > <step title>" for Agent Runs made by flow steps; null where unknown. */
export async function getFlowStepLabels(
    items: Array<{ flow_run: string; flow_node_id?: string | null }>
): Promise<Array<string | null>> {
    try {
        const result = await call.post('huf.ai.flow.api.get_flow_step_labels', {
            items: JSON.stringify(items),
        });
        return result.message as Array<string | null>;
    } catch {
        return items.map(() => null);
    }
}

/** System Manager only: fail a run stuck in Queued/Running. */
export async function markFlowRunFailed(flowRunId: string): Promise<{ flow_run_id: string; status: string }> {
    try {
        const result = await call.post('huf.ai.flow.api.mark_flow_run_failed', { flow_run_id: flowRunId });
        return result.message as { flow_run_id: string; status: string };
    } catch (error) {
        handleFrappeError(error, `Error marking flow run ${flowRunId} as failed`);
    }
}

/** Approve a flow run waiting for approval */
export async function approveFlowRun(
    flowRunId: string,
    comment?: string
): Promise<{ flow_run_id: string; status: string; current_node_id: string }> {
    try {
        const result = await call.post('huf.ai.flow.api.approve_flow_run', {
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
        const result = await call.post('huf.ai.flow.api.reject_flow_run', {
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
        const result = await call.post('huf.ai.flow.api.resume_flow_run', {
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
        const result = await call.get('huf.ai.flow.api.get_pending_approvals');
        return result.message as PendingApproval[];
    } catch (error) {
        handleFrappeError(error, 'Error fetching pending approvals');
    }
}

// ─── Integration connection status (Slack / Gmail / Drive / Sheets steps) ───

export interface FlowIntegrationStatus {
    label: string;
    connected: boolean;
}

/** Which integrations the flow builder's steps use and whether each has credentials. */
export async function getFlowIntegrationStatus(): Promise<Record<string, FlowIntegrationStatus>> {
    try {
        const result = await call.get('huf.ai.flow.integrations.get_flow_integration_status');
        return (result.message ?? {}) as Record<string, FlowIntegrationStatus>;
    } catch {
        // Advisory only: without it the builder simply shows no "Not connected" badges.
        return {};
    }
}

export * from './flow/flowConversionApi';
