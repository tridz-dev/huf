import { createContext, useContext, useState, useCallback, useEffect, useMemo, useRef, ReactNode } from 'react';
import { toast } from '@/lib/toast';
import { Flow, FlowMetadata, FlowNode, FlowEdge } from '../types/flow.types';
import { flowService } from '../services/flowService';
import { useFlowHistory } from '../lib/flow-history/useFlowHistory';
import { removedDescription } from '../lib/flow-history/historyText';
import { useHistoryStepper } from '../lib/flow-history/useHistoryStepper';
import type { GraphChange, GraphSnapshot } from '../lib/flow-history/graphChange';
import { tidyPositions } from '../lib/flow/flowLayout';
import { followRenamedTarget } from '../lib/flow/flowEdgeLabels';
import { removeStep, type RemoveStepMode } from '../lib/flow/flowEdit';
import { announceConversion, flowsEqual } from '../lib/flow-graph/flowSync';
import { useFlowRealtimeStatus } from '../hooks/flow/useFlowRealtimeStatus';

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
  getFlow: () => Flow | null; // latest committed flow, even before React re-renders with it
  /** Remove a step. Default `reconnect` joins the step before it to the step after it; `cascade` also removes what only it led to. */
  deleteNode: (nodeId: string, mode?: RemoveStepMode) => void;
  /** Remove one connection between two steps. */
  deleteEdge: (edgeId: string) => void;
  addEdge: (edge: FlowEdge) => void;
  /** Re-arrange the steps in a clean layered layout (undoable). */
  tidyLayout: () => void;
  /** Bumped when steps are moved by the app (Tidy layout, its undo), so the canvas re-reads their positions. */
  layoutRevision: number;
  /** Step back through edits (config, add, delete, move, connect, tidy). Bounded to 100 steps. */
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  /** What the next Undo / Redo would do, in words ("Moved a step"); undefined when there is nothing to do. */
  undoLabel?: string;
  redoLabel?: string;
  saveFlow: () => Promise<void>;
  /** Publish or unpublish a flow; the active flow and the list pick up the new status. */
  setFlowPublished: (flowId: string, published: boolean) => Promise<void>;
  refreshFlows: () => Promise<void>;
}

