import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import type { GraphSnapshot } from '../lib/flow-history/graphChange';
import { flowService } from '../services/flowService';
import type { Flow } from '../types/flow.types';

interface Deps {
  activeFlowId: string | null | undefined;
  activeFlowRef: MutableRefObject<Flow | null>;
  lastSyncedFlowRef: MutableRefObject<Flow | null>;
  setActiveFlowState: Dispatch<SetStateAction<Flow | null>>;
  setSelectedNodeId: Dispatch<SetStateAction<string | null>>;
  setSelectedEdgeId: Dispatch<SetStateAction<string | null>>;
  setLayoutRevision: Dispatch<SetStateAction<number>>;
  markUnsaved: () => void;
}

/** Put a snapshot from the history back (layoutRevision makes the canvas re-read it; selection and live status are not part of it). */
export function useSnapshotRestore({ activeFlowId, activeFlowRef, lastSyncedFlowRef, setActiveFlowState, setSelectedNodeId, setSelectedEdgeId, setLayoutRevision, markUnsaved }: Deps) {
  return useCallback((snapshot: GraphSnapshot) => {
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
  }, [activeFlowId, activeFlowRef, lastSyncedFlowRef, setActiveFlowState, setSelectedNodeId, setSelectedEdgeId, setLayoutRevision, markUnsaved]);
}
