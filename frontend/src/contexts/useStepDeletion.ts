import { useCallback, type MutableRefObject } from 'react';
import { toast } from 'sonner';
import { removedDescription } from '../lib/flow-history/historyText';
import type { RemoveStepMode } from '../lib/flow/flowEdit';
import { removeSteps } from '../lib/flow-graph/canvas/removeSteps';
import { flowService } from '../services/flowService';
import type { Flow } from '../types/flow.types';

interface Deps {
  activeFlowId: string | null | undefined;
  activeFlowRef: MutableRefObject<Flow | null>;
  patchActive: (patch: (flow: Flow) => Partial<Flow>) => void;
  markUnsaved: () => void;
  undo: () => void;
  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;
}

/** Remove one step or several at once: one change in the history, so one Undo brings them all back. */
export function useStepDeletion({ activeFlowId, activeFlowRef, patchActive, markUnsaved, undo, selectedNodeId, setSelectedNodeId }: Deps) {
  const deleteNodes = useCallback((nodeIds: string[], mode: RemoveStepMode = 'reconnect') => {
    if (!activeFlowId || nodeIds.length === 0) return;
    const prev = activeFlowRef.current;
    if (!prev) return;
    const first = prev.nodes.find((n) => n.id === nodeIds[0]);
    const { nodes: updatedNodes, edges: updatedEdges } = removeSteps({ nodes: prev.nodes, edges: prev.edges }, nodeIds, mode);
    const removedCount = prev.nodes.length - updatedNodes.length;
    patchActive(() => ({ nodes: updatedNodes, edges: updatedEdges }));
    flowService.updateNodesAndEdges(activeFlowId, updatedNodes, updatedEdges);
    if (selectedNodeId && !updatedNodes.some((n) => n.id === selectedNodeId)) setSelectedNodeId(null);
    markUnsaved();
    const label = (first?.data as { label?: string } | undefined)?.label;
    const action = { label: 'Undo', onClick: () => undo() };
    if (nodeIds.length > 1) toast(`${removedCount} steps deleted`, { description: 'They were removed from the flow. Undo puts them all back.', action });
    else toast('Node deleted', { description: removedDescription(label, removedCount), action });
  }, [activeFlowId, activeFlowRef, selectedNodeId, setSelectedNodeId, markUnsaved, undo, patchActive]);

  const deleteNode = useCallback((nodeId: string, mode: RemoveStepMode = 'reconnect') => deleteNodes([nodeId], mode), [deleteNodes]);
  return { deleteNode, deleteNodes };
}
