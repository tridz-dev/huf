import { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef, ReactNode } from 'react';
import { Flow, FlowMetadata, FlowNode, FlowEdge } from '../types/flow.types';
import { flowService } from '../services/flowService';
import { toast } from 'sonner';

export type SaveState = 'saved' | 'saving' | 'unsaved' | 'error';

interface FlowContextType {
  flows: FlowMetadata[];
  activeFlowId: string | null;
  activeFlow: Flow | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  loading: boolean;
  error: string | null;
  saveState: SaveState;
  hasUnsavedChanges: boolean;
  setActiveFlow: (flowId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setSelectedEdge: (edgeId: string | null) => void;
  createFlow: (name: string, category?: string) => Promise<Flow>;
  updateFlowName: (flowId: string, name: string) => Promise<void>;
  updateFlowMetadata: (flowId: string, updates: Partial<Flow>) => Promise<void>;
  deleteFlow: (flowId: string) => Promise<void>;
  updateNodes: (nodes: FlowNode[]) => void;
  updateEdges: (edges: FlowEdge[]) => void;
  updateNodesAndEdges: (nodes: FlowNode[], edges: FlowEdge[]) => void;
  addNode: (node: FlowNode) => void;
  updateNode: (nodeId: string, updates: Partial<FlowNode>) => void;
  deleteNode: (nodeId: string) => void;
  addEdge: (edge: FlowEdge) => void;
  undo: () => void;
  canUndo: boolean;
  saveFlow: () => Promise<void>;
  refreshFlows: () => Promise<void>;
}

const FlowContext = createContext<FlowContextType | undefined>(undefined);

// Deep equality check for flows to prevent unnecessary updates
function flowsEqual(a: Flow | null, b: Flow | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.id === b.id &&
    a.name === b.name &&
    a.description === b.description &&
    a.status === b.status &&
    a.category === b.category &&
    (a.settings?.mode || null) === (b.settings?.mode || null) &&
    (a.settings?.max_hops ?? null) === (b.settings?.max_hops ?? null) &&
    a.version === b.version &&
    a.nodes.length === b.nodes.length &&
    a.edges.length === b.edges.length
  );
}

