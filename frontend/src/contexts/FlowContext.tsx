import { createContext, useContext, useState, useCallback, useEffect, useRef, ReactNode } from 'react';
import { Flow, FlowMetadata, FlowNode, FlowEdge } from '../types/flow.types';
import { flowService } from '../services/flowService';

interface FlowContextType {
  flows: FlowMetadata[];
  activeFlowId: string | null;
  activeFlow: Flow | null;
  selectedNodeId: string | null;
  loading: boolean;
  error: string | null;
  setActiveFlow: (flowId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;
  createFlow: (name: string, category?: string) => Promise<Flow>;
  updateFlowName: (flowId: string, name: string) => Promise<void>;
  deleteFlow: (flowId: string) => Promise<void>;
  updateNodes: (nodes: FlowNode[]) => void;
  updateEdges: (edges: FlowEdge[]) => void;
  updateNodesAndEdges: (nodes: FlowNode[], edges: FlowEdge[]) => void;
  addNode: (node: FlowNode) => void;
  updateNode: (nodeId: string, updates: Partial<FlowNode>) => void;
  deleteNode: (nodeId: string) => void;
  addEdge: (edge: FlowEdge) => void;
  saveFlow: () => Promise<void>;
  refreshFlows: () => Promise<void>;
}

const FlowContext = createContext<FlowContextType | undefined>(undefined);

export function FlowProvider({ children }: { children: ReactNode }) {
  const [flows, setFlows] = useState<FlowMetadata[]>([]);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [activeFlow, setActiveFlowState] = useState<Flow | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasFetchedRef = useRef(false);

  const refreshFlows = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const items = await flowService.getAllFlows();
      setFlows(items);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load flows';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadActiveFlow = useCallback(async () => {
    if (!activeFlowId) {
      setActiveFlowState(null);
      return;
    }

    // First check local cache for instant display
    const cached = flowService.getCachedFlow(activeFlowId);
    if (cached) {
      setActiveFlowState(cached);
      return;
    }

    // Fetch from backend
    try {
      setLoading(true);
      const flow = await flowService.getFlow(activeFlowId);
      setActiveFlowState(flow);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load flow';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [activeFlowId]);

  // Initial fetch
  useEffect(() => {
    if (!hasFetchedRef.current) {
      hasFetchedRef.current = true;
      refreshFlows();
    }
  }, [refreshFlows]);

  // Listen for flowService changes
  useEffect(() => {
    const unsubscribe = flowService.subscribe(() => {
      // Reload active flow from cache when nodes/edges change
      if (activeFlowId) {
        const cached = flowService.getCachedFlow(activeFlowId);
        if (cached) setActiveFlowState(cached);
      }
    });
    return unsubscribe;
  }, [activeFlowId]);

  // Load active flow when it changes
  useEffect(() => {
    loadActiveFlow();
  }, [loadActiveFlow]);

  const setActiveFlow = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    setSelectedNodeId(null);
  }, []);

  const setSelectedNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
  }, []);

  const createFlow = useCallback(async (name: string, category?: string) => {
    const newFlow = await flowService.createFlow(name, category);
    setActiveFlowId(newFlow.id);
    await refreshFlows();
    return newFlow;
  }, [refreshFlows]);

  const updateFlowName = useCallback(async (flowId: string, name: string) => {
    await flowService.updateFlowName(flowId, name);
    await refreshFlows();
    if (flowId === activeFlowId) {
      const cached = flowService.getCachedFlow(flowId);
      if (cached) setActiveFlowState(cached);
    }
  }, [activeFlowId, refreshFlows]);

  const deleteFlow = useCallback(async (flowId: string) => {
    await flowService.deleteFlow(flowId);
    await refreshFlows();
    if (activeFlowId === flowId) {
      setActiveFlowId(null);
    }
  }, [activeFlowId, refreshFlows]);

  // ─── Synchronous node/edge mutations (cache-only, fast) ────────────

  const updateNodes = useCallback((nodes: FlowNode[]) => {
    if (!activeFlowId) return;
    flowService.updateNodes(activeFlowId, nodes);
  }, [activeFlowId]);

  const updateEdges = useCallback((edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    flowService.updateEdges(activeFlowId, edges);
  }, [activeFlowId]);

  const updateNodesAndEdges = useCallback((nodes: FlowNode[], edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    flowService.updateNodesAndEdges(activeFlowId, nodes, edges);
  }, [activeFlowId]);

  const addNode = useCallback((node: FlowNode) => {
    if (!activeFlowId) return;
    flowService.addNode(activeFlowId, node);
  }, [activeFlowId]);

  const updateNode = useCallback((nodeId: string, updates: Partial<FlowNode>) => {
    if (!activeFlowId) return;
    flowService.updateNode(activeFlowId, nodeId, updates);
  }, [activeFlowId]);

  const deleteNode = useCallback((nodeId: string) => {
    if (!activeFlowId) return;
    flowService.deleteNode(activeFlowId, nodeId);
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
  }, [activeFlowId, selectedNodeId]);

  const addEdge = useCallback((edge: FlowEdge) => {
    if (!activeFlowId) return;
    flowService.addEdge(activeFlowId, edge);
  }, [activeFlowId]);

  // ─── Explicit save to backend ──────────────────────────────────────

  const saveFlow = useCallback(async () => {
    if (!activeFlow) return;
    try {
      setLoading(true);
      await flowService.saveFlow(activeFlow);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save flow';
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [activeFlow]);

  const value: FlowContextType = {
    flows,
    activeFlowId,
    activeFlow,
    selectedNodeId,
    loading,
    error,
    setActiveFlow,
    setSelectedNode,
    createFlow,
    updateFlowName,
    deleteFlow,
    updateNodes,
    updateEdges,
    updateNodesAndEdges,
    addNode,
    updateNode,
    deleteNode,
    addEdge,
    saveFlow,
    refreshFlows,
  };

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (context === undefined) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}
