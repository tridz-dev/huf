/**
 * Flow Service — backend-connected flow management.
 *
 * Previously used an in-memory Map (mock). Now calls the backend
 * via flowApi.ts and uses flowSerializer.ts for JSON conversion.
 *
 * Keeps the same public method signatures so FlowContext.tsx needs
 * minimal changes. Methods that were synchronous are now async.
 */

import { Flow, FlowMetadata, FlowNode, FlowEdge, FlowStatus } from '../types/flow.types';
import {
  getFlowDefinitions,
  getFlowDefinition,
  saveFlowDefinition,
  deleteFlowDefinition,
  updateFlowDefinitionFields,
  runFlow as apiRunFlow,
  listFlowRuns as apiListFlowRuns,
  getFlowRun as apiGetFlowRun,
  approveFlowRun as apiApproveFlowRun,
  rejectFlowRun as apiRejectFlowRun,
} from './flowApi';
import type { FlowRunSummary, FlowRunDetail } from './flowApi';
import { serializeFlow, deserializeFlow, mapBackendStatusToFrontend } from './flowSerializer';
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
      description: undefined,
      status: mapBackendStatusToFrontend(item.status),
      category: undefined,
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

    // Build a minimal valid graph
    const defaultGraph: BackendFlowGraph = {
      schema_version: 1,
      id: flowId,
      version: 1,
      entry: 'empty-trigger',
      nodes: [
        {
          id: 'empty-trigger',
          type: 'trigger.webhook',
          config: {},
          _position: { x: 250, y: 100 },
          _label: 'Select Trigger',
          _icon: 'Webhook',
        },
      ],
      edges: [],
      settings: { mode: 'normal', max_hops: 100 },
      metadata: { name, category },
    };

    await saveFlowDefinition(flowId, defaultGraph);

    const newFlow: Flow = {
      id: flowId,
      name,
      description: 'New automation flow',
      status: 'draft',
      category: category || 'Uncategorized',
      nodes: [
        {
          id: 'empty-trigger',
          type: 'trigger',
          position: { x: 250, y: 100 },
          data: {
            label: 'Select Trigger',
            nodeType: 'trigger',
            description: 'Empty Trigger',
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

  /** Update a flow locally and save to backend */
  async updateFlow(id: string, updates: Partial<Flow>): Promise<Flow | null> {
    const flow = this.flowCache.get(id);
    if (!flow) return null;

    const updatedFlow: Flow = {
      ...flow,
      ...updates,
      updatedAt: new Date(),
      version: flow.version + 1,
    };

    this.flowCache.set(id, updatedFlow);
    this.notifyListeners();

    // Save to backend
    const graph = serializeFlow(updatedFlow);
    await saveFlowDefinition(id, graph);

    return updatedFlow;
  }

  /** Delete a flow from the backend */
  async deleteFlow(id: string): Promise<boolean> {
    try {
      await deleteFlowDefinition(id);
      this.flowCache.delete(id);
      this.notifyListeners();
      return true;
    } catch {
      return false;
    }
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

  // ─── Local-only mutation helpers (update cache, notify) ────────────

  /**
   * Update the local cache and notify listeners.
   * Does NOT save to backend — used for local-only field updates
   * where the backend was already updated separately.
   */
  private updateFlowLocal(id: string, updates: Partial<Flow>): Flow | null {
    const flow = this.flowCache.get(id);
    if (!flow) return null;

    const updatedFlow = { ...flow, ...updates, updatedAt: new Date() };
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