const FlowContext = createContext<FlowContextType | undefined>(undefined);

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
  // Applies an edit to the active flow (the ref is updated at once: two edits in one tick build on each other), marks it synced
  // (the flowService echo is ignored) and records it in the undo history.
  const history = useFlowHistory();
  const { record: recordHistory, reset: resetHistory, undo: undoHistory, redo: redoHistory } = history;
  const patchActive = useCallback((patch: (flow: Flow) => Partial<Flow>, hint?: Partial<GraphChange>) => {
    const prev = activeFlowRef.current;
    if (!prev) return;
    const updated = { ...prev, ...patch(prev) };
    recordHistory({ nodes: prev.nodes, edges: prev.edges }, { nodes: updated.nodes, edges: updated.edges }, hint);
    activeFlowRef.current = updated;
    lastSyncedFlowRef.current = updated;
    setActiveFlowState(updated);
  }, [recordHistory]);

  // Steps of undo history live in useFlowHistory (session-local: cleared on flow switch, gone after a reload).
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

  useFlowRealtimeStatus(activeFlowId, setActiveFlowState, refreshFlows);

  const setActiveFlow = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    // Never keep showing the previous flow while the next one loads: settings, Run and Publish would act on the wrong flow.
    if (activeFlowRef.current?.id !== flowId) setActiveFlowState(flowService.getCachedFlow(flowId));
    setSelectedNodeId(null);
    resetHistory();
  }, [resetHistory]);


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

      await announceConversion(activeFlowId);
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
    patchActive(() => ({ nodes }));
    flowService.updateNodes(activeFlowId, nodes);
    markUnsaved();
  }, [activeFlowId, markUnsaved, patchActive]);

  const updateEdges = useCallback((edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    patchActive(() => ({ edges }));
    flowService.updateEdges(activeFlowId, edges);
    markUnsaved();
  }, [activeFlowId, markUnsaved, patchActive]);

  const updateNodesAndEdges = useCallback((nodes: FlowNode[], edges: FlowEdge[]) => {
    if (!activeFlowId) return;
    patchActive(() => ({ nodes, edges }));
    flowService.updateNodesAndEdges(activeFlowId, nodes, edges);
    markUnsaved();
  }, [activeFlowId, markUnsaved, patchActive]);

  const addNode = useCallback((node: FlowNode) => {
    if (!activeFlowId) return;
    patchActive(prev => ({ nodes: [...prev.nodes, node] }));
    flowService.addNode(activeFlowId, node);
    markUnsaved();
  }, [activeFlowId, markUnsaved, patchActive]);

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
      const after = { ...before, nodes: updatedNodes, ...(edgesChanged && renamedEdges ? { edges: renamedEdges } : {}) };
      recordHistory({ nodes: before.nodes, edges: before.edges }, { nodes: after.nodes, edges: after.edges });
      activeFlowRef.current = after;
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
  }, [activeFlowId, markUnsaved, recordHistory]);

  const getNode = useCallback((nodeId: string) => activeFlowRef.current?.nodes.find(n => n.id === nodeId), []);
  const getFlow = useCallback(() => activeFlowRef.current, []);

  const updateNodeData = useCallback((nodeId: string, update: (data: FlowNode['data']) => FlowNode['data']) => {
    const current = activeFlowRef.current?.nodes.find(n => n.id === nodeId);
    if (!current) return;
    updateNode(nodeId, { data: update(current.data) });
  }, [updateNode]);

  // Put a snapshot from the history back (layoutRevision makes the canvas re-read it; selection and live status are not part of it).
  const restoreSnapshot = useCallback((snapshot: GraphSnapshot) => {
    const current = activeFlowRef.current;
    if (!activeFlowId || !current) return;
    const liveStatus = new Map(current.nodes.map(n => [n.id, n.data.status]));
    const nodes = snapshot.nodes.map(n => ({ ...n, selected: false, dragging: false, data: { ...n.data, status: liveStatus.get(n.id) ?? n.data.status } }));
    const updated = { ...current, nodes, edges: snapshot.edges };
    activeFlowRef.current = updated;
    lastSyncedFlowRef.current = updated;
    setActiveFlowState(updated);
    flowService.updateNodesAndEdges(activeFlowId, nodes, snapshot.edges);
    setSelectedNodeId(sel => (sel && nodes.some(n => n.id === sel) ? sel : null));
    setSelectedEdgeId(sel => (sel && snapshot.edges.some(e => e.id === sel) ? sel : null));
    setLayoutRevision(v => v + 1);
    markUnsaved();
  }, [activeFlowId, markUnsaved]);

  const { undo, redo } = useHistoryStepper({ getFlow, undoStep: undoHistory, redoStep: redoHistory, restore: restoreSnapshot });

  const deleteNode = useCallback((nodeId: string, mode: RemoveStepMode = 'reconnect') => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev) return;
    const deletedNode = prev.nodes.find(n => n.id === nodeId);
    const { nodes: updatedNodes, edges: updatedEdges } = removeStep({ nodes: prev.nodes, edges: prev.edges }, nodeId, mode);
    const removedCount = prev.nodes.length - updatedNodes.length;
    patchActive(() => ({ nodes: updatedNodes, edges: updatedEdges }));
    flowService.updateNodesAndEdges(activeFlowId, updatedNodes, updatedEdges);
    if (selectedNodeId && !updatedNodes.some(n => n.id === selectedNodeId)) {
      setSelectedNodeId(null);
    }
    markUnsaved();
    const label = (deletedNode?.data as { label?: string } | undefined)?.label;
    toast('Node deleted', { description: removedDescription(label, removedCount), action: { label: 'Undo', onClick: () => undo() } });
  }, [activeFlowId, selectedNodeId, markUnsaved, undo, patchActive]);

  const deleteEdge = useCallback((edgeId: string) => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev || !prev.edges.some(e => e.id === edgeId)) return;
    const updatedEdges = prev.edges.filter(e => e.id !== edgeId);
    patchActive(() => ({ edges: updatedEdges }));
    flowService.updateEdges(activeFlowId, updatedEdges);
    setSelectedEdgeId(null);
    markUnsaved();
    toast('Connection removed', {
      description: 'The step it led to is not connected any more. Connect it again or delete it.',
      action: { label: 'Undo', onClick: () => undo() },
    });
  }, [activeFlowId, markUnsaved, undo, patchActive]);

  const tidyLayout = useCallback(() => {
    if (!activeFlowId) return;
    const prev = activeFlowRef.current;
    if (!prev || prev.nodes.length === 0) return;
    const positions = tidyPositions(prev.nodes, prev.edges);
    const updatedNodes = prev.nodes.map(n => ({ ...n, position: positions[n.id] ?? n.position }));
    patchActive(() => ({ nodes: updatedNodes }), { kind: 'layout', label: 'Tidied the layout', group: undefined });
    flowService.updateNodesAndEdges(activeFlowId, updatedNodes, prev.edges);
    setLayoutRevision(v => v + 1);
    markUnsaved();
    toast('Layout tidied', { action: { label: 'Undo', onClick: () => undo() } });
  }, [activeFlowId, markUnsaved, undo, patchActive]);

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
    patchActive(prev => ({ edges: [...prev.edges, edge] }));
    flowService.addEdge(activeFlowId, edge);
    markUnsaved();
  }, [activeFlowId, markUnsaved, patchActive]);

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
    getFlow,
    deleteNode,
    deleteEdge,
    addEdge,
    tidyLayout,
    layoutRevision,
    undo,
    redo,
    canUndo: history.canUndo,
    canRedo: history.canRedo,
    undoLabel: history.undoLabel,
    redoLabel: history.redoLabel,
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
    getFlow,
    deleteNode,
    deleteEdge,
    addEdge,
    tidyLayout,
    layoutRevision,
    undo,
    redo,
    history.canUndo,
    history.canRedo,
    history.undoLabel,
    history.redoLabel,
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
