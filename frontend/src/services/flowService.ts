/**
 * Flow Service — backend-connected flow management.
 *
 * Previously used an in-memory Map (mock). Now calls the backend
 * via flowApi.ts and uses flowSerializer.ts for JSON conversion.
 *
 * Keeps the same public method signatures so FlowContext.tsx needs
 * minimal changes. Methods that were synchronous are now async.
 */

import { cancelFlowRun as apiCancelFlowRun } from './flow/flowRunActionsApi';
import { Flow, FlowMetadata, FlowNode, FlowEdge, FlowStatus } from '../types/flow.types';
import {
  getFlowDefinitions,
  getFlowDefinition,
  saveFlowDefinition,
  deleteFlowDefinition,
  updateFlowDefinitionFields,
  getFlowConversionStatus,
  runFlow as apiRunFlow,
  listFlowRuns as apiListFlowRuns,
  getFlowRun as apiGetFlowRun,
  approveFlowRun as apiApproveFlowRun,
  rejectFlowRun as apiRejectFlowRun,
  resumeFlowRun as apiResumeFlowRun,
  markFlowRunFailed as apiMarkFlowRunFailed,
  publishFlow as apiPublishFlow,
  unpublishFlow as apiUnpublishFlow,
} from './flowApi';
import type { FlowRunSummary, FlowRunDetail } from './flowApi';
import { serializeFlow, deserializeFlow, mapBackendStatusToFrontend, defaultContract } from './flowSerializer';
import type { BackendFlowGraph } from './flowApi';

class FlowService {
  private listeners: Set<() => void> = new Set();

  // ─── Local cache for fast access between saves ─────────────────────
  private flowCache: Map<string, Flow> = new Map();

  private notifyListeners() {
    this.listeners.forEach(listener => listener());
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  // ─── Read operations ───────────────────────────────────────────────

  /** Fetch all flows from backend and return as metadata list */
  async getAllFlows(): Promise<FlowMetadata[]> {
    const items = await getFlowDefinitions();
    return items.map(item => ({
      id: item.flow_id,
      name: item.flow_name,
      description: item.description || undefined,
      status: mapBackendStatusToFrontend(item.status),
      category: item.category || undefined,
      nodeCount: 0, // Will be populated when flow is loaded individually
      createdAt: new Date(item.modified),
      updatedAt: new Date(item.modified),
    }));
  }

  /** Fetch a single flow from backend and cache it locally */
  async getFlow(id: string): Promise<Flow | null> {
    try {
      const doc = await getFlowDefinition(id);
      if (!doc) return null;

      const graph = typeof doc.definition_json === 'string'
        ? JSON.parse(doc.definition_json) as BackendFlowGraph
        : doc.definition_json;

      const flow = deserializeFlow(doc.flow_id, doc.flow_name, doc.status, graph);
      // Name, description and category live on the Flow Definition record, not in the graph.
      flow.description = doc.description || '';
      flow.category = doc.category || 'Uncategorized';
      this.flowCache.set(id, flow);
      return flow;
    } catch {
      return null;
    }
  }

  /** Get a flow from the local cache (no API call) */
  getCachedFlow(id: string): Flow | null {
    return this.flowCache.get(id) || null;
  }

  // ─── Write operations ──────────────────────────────────────────────

  /** Create a new flow with a default trigger node */
  async createFlow(name: string, category?: string): Promise<Flow> {
    const flowId = `flow-${Date.now()}`;

    // Build a minimal valid graph (shared graph-IR Flow profile -- see flowSerializer.ts)
    const defaultGraph: BackendFlowGraph = {
      schema_version: '1.0.0',
      profile: 'flow',
      fingerprint: '0'.repeat(64),
      entry: 'empty_trigger',
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger.unset',
          config: {},
          next: null,
          _position: { x: 250, y: 100 },
          _label: 'Choose what starts this flow',
          _icon: 'CircleDashed',
        },
      ],
      contract: defaultContract(),
    };

    await saveFlowDefinition(flowId, defaultGraph);
    // The first save names the record after its id; store the real name and category.
    await updateFlowDefinitionFields(flowId, { flow_name: name, category: category || 'Uncategorized' });

    const newFlow: Flow = {
      id: flowId,
      name,
      description: '',
      status: 'draft',
      category: category || 'Uncategorized',
      nodes: [
        {
          id: 'empty_trigger',
          type: 'trigger',
          position: { x: 250, y: 100 },
          data: {
            label: 'Choose what starts this flow',
            nodeType: 'trigger',
            description: 'Choose what starts this flow',
            configured: false,
          },
        },
      ],
      edges: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      version: 1,
    };

