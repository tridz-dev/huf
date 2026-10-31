import { useEffect } from 'react';
import type { Edge, Node } from 'reactflow';
import { RENDER_ONLY_EDGE_PREFIX, RENDER_ONLY_NODE_PREFIX } from '@/lib/flow-graph/flowCanvasGraph';
import { actionHasConfiguredContent } from '@/lib/flow/flowNodeConfigured';
import type { FlowNodeData } from '@/types/flow.types';

interface Params {
  canManage: boolean;
  nodes: Node<FlowNodeData>[];
  edges: Edge[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Remove a step now (an empty step is not worth a question). */
  deleteNode: (id: string) => void;
  /** Ask before removing these steps (one, or all the selected ones together). */
  askDeleteSteps: (ids: string[]) => void;
  /** Ask before removing this connection. */
  askDeleteEdge: (id: string) => void;
}

const busy = (n: Node<FlowNodeData>) => n.data.status === 'running' || n.data.status === 'waiting';

/**
 * Delete / Backspace on the canvas: removes the selected step(s) after asking, or the selected connection when no step is selected.
 * With several steps selected it asks once for all of them ("Delete 3 steps?"). Never while typing or inside a dialog or menu.
 */
export function useCanvasDeleteKey({ canManage, nodes, edges, selectedNodeId, selectedEdgeId, deleteNode, askDeleteSteps, askDeleteEdge }: Params) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (!canManage) return;
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable || target?.closest('[role="dialog"], [role="alertdialog"], [role="combobox"], [role="listbox"], [role="menu"]')) return;
      // Only when the user is on the canvas (or nowhere in particular), never in another part of the page.
      if (target && target !== document.body && !target.closest('[data-testid="flow-canvas"]')) return;
      const picked = nodes.filter((n) => n.selected && !n.id.startsWith(RENDER_ONLY_NODE_PREFIX));
      const node = picked[0] ?? nodes.find((n) => n.id === selectedNodeId);
      if (!node) {
        // No step selected: Delete removes the selected connection (after asking).
        const edge = edges.find((ed) => ed.selected && !ed.id.startsWith(RENDER_ONLY_EDGE_PREFIX)) ?? edges.find((ed) => ed.id === selectedEdgeId);
        if (edge) {
          e.preventDefault();
          askDeleteEdge(edge.id);
        }
        return;
      }
      if (picked.length > 1) {
        const ids = picked.filter((n) => !busy(n)).map((n) => n.id);
        if (ids.length > 0) {
          e.preventDefault();
          askDeleteSteps(ids);
        }
        return;
      }
      if (busy(node)) return;
      e.preventDefault();
      if (node.data.nodeType === 'action' && !actionHasConfiguredContent(node.data)) deleteNode(node.id);
      else askDeleteSteps([node.id]);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [canManage, nodes, edges, selectedNodeId, selectedEdgeId, deleteNode, askDeleteSteps, askDeleteEdge]);
}
