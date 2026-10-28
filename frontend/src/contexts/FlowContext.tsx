import { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef, ReactNode } from 'react';
import { toast } from '@/lib/toast';
import { Flow, FlowMetadata, FlowNode, FlowEdge } from '../types/flow.types';
import { flowService } from '../services/flowService';
import { popSnapshot, pushSnapshot } from '../lib/flowUndoStack';
import { tidyPositions } from '../lib/flowLayout';
import { BLOCKED_TOAST_ID } from '../lib/flowValidation';
import { followRenamedTarget } from '../lib/flowEdgeLabels';
import { removeStep, type RemoveStepMode } from '../lib/flowEdit';

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
  /** Change a step's data from the latest committed value, so quick consecutive edits never overwrite each other. */
  updateNodeData: (nodeId: string, update: (data: FlowNode['data']) => FlowNode['data']) => void;
  /** The latest committed copy of a step. */
  getNode: (nodeId: string) => FlowNode | undefined;
  /** Remove a step. Default `reconnect` joins the step before it to the step after it; `cascade` also removes what only it led to. */
  deleteNode: (nodeId: string, mode?: RemoveStepMode) => void;
  /** Remove one connection between two steps. */
  deleteEdge: (edgeId: string) => void;
  addEdge: (edge: FlowEdge) => void;
  /** Re-arrange the steps in a clean layered layout (undoable). */
  tidyLayout: () => void;
  /** Bumped when steps are moved by the app (Tidy layout, its undo), so the canvas re-reads their positions. */
  layoutRevision: number;
  undo: () => void;
  canUndo: boolean;
  saveFlow: () => Promise<void>;
  /** Publish or unpublish a flow; the active flow and the list pick up the new status. */
  setFlowPublished: (flowId: string, published: boolean) => Promise<void>;
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

  // Undo history for node deletion. Full nodes+edges snapshots are taken before
  // each delete and replayed verbatim on undo, so a restored node can never come
  // back with dangling edges. Session-local only: cleared on flow switch and
  // discarded on reload (not persisted undo).
  // The stack lives in a ref so push/pop are plain synchronous mutations (no side
  // effects inside state updaters); the state counter only drives canUndo.
  const UNDO_STACK_LIMIT = 20;
  const undoStackRef = useRef<{ nodes: FlowNode[]; edges: FlowEdge[] }[]>([]);
  const [undoDepth, setUndoDepth] = useState(0);
  const [layoutRevision, setLayoutRevision] = useState(0);

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
    // Never keep showing the previous flow while the next one loads: settings, Run and Publish would act on the wrong flow.
    if (activeFlowRef.current?.id !== flowId) setActiveFlowState(flowService.getCachedFlow(flowId));
    setSelectedNodeId(null);
    undoStackRef.current = [];
    setUndoDepth(0);
  }, []);


  const createFlow = useCallback(async (name: string, category?: string) => {
    const newFlow = await flowService.createFlow(name, category);
    setActiveFlowId(newFlow.id);
    setActiveFlowState(flowService.getCachedFlow(newFlow.id) ?? newFlow);
    setHasUnsavedChanges(false);
    setSaveState('saved');
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

  const setFlowPublished = useCallback(async (flowId: string, published: boolean) => {
    await flowService.setPublished(flowId, published);
    const cached = flowService.getCachedFlow(flowId);
    if (cached && flowId === activeFlowRef.current?.id) {
      setActiveFlowState(prev => (prev ? { ...prev, status: cached.status } : prev));
    }
    await refreshFlows();
  }, [refreshFlows]);

  // ─── Save Flow Logic ──────────────────────────────────────────────

  const saveFlow = useCallback(async () => {
    if (!activeFlowId || !activeFlow || !hasUnsavedChanges) return;

    setSaveState('saving');
    try {
      await flowService.saveFlow(activeFlow);
      setSaveState('saved');
      setHasUnsavedChanges(false);

      // The "create a procedure from this flow on save" checkbox (if enabled) runs
      // after the flow itself is saved and leaves a note on the doc explaining what
      // happened -- surface it so the user isn't left guessing. A missing note (the
      // checkbox was off) is silently skipped.
      try {
        const conversion = await flowService.getConversionStatus(activeFlowId);
        if (conversion.conversion_note) {
          if (conversion.converted_procedure) {
            toast.success(conversion.conversion_note);
          } else {
            toast.info(conversion.conversion_note);
          }
        }
      } catch (conversionErr) {
        // Non-critical: the flow itself saved fine, just couldn't fetch the note.
        console.error('Failed to fetch flow conversion status:', conversionErr);
      }
    } catch (err: unknown) {
      setSaveState('error');
      console.error('Failed to save flow:', err);
      // We don't throw here so the UI can handle the error state gracefully
      throw err;
    }
  }, [activeFlowId, activeFlow, hasUnsavedChanges]);

  // ─── Synchronous node/edge mutations (cache-only, fast) ────────────

  const markUnsaved = useCallback(() => {
    toast.dismiss(BLOCKED_TOAST_ID);
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
    // Router path names that still equal this step's old title follow its rename.
    const before = activeFlowRef.current;
    const oldLabel = before?.nodes.find(n => n.id === nodeId)?.data.label;
    const newLabel = updates.data?.label;
    const renamedEdges = before && oldLabel !== undefined && newLabel !== undefined
      ? followRenamedTarget(before.edges, nodeId, oldLabel, newLabel)
      : undefined;
    const edgesChanged = Boolean(before && renamedEdges && renamedEdges !== before.edges);
    if (before) {
      // Keep the ref current right away: two edits in the same tick must build on each other.
      const updatedNodes = before.nodes.map(n => (n.id === nodeId ? { ...n, ...updates } : n));
      activeFlowRef.current = { ...before, nodes: updatedNodes, ...(edgesChanged && renamedEdges ? { edges: renamedEdges } : {}) };
    }
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updatedNodes = prev.nodes.map(n =>
        n.id === nodeId ? { ...n, ...updates } : n
      );
      const updated = { ...prev, nodes: updatedNodes, ...(edgesChanged && renamedEdges ? { edges: renamedEdges } : {}) };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNode(activeFlowId, nodeId, updates);
    if (edgesChanged && renamedEdges) flowService.updateEdges(activeFlowId, renamedEdges);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const getNode = useCallback((nodeId: string) => activeFlowRef.current?.nodes.find(n => n.id === nodeId), []);

  const updateNodeData = useCallback((nodeId: string, update: (data: FlowNode['data']) => FlowNode['data']) => {
    const current = activeFlowRef.current?.nodes.find(n => n.id === nodeId);
    if (!current) return;
    updateNode(nodeId, { data: update(current.data) });
  }, [updateNode]);

  // Restore a prior nodes+edges snapshot. Goes through the same context-level
  // update as other structural mutations, so FlowCanvas's resync effect (keyed on
  // node/edge counts) cancels any in-flight debounced push before re-syncing.
  const restoreSnapshot = useCallback((snapshot: { nodes: FlowNode[]; edges: FlowEdge[] }) => {
    if (!activeFlowId) return;
    setActiveFlowState(prev => {
      if (!prev) return prev;
      const updated = { ...prev, nodes: snapshot.nodes, edges: snapshot.edges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodesAndEdges(activeFlowId, snapshot.nodes, snapshot.edges);
    setLayoutRevision(v => v + 1);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const undo = useCallback(() => {
    const { snapshot, rest } = popSnapshot(undoStackRef.current);
    if (!snapshot) return;
    undoStackRef.current = rest;
    setUndoDepth(undoStackRef.current.length);
    restoreSnapshot(snapshot);
  }, [restoreSnapshot]);

  const deleteNode = useCallback((nodeId: string, mode: RemoveStepMode = 'reconnect') => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev) return;
    const deletedNode = prev.nodes.find(n => n.id === nodeId);
    undoStackRef.current = pushSnapshot(undoStackRef.current, { nodes: prev.nodes, edges: prev.edges }, UNDO_STACK_LIMIT);
    setUndoDepth(undoStackRef.current.length);
    const { nodes: updatedNodes, edges: updatedEdges } = removeStep({ nodes: prev.nodes, edges: prev.edges }, nodeId, mode);
    const removedCount = prev.nodes.length - updatedNodes.length;
    setActiveFlowState(current => {
      if (!current) return current;
      const updated = { ...current, nodes: updatedNodes, edges: updatedEdges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodesAndEdges(activeFlowId, updatedNodes, updatedEdges);
    if (selectedNodeId && !updatedNodes.some(n => n.id === selectedNodeId)) {
      setSelectedNodeId(null);
    }
    markUnsaved();
    const label = (deletedNode?.data as { label?: string } | undefined)?.label;
    toast('Node deleted', {
      description: removedCount > 1
        ? `"${label ?? 'The step'}" and ${removedCount - 1} step${removedCount - 1 === 1 ? '' : 's'} after it were removed from the flow.`
        : label ? `"${label}" was removed from the flow.` : undefined,
      action: {
        label: 'Undo',
        onClick: () => undo(),
      },
    });
  }, [activeFlowId, selectedNodeId, markUnsaved, undo]);

  const deleteEdge = useCallback((edgeId: string) => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev || !prev.edges.some(e => e.id === edgeId)) return;
    undoStackRef.current = pushSnapshot(undoStackRef.current, { nodes: prev.nodes, edges: prev.edges }, UNDO_STACK_LIMIT);
    setUndoDepth(undoStackRef.current.length);
    const updatedEdges = prev.edges.filter(e => e.id !== edgeId);
    setActiveFlowState(current => {
      if (!current) return current;
      const updated = { ...current, edges: updatedEdges };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateEdges(activeFlowId, updatedEdges);
    setSelectedEdgeId(null);
    markUnsaved();
    toast('Connection removed', {
      description: 'The step it led to is not connected any more. Connect it again or delete it.',
      action: { label: 'Undo', onClick: () => undo() },
    });
  }, [activeFlowId, markUnsaved, undo]);

  const tidyLayout = useCallback(() => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev || prev.nodes.length === 0) return;
    const positions = tidyPositions(prev.nodes, prev.edges);
    const updatedNodes = prev.nodes.map(n => ({ ...n, position: positions[n.id] ?? n.position }));
    undoStackRef.current = pushSnapshot(undoStackRef.current, { nodes: prev.nodes, edges: prev.edges }, UNDO_STACK_LIMIT);
    setUndoDepth(undoStackRef.current.length);
    setActiveFlowState(current => {
      if (!current) return current;
      const updated = { ...current, nodes: updatedNodes };
      lastSyncedFlowRef.current = updated;
      return updated;
    });
    flowService.updateNodesAndEdges(activeFlowId, updatedNodes, prev.edges);
    setLayoutRevision(v => v + 1);
    markUnsaved();
    toast('Layout tidied', { action: { label: 'Undo', onClick: () => undo() } });
  }, [activeFlowId, markUnsaved, undo]);

  const handleSetSelectedNode = useCallback((nodeId: string | null) => {
    toast.dismiss(BLOCKED_TOAST_ID);
    setSelectedNodeId(nodeId);
    if (nodeId) setSelectedEdgeId(null);
  }, []);

  const handleSetSelectedEdge = useCallback((edgeId: string | null) => {
    toast.dismiss(BLOCKED_TOAST_ID);
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
    updateNodeData,
    getNode,
    deleteNode,
    deleteEdge,
    addEdge,
    tidyLayout,
    layoutRevision,
    undo,
    canUndo: undoDepth > 0,
    saveFlow,
    setFlowPublished,
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
    updateNodeData,
    getNode,
    deleteNode,
    deleteEdge,
    addEdge,
    tidyLayout,
    layoutRevision,
    undo,
    undoDepth,
    saveFlow,
    setFlowPublished,
    refreshFlows,
  ]);

  return <FlowContext.Provider value={value}>{children}</FlowContext.Provider>;
}

/** Like useFlowContext, but returns undefined outside a FlowProvider (e.g. the Executions page). */
export function useOptionalFlowContext() {
  return useContext(FlowContext);
}

export function useFlowContext() {
  const context = useContext(FlowContext);
  if (context === undefined) {
    throw new Error('useFlowContext must be used within a FlowProvider');
  }
  return context;
}