export function FlowProvider({ children }: { children: ReactNode }) {
  const [flows, setFlows] = useState<FlowMetadata[]>([]);
  const [activeFlowId, setActiveFlowId] = useState<string | null>(null);
  const [activeFlow, setActiveFlowState] = useState<Flow | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('saved');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const hasFetchedRef = useRef(false);
  // Ref to track last synced flow to prevent circular updates
  const lastSyncedFlowRef = useRef<Flow | null>(null);
  const activeFlowRef = useRef<Flow | null>(activeFlow);

  // ─── Undo history for destructive canvas mutations (node deletion) ──
  // We snapshot the FULL nodes+edges pair before each destructive mutation,
  // rather than computing a per-action inverse. A whole-graph snapshot is
  // trivially correct (it can never leave a node's edges dangling, unlike a
  // hand-rolled inverse) at the cost of a bit more memory, which is fine at
  // a shallow depth. History is in-memory only: it does NOT survive a flow
  // save (undo can still revert past a save, back to an earlier unsaved
  // shape) and is discarded on reload or when switching to a different flow.
  const UNDO_STACK_LIMIT = 20;
  const [undoStack, setUndoStack] = useState<{ nodes: FlowNode[]; edges: FlowEdge[] }[]>([]);

  // Sync ref with state
  useEffect(() => {
    activeFlowRef.current = activeFlow;
  }, [activeFlow]);

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
      setHasUnsavedChanges(false);
      setSaveState('saved');
      return;
    }

    // First check local cache for instant display
    const cached = flowService.getCachedFlow(activeFlowId);
    if (cached) {
      setActiveFlowState(cached);
      setHasUnsavedChanges(false);
      setSaveState('saved');
      return;
    }

    // Fetch from backend
    try {
      setLoading(true);
      const flow = await flowService.getFlow(activeFlowId);
      setActiveFlowState(flow);
      setHasUnsavedChanges(false);
      setSaveState('saved');
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

  // Listen for flowService changes - only sync from other sources, not from our own updates
  useEffect(() => {
    const unsubscribe = flowService.subscribe(() => {
      if (activeFlowId) {
        const cached = flowService.getCachedFlow(activeFlowId);
        // Only update if the cached flow is different from what we last synced
        // and different from current active flow
        if (cached && !flowsEqual(cached, lastSyncedFlowRef.current) && !flowsEqual(cached, activeFlowRef.current)) {
          lastSyncedFlowRef.current = cached;
          setActiveFlowState(cached);
        }
      }
    });
    return unsubscribe;
  }, [activeFlowId]); // Only resubscribe on ID change, use ref for content comparison

  // Load active flow when ID changes (not when loadActiveFlow function changes)
  useEffect(() => {
    // Skip if we're already showing the correct flow
    if (activeFlowRef.current?.id === activeFlowId && activeFlowId) {
      return;
    }
    loadActiveFlow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeFlowId]);

  // ─── Realtime Event Listeners for Flow Execution Tracker ─────────────
  useEffect(() => {
    if (!activeFlowId) return;

    const handleNodeStart = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: 'running' as const } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleNodeEnd = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: data.status === 'success' ? ('success' as const) : ('error' as const) } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleFlowPaused = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        const nodes = prev.nodes.map(n =>
          n.id === data.node_id ? { ...n, data: { ...n.data, status: 'waiting' as const } } : n
        );
        return { ...prev, nodes };
      });
    };

    const handleFlowCompleted = (e: Event) => {
      const data = (e as CustomEvent).detail;
      setActiveFlowState(prev => {
        if (!prev) return prev;
        // Mark node as success if provided
        const nodes = prev.nodes.map(n =>
          data.node_id && n.id === data.node_id ? { ...n, data: { ...n.data, status: 'success' as const } } : n
        );
        return { ...prev, nodes };
      });
      refreshFlows(); // Reload flows to get updated statuses
    };

    const handleFlowError = (e: Event) => {
      const data = (e as CustomEvent).detail;
      // Mark flow as error
      setActiveFlowState(prev => {
        if (!prev) return prev;
        // Mark the active node as error
        const nodes = prev.nodes.map(n =>
          n.data.status === 'running' || (data.node_id && n.id === data.node_id)
            ? { ...n, data: { ...n.data, status: 'error' as const } }
            : n
        );
        return { ...prev, nodes };
      });
    };

    window.addEventListener('frappe:flow_node_start', handleNodeStart);
    window.addEventListener('frappe:flow_node_end', handleNodeEnd);
    window.addEventListener('frappe:flow_paused', handleFlowPaused);
    window.addEventListener('frappe:flow_completed', handleFlowCompleted);
    window.addEventListener('frappe:flow_error', handleFlowError);

    return () => {
      window.removeEventListener('frappe:flow_node_start', handleNodeStart);
      window.removeEventListener('frappe:flow_node_end', handleNodeEnd);
      window.removeEventListener('frappe:flow_paused', handleFlowPaused);
      window.removeEventListener('frappe:flow_completed', handleFlowCompleted);
      window.removeEventListener('frappe:flow_error', handleFlowError);
    };
  }, [activeFlowId, refreshFlows]);

  const setActiveFlow = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    setSelectedNodeId(null);
    // Undo history is scoped to a single flow session; switching flows starts fresh.
    setUndoStack([]);
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

  const updateFlowMetadata = useCallback(async (flowId: string, updates: Partial<Flow>) => {
    await flowService.updateFlow(flowId, updates);
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

  // ─── Save Flow Logic ──────────────────────────────────────────────

  const saveFlow = useCallback(async () => {
    if (!activeFlowId || !activeFlow || !hasUnsavedChanges) return;

    setSaveState('saving');
    try {
      await flowService.saveFlow(activeFlow);
      setSaveState('saved');
      setHasUnsavedChanges(false);
    } catch (err: unknown) {
      setSaveState('error');
      console.error('Failed to save flow:', err);
      // We don't throw here so the UI can handle the error state gracefully
      throw err;
    }
  }, [activeFlowId, activeFlow, hasUnsavedChanges]);

  // ─── Synchronous node/edge mutations (cache-only, fast) ────────────

  const markUnsaved = useCallback(() => {
    setHasUnsavedChanges(true);
    setSaveState('unsaved');
  }, []);

  // Update local state immediately and track what we synced
  const updateNodes = useCallback((nodes: FlowNode[]) => {
    if (!activeFlowId) return;
    // Update local state first to avoid flicker
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, nodes };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodes(activeFlowId, nodes);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const updateEdges = useCallback((edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, edges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateEdges(activeFlowId, edges);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const updateNodesAndEdges = useCallback((nodes: FlowNode[], edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, nodes, edges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodesAndEdges(activeFlowId, nodes, edges);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const addNode = useCallback((node: FlowNode) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, nodes: [...prev.nodes, node] };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.addNode(activeFlowId, node);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const updateNode = useCallback((nodeId: string, updates: Partial<FlowNode>) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updatedNodes = prev.nodes.map(n =>
        n.id === nodeId ? { ...n, ...updates } : n
      );
      const updated = { ...prev, nodes: updatedNodes };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNode(activeFlowId, nodeId, updates);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  // Restore a prior nodes+edges snapshot (used by undo). This goes through the
  // same context-level state update as any other structural mutation, which is
  // what makes it safe against FlowCanvas's 50ms debounce: FlowCanvas re-syncs
  // its local nodes/edges from activeFlow whenever nodes.length or edges.length
  // changes (see the useEffect keyed on activeFlow?.nodes.length /
  // activeFlow?.edges.length in FlowCanvas.tsx), and that same effect cancels
  // any in-flight debounced push (updateTimeoutRef / pendingUpdateRef) before
  // re-syncing. Undoing a delete always changes node count, so it always hits
  // that path — a debounced write that was mid-flight when undo fires is
  // discarded rather than allowed to clobber the restored state with stale data.
  const restoreSnapshot = useCallback((snapshot: { nodes: FlowNode[]; edges: FlowEdge[] }) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, nodes: snapshot.nodes, edges: snapshot.edges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodesAndEdges(activeFlowId, snapshot.nodes, snapshot.edges);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const undo = useCallback(() => {
    setUndoStack(prev => {
      if (prev.length === 0) return prev;
      const next = prev.slice(0, -1);
      const snapshot = prev[prev.length - 1];
      restoreSnapshot(snapshot);
      return next;
    });
  }, [restoreSnapshot]);

  const deleteNode = useCallback((nodeId: string) => {
    if (!activeFlowId) return;
    let deletedNode: FlowNode | undefined;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      deletedNode = prev.nodes.find(n => n.id === nodeId);
      // Snapshot the pre-delete graph so undo can restore it verbatim —
      // this is what guarantees a restored node never comes back with its
      // edges dangling: we're not reconstructing edges, we're replaying the
      // exact prior edges array.
      setUndoStack(stack => [...stack, { nodes: prev.nodes, edges: prev.edges }].slice(-UNDO_STACK_LIMIT));
      const updatedNodes = prev.nodes.filter(n => n.id !== nodeId);
      const updatedEdges = prev.edges.filter(
        e => e.source !== nodeId && e.target !== nodeId
      );
      const updated = { ...prev, nodes: updatedNodes, edges: updatedEdges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.deleteNode(activeFlowId, nodeId);
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
    markUnsaved();
    const label = (deletedNode?.data as { label?: string } | undefined)?.label;
    toast('Node deleted', {
      description: label ? `"${label}" was removed from the flow.` : undefined,
      action: {
        label: 'Undo',
        onClick: () => undo(),
      },
    });
  }, [activeFlowId, selectedNodeId, markUnsaved, undo]);

  const handleSetSelectedNode = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    if (nodeId) setSelectedEdgeId(null);
  }, []);

  const handleSetSelectedEdge = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId);
    if (edgeId) setSelectedNodeId(null);
  }, []);

  const addEdge = useCallback((edge: FlowEdge) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, edges: [...prev.edges, edge] };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.addEdge(activeFlowId, edge);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const value = useMemo(() => ({
    flows,
    activeFlowId,
    activeFlow,
    selectedNodeId,
    selectedEdgeId,
    loading,
    error,
    saveState,
    hasUnsavedChanges,
    setActiveFlow,
    setSelectedNode: handleSetSelectedNode,
    setSelectedEdge: handleSetSelectedEdge,
    createFlow,
    updateFlowName,
    updateFlowMetadata,
    deleteFlow,
    updateNodes,
    updateEdges,
    updateNodesAndEdges,
    addNode,
    updateNode,
    deleteNode,
    addEdge,
    undo,
    canUndo: undoStack.length > 0,
    saveFlow,
    refreshFlows,
  }), [
    flows,
    activeFlowId,
    activeFlow,
    selectedNodeId,
    selectedEdgeId,
    loading,
    error,
    saveState,
    hasUnsavedChanges,
    setActiveFlow,
    handleSetSelectedNode,
    handleSetSelectedEdge,
    createFlow,
    updateFlowName,
    updateFlowMetadata,
    deleteFlow,
    updateNodes,
    updateEdges,
    updateNodesAndEdges,
    addNode,
    updateNode,
    deleteNode,
    addEdge,
    undo,
    undoStack.length,
    saveFlow,
    refreshFlows,
  ]);

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (context === undefined) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}