    this.flowCache.set(flowId, newFlow);
    this.notifyListeners();
    return newFlow;
  }

  /** Save the current flow state to the backend */
  async saveFlow(flow: Flow): Promise<void> {
    const graph = serializeFlow(flow);
    await saveFlowDefinition(flow.id, graph);
    this.flowCache.set(flow.id, { ...flow, updatedAt: new Date() });
    this.notifyListeners();
  }

  /** Fetch the auto-convert-to-procedure checkbox and the outcome of the last
   * conversion attempt for a flow (see flowApi.getFlowConversionStatus). */
  async getConversionStatus(id: string) {
    return getFlowConversionStatus(id);
  }

  /**
   * Change a flow's name, description or category: only those record fields are written. The steps are NOT saved
   * here (that is the editor's Save), so unfinished edits can never make this call fail, and nothing is saved
   * behind the person's back.
   */
  async updateFlow(id: string, updates: Partial<Flow>): Promise<Flow | null> {
    const fields: { flow_name?: string; description?: string; category?: string } = {};
    if (typeof updates.name === 'string' && updates.name.trim()) fields.flow_name = updates.name;
    if (typeof updates.description === 'string') fields.description = updates.description;
    if (typeof updates.category === 'string') fields.category = updates.category;
    if (Object.keys(fields).length) {
      await updateFlowDefinitionFields(id, fields);
    }

    const flow = this.flowCache.get(id);
    if (!flow) return null;
    const updatedFlow: Flow = { ...flow, ...updates, updatedAt: new Date() };
    this.flowCache.set(id, updatedFlow);
    this.notifyListeners();
    return updatedFlow;
  }

  /** Delete a flow from the backend. A refusal (not allowed, still in use) is thrown so the caller can say so. */
  async deleteFlow(id: string): Promise<boolean> {
    await deleteFlowDefinition(id);
    this.flowCache.delete(id);
    this.notifyListeners();
    return true;
  }

  /** Update flow name (backend + cache) */
  async updateFlowName(id: string, name: string): Promise<Flow | null> {
    await updateFlowDefinitionFields(id, { flow_name: name });
    return this.updateFlowLocal(id, { name });
  }

  /** Update flow status (backend + cache) */
  async updateFlowStatus(id: string, status: FlowStatus): Promise<Flow | null> {
    const statusMap: Record<string, string> = {
      'draft': 'Draft',
      'active': 'Active',
      'paused': 'Archived',
      'error': 'Draft',
    };
    await updateFlowDefinitionFields(id, { status: statusMap[status] || 'Draft' });
    return this.updateFlowLocal(id, { status });
  }

  /** Publish (status Active) or unpublish (back to Draft) a flow, then mirror the status in the cache. */
  async setPublished(id: string, published: boolean): Promise<Flow | null> {
    if (published) await apiPublishFlow(id);
    else await apiUnpublishFlow(id);
    return this.updateFlowLocal(id, { status: published ? 'active' : 'draft' });
  }

  /** Run a flow via the backend */
  async runFlow(flowId: string, payload?: Record<string, unknown>): Promise<{ flow_run_id: string; status: string }> {
    return apiRunFlow(flowId, payload);
  }

  // ─── Flow Run API Wrappers ──────────────────────────────────────────

  async listFlowRuns(flowId?: string, status?: string, limit?: number): Promise<FlowRunSummary[]> {
    return apiListFlowRuns(flowId, status, limit);
  }

  async getFlowRun(flowRunId: string): Promise<FlowRunDetail | undefined> {
    return apiGetFlowRun(flowRunId);
  }

  async approveFlowRun(flowRunId: string, comment?: string) {
    return apiApproveFlowRun(flowRunId, comment);
  }

  async rejectFlowRun(flowRunId: string, comment?: string) {
    return apiRejectFlowRun(flowRunId, comment);
  }

  async resumeFlowRun(flowRunId: string, input?: Record<string, unknown>) {
    return apiResumeFlowRun(flowRunId, input);
  }

  async markFlowRunFailed(flowRunId: string) {
    return apiMarkFlowRunFailed(flowRunId);
  }

  async cancelFlowRun(flowRunId: string) {
    return apiCancelFlowRun(flowRunId);
  }

  // ─── Local-only mutation helpers (update cache, notify) ────────────

  /**
   * Update the local cache and notify listeners.
   * Does NOT save to backend — used for local-only field updates
   * where the backend was already updated separately.
   */
  private updateFlowLocal(id: string, updates: Partial<Flow>): Flow | null {
    const flow = this.flowCache.get(id);
    if (!flow) return null;

    const updatedFlow = {
      ...flow,
      ...updates,
      updatedAt: new Date(),
      version: (flow.version || 0) + 1
    };
    this.flowCache.set(id, updatedFlow);
    this.notifyListeners();
    return updatedFlow;
  }

  // ─── Node/Edge mutation (operates on cache, auto-saves) ────────────

  updateNodes(flowId: string, nodes: FlowNode[]): Flow | null {
    return this.updateFlowLocal(flowId, { nodes });
  }

  updateEdges(flowId: string, edges: FlowEdge[]): Flow | null {
    return this.updateFlowLocal(flowId, { edges });
  }

  updateNodesAndEdges(flowId: string, nodes: FlowNode[], edges: FlowEdge[]): Flow | null {
    return this.updateFlowLocal(flowId, { nodes, edges });
  }

  addNode(flowId: string, node: FlowNode): Flow | null {
    const flow = this.flowCache.get(flowId);
    if (!flow) return null;
    return this.updateNodes(flowId, [...flow.nodes, node]);
  }

  updateNode(flowId: string, nodeId: string, updates: Partial<FlowNode>): Flow | null {
    const flow = this.flowCache.get(flowId);
    if (!flow) return null;
    const updatedNodes = flow.nodes.map(n =>
      n.id === nodeId ? { ...n, ...updates } : n
    );
    return this.updateNodes(flowId, updatedNodes);
  }

  deleteNode(flowId: string, nodeId: string): Flow | null {
    const flow = this.flowCache.get(flowId);
    if (!flow) return null;
    const updatedNodes = flow.nodes.filter(n => n.id !== nodeId);
    const updatedEdges = flow.edges.filter(
      e => e.source !== nodeId && e.target !== nodeId
    );
    return this.updateNodesAndEdges(flowId, updatedNodes, updatedEdges);
  }

  addEdge(flowId: string, edge: FlowEdge): Flow | null {
    const flow = this.flowCache.get(flowId);
    if (!flow) return null;
    return this.updateEdges(flowId, [...flow.edges, edge]);
  }
}

export const flowService = new FlowService();
