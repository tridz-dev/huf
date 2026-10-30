/**
 * Duplicate step(s). One linear step is copied right behind itself and wired in (original -> copy -> what came next); a
 * branching step, an End, or several steps at once are copied beside the originals, with the connections among the copies kept.
 */
import { edgeRoute, makeFlowEdge } from '../../services/flowSerializer';
import { branchHandlesFor } from '../flow/flowBranches';
import { subtreeIds } from '../flow/flowEdgeLabels';
import { ROW_GAP } from '../flow/flowLayout';
import type { FlowEdge, FlowNode } from '../../types/flow.types';
import { cloneSteps, type Graph } from './cloneSteps';

/** Where a copy that is not wired in lands, relative to its original. */
export const COPY_OFFSET = { x: 48, y: 72 } as const;

export interface DuplicateResult extends Graph {
  /** Ids of the new steps, in the order of the originals. */
  addedIds: string[];
  /** The copy was wired in behind this step. */
  wiredAfter?: string;
  /** A trigger was part of the request and left out (a flow has only one). */
  skippedTrigger: boolean;
}

type Cfg = ({ type?: string } & Record<string, unknown>) | undefined;

/** One way in, one way out: a plain step that has at most one "next". */
export function isLinearStep(node: FlowNode, edges: FlowEdge[]): boolean {
  if (node.data.nodeType !== 'action') return false;
  const cfg = node.data.actionConfig as Cfg;
  if (cfg?.type === 'router' || branchHandlesFor(cfg?.type, cfg).length > 0) return false;
  const out = edges.filter((e) => e.source === node.id);
  return out.length === 0 || (out.length === 1 && edgeRoute(out[0]) === 'next');
}

/** The copy of a pinned example would be someone else's data; a copy starts without one. */
const withoutSample = (node: FlowNode): FlowNode => ({ ...node, data: { ...node.data, sample: undefined } });

export function duplicateSteps(graph: Graph, ids: string[], now: number): DuplicateResult | null {
  const existing = new Set(graph.nodes.map((n) => n.id));
  const picked = ids.filter((id) => existing.has(id));
  const steps = picked.filter((id) => graph.nodes.find((n) => n.id === id)?.data.nodeType !== 'trigger');
  const skippedTrigger = steps.length !== picked.length;
  if (steps.length === 0) return skippedTrigger ? { ...graph, addedIds: [], skippedTrigger } : null;

  const takenLabels = graph.nodes.map((n) => n.data.label);
  if (steps.length === 1) {
    const original = graph.nodes.find((n) => n.id === steps[0]) as FlowNode;
    if (isLinearStep(original, graph.edges)) {
      const out = graph.edges.find((e) => e.source === original.id);
      const clone = cloneSteps(graph, steps, existing, {
        now,
        takenLabels,
        place: (n) => ({ x: n.position.x, y: n.position.y + ROW_GAP }),
        adjust: withoutSample,
      });
      const copy = clone.nodes[0];
      // Whatever came after the original now comes after the copy, and moves down to make room.
      const moving = out ? subtreeIds(out.target, graph.edges) : new Set<string>();
      const nodes = graph.nodes.map((n) => (moving.has(n.id) ? { ...n, position: { x: n.position.x, y: n.position.y + ROW_GAP } } : n));
      const edges = graph.edges.filter((e) => e !== out);
      edges.push(makeFlowEdge(original.id, copy.id, 'next', { label: copy.data.label }));
      if (out) edges.push({ ...out, ...makeFlowEdge(copy.id, out.target, 'next', { label: typeof out.label === 'string' ? out.label : undefined }) });
      return { nodes: [...nodes, copy], edges, addedIds: [copy.id], wiredAfter: original.id, skippedTrigger };
    }
  }

  const clone = cloneSteps(graph, steps, existing, {
    now,
    takenLabels,
    place: (n) => ({ x: n.position.x + COPY_OFFSET.x, y: n.position.y + COPY_OFFSET.y }),
    adjust: withoutSample,
  });
  return {
    nodes: [...graph.nodes, ...clone.nodes],
    edges: [...graph.edges, ...clone.edges],
    addedIds: steps.map((id) => clone.idMap.get(id) as string),
    skippedTrigger,
  };
}
